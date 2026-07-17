"""
app.py
------
Flask server entry point for the PII Shield Web Application.

Endpoints:
    - GET  /                  : Renders the beautiful glassmorphism frontend.
    - POST /redact            : Receives a DOCX file, runs the hybrid AI pipeline,
                                saves the result, and returns redaction summary
                                + deduplicated audit mapping logs.
    - GET  /download/<name>   : Serves the redacted document for download.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, send_from_directory

import config
from detector import PIIDetector
from fake_generator import FakeGenerator
from redactor import DocxRedactor
from utils import setup_logger

# Initialize logger and Flask app
logger = setup_logger("app")
app = Flask(__name__)

# Configure upload and output folders
UPLOAD_FOLDER = Path("input")
OUTPUT_FOLDER = Path("output")
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
# Limit upload size to 25MB
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Preload heavy NLP models and pipeline components globally at startup.
# This prevents RAM spikes (OOM) and timeouts during active requests.
logger.info("Initializing global PII detection pipeline and preloading spaCy/Presidio...")
detector = PIIDetector()
fake_generator = FakeGenerator()
logger.info("Global pipeline initialized successfully!")


@app.route("/")
def index():
    """Render the main single-page web app."""
    return render_template("index.html")


@app.route("/redact", methods=["POST"])
def redact_document():
    """API endpoint to upload and redact a document."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected for upload"}), 400

    if not file.filename.endswith(".docx"):
        return jsonify({"error": "Invalid file type. Only .docx files are supported"}), 400

    try:
        # 1. Parse and apply configuration toggle
        redact_non_pii = request.form.get("redact_non_pii") == "true"
        config.REDACT_NON_PII_IDENTIFIERS = redact_non_pii
        logger.info("Configuration: REDACT_NON_PII_IDENTIFIERS = %s", redact_non_pii)

        # 2. Save the uploaded file securely
        orig_filename = secure_filename(file.filename)
        # Create a unique filename using timestamp to avoid conflict
        timestamp = int(time.time())
        filename = f"{Path(orig_filename).stem}_{timestamp}.docx"
        input_path = UPLOAD_FOLDER / filename
        file.save(input_path)
        logger.info("Saved uploaded file to %s", input_path)

        # 3. Initialize redactor using the globally preloaded pipeline components
        redactor = DocxRedactor(detector=detector, fake_generator=fake_generator)

        # 4. Process document redaction
        t0 = time.time()
        output_filename = f"{Path(orig_filename).stem}_redacted_{timestamp}.docx"
        output_path = OUTPUT_FOLDER / output_filename
        
        stats = redactor.redact_file(str(input_path), str(output_path))
        elapsed = time.time() - t0
        logger.info("Redacted document in %.1fs", elapsed)

        # 5. Extract and deduplicate the mapping log
        unique_mappings = []
        seen = set()
        for orig, fake, label in redactor.mapping_log:
            tup = (orig, fake, label)
            if tup not in seen:
                seen.add(tup)
                unique_mappings.append({
                    "original": orig,
                    "fake": fake,
                    "label": label
                })

        # 6. Return stats and mappings
        return jsonify({
            "success": True,
            "output_filename": output_filename,
            "stats": {
                "total_entities": stats.total_entities,
                "by_label": stats.by_label,
                "elapsed_time": elapsed
            },
            "mapping_log": unique_mappings
        })

    except Exception as exc:
        logger.error("Error during document redaction: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@app.route("/download/<filename>")
def download_file(filename):
    """Serve the redacted file for download."""
    # Prevent directory traversal attacks
    filename = secure_filename(filename)
    return send_from_directory(
        directory=app.config["OUTPUT_FOLDER"],
        path=filename,
        as_attachment=True
    )


if __name__ == "__main__":
    # Host on all interfaces, port 5000
    app.run(host="0.0.0.0", port=5000, debug=True)
