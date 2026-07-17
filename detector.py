"""
detector.py
-----------
Top-level detection orchestrator. Runs each detection layer over a block of
text and merges their outputs into a single, non-overlapping list of
`Entity` objects ready for redaction.

Adding a new PII type:
    1. Add the label to `config.EntityType`.
    2. Add a regex pattern to `config.REGEX_PATTERNS` (if structured) and a
       `_detect_x` method to `RegexDetector`, OR map a spaCy label to it in
       `config.SPACY_LABEL_MAP` (if free-text).
    3. Add a corresponding fake-value generator branch in
       `fake_generator.py`.
    No changes are required here — `PIIDetector.detect` is generic.
"""

from __future__ import annotations

from typing import List

import config
from ner_detector import NERDetector
from regex_detector import RegexDetector
from presidio_detector import PresidioDetector
from utils import Entity, merge_entities, setup_logger

logger = setup_logger(__name__)


class PIIDetector:
    """Runs the full hybrid (regex + NER + Presidio) detection pipeline over text."""

    def __init__(self) -> None:
        self.regex_detector = RegexDetector()
        self.ner_detector = NERDetector()
        self.presidio_detector = PresidioDetector()

    def detect(self, text: str) -> List[Entity]:
        if not text or not text.strip():
            return []

        regex_entities = self.regex_detector.detect(text)
        ner_entities = self.ner_detector.detect(text)
        presidio_entities = self.presidio_detector.detect(text)

        merged = merge_entities(regex_entities + ner_entities + presidio_entities)
        
        # Apply global stopword filtering to prevent false-positive corporate terms
        filtered = []
        for ent in merged:
            ent_text_clean = ent.text.lower().strip()
            if ent_text_clean in config.GLOBAL_STOPWORDS:
                logger.debug("Filtered out stopword entity: '%s'", ent.text)
                continue
            filtered.append(ent)

        logger.debug(
            "Detected %d regex + %d ner + %d presidio -> %d merged -> %d filtered entities",
            len(regex_entities), len(ner_entities), len(presidio_entities), len(merged), len(filtered)
        )
        return filtered

