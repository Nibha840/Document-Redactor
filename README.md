# PII Redaction Tool

A Python tool that reads a `.docx` document, detects personally identifiable information (PII), and produces a new `.docx` with every detected PII value replaced by a **realistic, consistent fake value** — the same real value always maps to the same fake value everywhere it appears — while preserving the original document's formatting.

**Built for the Scaler AI Labs assignment (PII Redaction Tool).**

---

## 📋 Overview

- **Input:** any `.docx` file (paragraphs, tables, headers, footers)
- **Output:** 
  - Redacted `.docx` file
  - Redaction summary report
  - (Optional) Precision/recall/F1 evaluation report against ground-truth
  
- **Detects:**
  - Full names
  - Email addresses
  - Phone numbers
  - Company names
  - Physical/mailing addresses
  - SSNs
  - Credit card numbers
  - Dates of birth
  - IP addresses

- **Avoids over-redacting:** order/ticket/invoice/case/reference numbers are left untouched unless explicitly configured otherwise

---

## ✨ Key Features

1. **Hybrid Detection Pipeline**
   - Regex for structured PII (email, phone, SSN, credit card, IP, dates)
   - spaCy NER for free-text PII (names, organizations, addresses)
   - Merged with overlap resolution

2. **Consistent Fake Mapping**
   - A value seen 15 times becomes the same fake value 15 times
   - Uses normalized-key → fake-value dictionary

3. **Format-Preserving Redaction**
   - Edits Word XML runs in place (via `python-docx`)
   - Preserves fonts, bold/italic, table shading, and styles

4. **Full Document Coverage**
   - Body paragraphs, tables (including nested tables)
   - All header/footer variants (default, first-page, even-page)

5. **Evaluation Pipeline**
   - Precision/recall/F1/accuracy per entity type
   - Against JSON ground-truth file
   - Exported as CSV + Markdown

6. **CLI & Web Interface**
   - Command-line interface with logging
   - Mapping-log export
   - Pluggable architecture for adding new PII types
   - Flask web application with interactive dashboard

---

## 🛠️ Installation

```bash
cd PII_Redaction
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

---

## 🚀 How to Run

### Basic Redaction (CLI)
```bash
python main.py input/document.docx output/document_redacted.docx
```

### With Ground-Truth Evaluation
```bash
python main.py input/sample_test.docx output/sample_test_redacted.docx \
  --ground-truth reports/ground_truth.json
```

### Export Mapping Log as JSON
```bash
python main.py input/document.docx output/document_redacted.docx \
  --mapping-log reports/mapping_log.json
```

### Run Flask Web Application
```bash
python app.py
```

Open your browser and navigate to `http://localhost:5000` to access the interactive redactor dashboard.

Reports are written to `reports/`:
- `redaction_summary.md`
- `evaluation_report.csv` / `evaluation_report.md` (if `--ground-truth` is passed)

---

## 📁 Project Architecture

```
PII_Redaction/
├── main.py                  CLI entry point — wires everything together
├── app.py                   Flask Web Server — serves template and redact APIs
├── config.py                Entity types, regex patterns, stoplists, Faker config
├── utils.py                 Entity dataclass, overlap-merge logic, logging
│
├── Detection Modules
│   ├── regex_detector.py    Layer 1: structured PII (email/phone/ssn/card/ip/dob)
│   ├── ner_detector.py      Layer 2: spaCy NER (person/org/address)
│   ├── presidio_detector.py Layer 3: Microsoft Presidio (contextual PII)
│   └── detector.py          Orchestrates all layers, merges overlapping spans
│
├── Processing Modules
│   ├── fake_generator.py    Faker-backed, consistent original→fake mapping
│   ├── redactor.py          Reads/writes .docx, run-level text replacement
│   └── evaluator.py         Precision/recall/F1 against ground truth
│
├── Web Interface
│   ├── templates/
│   │   └── index.html       Main glassmorphic single-page web interface
│   └── static/
│       ├── style.css        Glassmorphism design system & visual variables
│       └── script.js        Drag-and-drop logic & chart/log rendering
│
├── Data Directories
│   ├── input/               Source .docx files
│   ├── output/              Redacted .docx files
│   └── reports/             Summary + evaluation reports
│
├── requirements.txt         Project dependencies
└── README.md                This file
```

---

## 🔍 Detection Pipeline

### **Layer 1 — Regex** (`regex_detector.py`)

Catches PII with predictable structure. Ambiguous numeric patterns are disambiguated with:
- Digit-count checks
- Luhn check for card numbers
- Look-behind context guards

A number preceded by "Invoice No.", "Order Number", "Ticket ID", etc. is **not** redacted (matches assignment default).

Dates are only treated as **DOB** if nearby keywords ("born", "DOB", "date of birth") are present.

### **Layer 2 — spaCy NER** (`ner_detector.py`)

Catches free-text PII: PERSON, ORG, GPE/LOC/FAC (merged into ADDRESS).

**Optimizations for legal/financial text:**
- Single-token PERSON/ORG hits matching generic legal vocabulary are dropped ("Board", "Offer", "Company", "DEFINITIONS")
- ALL-CAPS ORG candidates trusted only if they contain company/legal suffix (LIMITED, LLP, BANK, TECHNOLOGIES...)
- ORG candidates that are reference-number labels ("Invoice No", "Order Number") are dropped

