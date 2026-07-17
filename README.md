# PII Redaction Tool

A Python tool that reads a `.docx` document, detects personally identifiable
information (PII), and produces a new `.docx` with every detected PII value
replaced by a **realistic, consistent fake value** — the same real value
always maps to the same fake value everywhere it appears — while preserving
the original document's formatting.

Built for the Scaler AI Labs assignment (PII Redaction Tool).

## Overview

- **Input:** any `.docx` file (paragraphs, tables, headers, footers).
- **Output:** a redacted `.docx`, a redaction summary, and (optionally) a
  precision/recall/F1 evaluation report against a ground-truth file.
- **Detects:** Full names, email addresses, phone numbers, company names,
  physical/mailing addresses, SSNs, credit card numbers, dates of birth, IP
  addresses.
- **Avoids over-redacting:** order/ticket/invoice/case/reference numbers are
  left untouched unless explicitly configured otherwise.

## Features

- **Hybrid detection pipeline** — regex for structured PII (email, phone,
  SSN, credit card, IP, dates) + spaCy NER for free-text PII (names, orgs,
  addresses), merged with overlap resolution.
- **Consistent fake mapping** — a value seen 15 times becomes the same fake
  value 15 times, via a normalized-key → fake-value dictionary.
- **Format-preserving redaction** — edits Word XML runs in place (via
  `python-docx`) rather than rebuilding the document, so fonts, bold/italic,
  table shading, and styles survive untouched.
- **Full document coverage** — body paragraphs, tables (including nested
  tables), and all header/footer variants (default, first-page, even-page).
- **Evaluation pipeline** — precision/recall/F1/accuracy per entity type
  against a JSON ground-truth file, exported as CSV + Markdown.
- **CLI** with logging, mapping-log export, and a pluggable architecture for
  adding new PII types.

## Installation

```bash
cd PII_Redaction
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## How to Run

```bash
# Basic redaction (CLI)
python main.py input/document.docx output/document_redacted.docx

# With evaluation against a ground-truth annotation file
python main.py input/sample_test.docx output/sample_test_redacted.docx --ground-truth reports/ground_truth.json

# Export mapping log as JSON
python main.py input/document.docx output/document_redacted.docx --mapping-log reports/mapping_log.json

# Run the Flask Web Application (Frontend + Backend)
python app.py
```

Open your browser and navigate to `http://localhost:5000` to access the premium interactive redactor dashboard.

Reports are written to `reports/` (`redaction_summary.md`, and — if
`--ground-truth` is passed — `evaluation_report.csv` / `.md`).


## Architecture

```
PII_Redaction/
├── main.py            CLI entry point — wires everything together
├── app.py             Flask Web Server — serves template and redact APIs
├── config.py           Entity types, regex patterns, stoplists, Faker config
├── utils.py             Entity dataclass, overlap-merge logic, logging
├── regex_detector.py    Layer 1: structured PII (email/phone/ssn/card/ip/dob)
├── ner_detector.py      Layer 2: spaCy NER (person/org/address)
├── presidio_detector.py Layer 3: Microsoft Presidio (contextual PII)
├── detector.py          Orchestrates regex + NER + Presidio, merges overlapping spans
├── fake_generator.py    Faker-backed, consistent original->fake mapping
├── redactor.py          Reads/writes .docx, run-level text replacement
├── evaluator.py         Precision/recall/F1 against ground truth
├── templates/           HTML templates for the web interface
│   └── index.html       Main glassmorphic single-page web interface
├── static/              Static client-side assets
│   ├── style.css        Glassmorphism design system & visual variables
│   └── script.js        Drag-and-drop logic & chart/log rendering
├── input/               Source .docx files
├── output/               Redacted .docx files
└── reports/              Summary + evaluation reports
```


## Detection Pipeline