### **Layer 3 — Microsoft Presidio** (`presidio_detector.py`)

Provides highly robust, context-aware PII detection:
- PERSON, EMAIL_ADDRESS, PHONE_NUMBER, ORGANIZATION
- LOCATION, US_SSN, CREDIT_CARD, DATE_TIME, IP_ADDRESS

Uses Presidio Analyzer Engine with machine learning and pattern matching. Custom logic applied to match Layer 1 & 2 behavior.

### **Merge** (`utils.merge_entities`)

Overlapping spans resolved by:
1. Preferring longer span
2. Source/label priority as tiebreaker: structured regex types > names/phone > org/address

---

## 💱 Replacement Strategy

`fake_generator.py` uses `Faker` (locale `en_IN`, seeded for determinism) to generate realistic fake values:
- Names
- Emails
- Company names
- Indian-style addresses
- SSNs
- Credit cards
- Dates of birth
- IPv4 addresses

**Consistency:** A normalized key (case/whitespace-insensitive; digits-only for phone/SSN/card) ensures **every occurrence of the same real value gets the same fake value** throughout the document.

---

## 📊 Evaluation Approach

Evaluation is performed on `input/sample_test.docx` — a synthetic document seeded with known values across **all nine PII types** plus deliberate decoys (order numbers, invoice numbers, case IDs) to test false-positive avoidance.

Ground truth: `reports/ground_truth.json`

**Metrics per entity type:**
- **True Positive:** predicted span matches ground-truth item (exact or containment match)
- **False Positive:** predicted span with no matching ground-truth item
- **False Negative:** ground-truth item with no matching prediction

**Overall accuracy:** micro `TP / (TP + FP + FN)`

### Latest Performance (sample_test.docx)

| Entity Type | Precision | Recall | F1 |
|---|---|---|---|
| ADDRESS | 0.500 | 1.000 | 0.667 |
| CREDIT_CARD | 1.000 | 1.000 | 1.000 |
| DOB | 1.000 | 1.000 | 1.000 |
| EMAIL | 1.000 | 0.750 | 0.857 |
| IP_ADDRESS | 1.000 | 1.000 | 1.000 |
| PHONE | 1.000 | 1.000 | 1.000 |
| SSN | 1.000 | 1.000 | 1.000 |
| ORG | 0.750 | 1.000 | 0.857 |
| PERSON | 0.889 | 1.000 | 0.941 |
| **OVERALL** | **0.862** | **0.962** | **0.909** |

> Structured, regex-caught types are nearly perfect. PERSON/ORG (NER-based) carry residual noise discussed below.

---

## ⚠️ Tradeoffs & Known Limitations

### NER Precision on Legal/Financial Text
- spaCy's `en_core_web_sm` is trained on general news text
- Dense prospectus text (all-caps headers, tables, boilerplate) produces some PERSON/ORG false positives even after stoplist/suffix heuristics
- Examples: "Pune" or "Registrar of Companies" occasionally over-redacted as ORG
- **Future improvement:** Presidio's recognizers or fine-tuned legal-domain NER model

### Same Text, Different Labels
- NER can tag identical strings as PERSON in one sentence and ORG in another (context-dependent)
- Example: "Rohan Dey" tagged as PERSON once, ORG another time
- Fake-value cache keyed by `(label, normalized text)` → can produce two different fake values for one person
- **Note:** Not observed for structured (regex) types

### Address Boundaries
- Multi-component addresses stitched via character-gap heuristic rather than true address parser
- Unusually formatted addresses may split into multiple ADDRESS entities or leak un-merged

### Reference Numbers vs. Real PII
- Context-guard list deliberately keeps order/invoice/ticket/case numbers un-redacted (assignment preference)
- Set `config.REDACT_NON_PII_IDENTIFIERS = True` to override

### Text Boxes
- Content inside Word text boxes (floating shapes) not currently supported by `python-docx`
- Out of scope for this version

---

## 🔧 Extending: Adding a New PII Type

1. **Add entity constant** to `config.EntityType`

2. **Add detection logic:**
   - If structured: add regex to `config.REGEX_PATTERNS` + `_detect_x` method in `regex_detector.py`
   - If free-text: map spaCy label in `config.SPACY_LABEL_MAP`

3. **Add fake generation** `_fake_x` branch in `fake_generator.py`

4. **No changes needed** to `detector.py`, `redactor.py`, or `evaluator.py` — they're generic over the entity list

---

## 📦 Deliverables

| File | Description |
|---|---|
| `main.py` + all source modules | Complete source code |
| `requirements.txt` | Dependencies |
| `README.md` | This file |
| `input/Red_Herring_Prospectus.docx` | Original assignment document |
| `output/Red_Herring_Prospectus_redacted.docx` | Redacted output |
| `input/sample_test.docx` | Synthetic test doc (all 9 PII types) |
| `output/sample_test_redacted.docx` | Redacted test output |
| `reports/ground_truth.json` | Ground-truth annotations |
| `reports/evaluation_report.csv` / `.md` | Precision/recall/F1 report |
| `reports/redaction_summary.md` | Per-run entity counts |
| `reports/prospectus_mapping_log.json` | Full original→fake audit trail |

---

## 📝 License

Built for Scaler AI Labs assignment.

## 👤 Author

**Nibha840**

---

**Last Updated:** July 2026