**Layer 1 — Regex** (`regex_detector.py`): catches PII with a predictable
shape. Ambiguous numeric patterns (phone vs. credit card vs. a plain
reference number) are disambiguated with digit-count checks, a Luhn check
for card numbers, and a look-behind context guard — a number preceded by
"Invoice No.", "Order Number", "Ticket ID", etc. is *not* redacted, matching
the assignment's default. Dates are only treated as **DOB** if a nearby
keyword ("born", "DOB", "date of birth") is present; otherwise they're left
alone (a prospectus is full of filing/incorporation dates that are not a
person's birth date).

**Layer 2 — spaCy NER** (`ner_detector.py`): catches free-text PII — PERSON,
ORG, and GPE/LOC/FAC (merged into ADDRESS when they sit close together, e.g.
"Pune", "Maharashtra", "410 501" collapsing into one address span). Several
heuristics were added after inspecting output on a real, dense financial
document (a Red Herring Prospectus) to cut down NER noise specific to
legal/financial text:
  - Single-token PERSON/ORG hits matching a stoplist of generic legal
    vocabulary ("Board", "Offer", "Company", "DEFINITIONS") are dropped.
  - ALL-CAPS ORG candidates are only trusted if they contain a company/legal
    suffix (LIMITED, LLP, BANK, TECHNOLOGIES...) — otherwise section
    headings (which are also capitalized runs) get mis-tagged as companies.
  - ORG candidates that are actually reference-number labels ("Invoice No",
    "Order Number") are dropped.

**Layer 3 — Microsoft Presidio** (`presidio_detector.py`): provides highly robust,
context-aware PII detection (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, ORGANIZATION,
LOCATION, US_SSN, CREDIT_CARD, DATE_TIME, and IP_ADDRESS). It uses the Presidio
Analyzer Engine to validate and score entities, utilizing machine learning and
pattern matching. We apply customized logic (such as context checking for DOB
and stoplist filtering for numbers) to match the behavior of Layer 1 & 2.

**Merge** (`utils.merge_entities`): overlapping spans from all layers are
resolved by preferring the longer span, then a source/label priority
(structured regex types > names/phone > org/address) as a tiebreaker.

## Replacement Strategy

`fake_generator.py` uses `Faker` (locale `en_IN`, seeded for determinism)
to generate a realistic fake value per entity type (name, email, company,
Indian-style address, SSN, credit card, DOB, IPv4). A normalized key
(case/whitespace-insensitive; digits-only for phone/SSN/card) is used to
cache the mapping, so **every occurrence of the same real value gets the
same fake value** throughout the document.

## Evaluation Approach

Because the primary target document (a real Red Herring Prospectus) is a
public financial filing and naturally contains no SSNs, credit cards, or
IP addresses, evaluation is done on `input/sample_test.docx` — a synthetic
document seeded with known values across **all nine** PII types plus
deliberate decoys (order numbers, invoice numbers, case IDs) to test
false-positive avoidance. Ground truth lives in `reports/ground_truth.json`.

For each entity type: **True Positive** = predicted span matches a
ground-truth item of the same label (exact or containment match, to tolerate
minor boundary differences); **False Positive** = predicted span with no
matching ground-truth item; **False Negative** = ground-truth item with no
matching prediction. Precision/Recall/F1 are computed per type, and overall
**accuracy** as micro `TP / (TP + FP + FN)`.

**Latest run on `sample_test.docx`** (see `reports/evaluation_report.md` for
the live numbers — reproduce with the command above):

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


Structured, regex-caught types are effectively perfect. PERSON/ORG (NER-
based) carry the residual noise, discussed below.

## Tradeoffs & Known False Positives/Negatives

- **NER precision on legal/financial text.** spaCy's `en_core_web_sm` is
  trained on general news text; a dense prospectus (all-caps headers,
  tables, boilerplate like "the Board", "the Offer") produces some
  PERSON/ORG false positives even after the stoplist/suffix heuristics
  above. On the real prospectus this is visible as things like "Pune" or
  "Registrar of Companies" occasionally being over-redacted as ORG. Using
  Presidio's recognizers or a fine-tuned/legal-domain NER model would
  reduce this further; it was left out here to keep the dependency
  footprint light and the run time reasonable (~60s for a ~90-page
  document) — noted as a natural next step.
- **Same text, different label across occurrences.** NER can tag the exact
  same string as PERSON in one sentence and ORG in another, depending on
  surrounding context (e.g. "Rohan Dey" once as PERSON, once mis-tagged as
  ORG). Because the fake-value cache is keyed by `(label, normalized text)`,
  this rare case can produce two different fake values for what's really
  one person. Not observed for any of the structured (regex) types, which
  don't have this ambiguity.
- **Address boundaries.** Multi-component addresses (street, city, state,
  PIN code) are stitched together via a character-gap heuristic
  (`ner_detector._merge_address_runs`) rather than a true address parser,
  so unusually formatted addresses may be split into two ADDRESS entities
  instead of one, or a lone city/state token may leak through un-merged.
- **Reference numbers vs. real PII.** The context-guard list
  (`config.NON_PII_NUMBER_CONTEXT_WORDS`) deliberately keeps order/invoice/
  ticket/case numbers un-redacted by default, per the assignment's stated
  preference. Set `config.REDACT_NON_PII_IDENTIFIERS = True` to redact them
  too.
- **Text boxes.** Content inside Word text boxes (drawn as floating shapes,
  not regular paragraph flow) is not currently walked by `python-docx` and
  is out of scope for this version.
- **Microsoft Presidio integration.** Integrated as Layer 3 to provide robust, context-aware PII detection, complementing Regex and spaCy NER. Under the hood, Presidio employs machine learning model recognizers along with rule-based systems to yield enterprise-grade recall.


## Extending: Adding a New PII Type

1. Add a constant to `config.EntityType`.
2. If structured: add a regex to `config.REGEX_PATTERNS` and a
   `_detect_x` method in `regex_detector.py`. If free-text: map a spaCy
   label to it in `config.SPACY_LABEL_MAP`.
3. Add a `_fake_x` branch in `fake_generator.py`.
4. No changes needed to `detector.py`, `redactor.py`, or `evaluator.py` —
   they're generic over the entity list.

## Deliverables in This Submission

| File | Description |
|---|---|
| `main.py` + all source modules | Complete source code |
| `requirements.txt` | Dependencies |
| `README.md` | This file |
| `input/Red_Herring_Prospectus.docx` | Original assignment document |
| `output/Red_Herring_Prospectus_redacted.docx` | Redacted output |
| `input/sample_test.docx` | Synthetic test doc covering all 9 PII types |
| `output/sample_test_redacted.docx` | Its redacted output |
| `reports/ground_truth.json` | Ground-truth annotations for evaluation |
| `reports/evaluation_report.csv` / `.md` | Precision/recall/F1 report |
| `reports/redaction_summary.md` | Per-run entity counts |
| `reports/prospectus_mapping_log.json` | Full original→fake audit trail |
#   D o c u m e n t - R e d a c t o r 
 
 #   D o c u m e n t - R e d a c t o r 
 
 


