"""
config.py
---------
Centralized configuration for the PII Redaction Tool.

Holds:
    - Entity type constants
    - Regex patterns (Layer 1 detection)
    - spaCy label -> internal entity type mapping (Layer 2 detection)
    - False-positive guard lists (things that look like numbers but are NOT PII)
    - Faker locale / seeding configuration
    - Confidence weights used when merging overlapping detections

Changing behaviour of the tool (e.g. adding a new PII type) should, in the
common case, only require edits to this file plus a new `detect_*` method.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Entity type constants
# --------------------------------------------------------------------------- #
class EntityType:
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ORG = "ORG"
    ADDRESS = "ADDRESS"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    DOB = "DOB"
    IP_ADDRESS = "IP_ADDRESS"

    ALL = [PERSON, EMAIL, PHONE, ORG, ADDRESS, SSN, CREDIT_CARD, DOB, IP_ADDRESS]


# --------------------------------------------------------------------------- #
# Regex patterns (Layer 1)
# --------------------------------------------------------------------------- #
# Order matters when two patterns could both match the same span; more
# specific patterns (SSN, CREDIT_CARD) are checked before generic ones.
REGEX_PATTERNS: dict[str, str] = {
    # user@example.com style addresses
    EntityType.EMAIL: r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",

    # US-style SSN: 123-45-6789  (word-boundary guarded so it doesn't eat
    # into longer numbers like phone/card numbers)
    EntityType.SSN: r"\b\d{3}-\d{2}-\d{4}\b",

    # Credit cards: 13-19 digits, optionally grouped by spaces or dashes in
    # blocks of 4 (covers Visa/MC/Amex/Discover common groupings)
    EntityType.CREDIT_CARD: r"\b(?:\d[ -]?){13,19}\b",

    # IPv4 addresses
    EntityType.IP_ADDRESS: r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b",

    # Phone numbers: optional country code, separators, 10 local digits.
    # Covers +91 98765 43210, (555) 123-4567, 555-123-4567, 9876543210, etc.
    EntityType.PHONE: r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?"
    r"(?:\(\d{2,4}\)[-.\s]?)?\d{3,5}[-.\s]?\d{3,4}[-.\s]?\d{0,4}(?!\d)",

    # Dates (many human formats). Whether a given date match is a DOB vs. a
    # filing date etc. is disambiguated in ner_detector.py using nearby
    # keywords ("born", "DOB", "date of birth").
    EntityType.DOB: r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|(?:January|February|March|April|May|June|July|August|September"
    r"|October|November|December)\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)\s+\d{4})\b",
}

# Keywords near a DOB-pattern date that upgrade it from "generic date" to
# a true Date-of-Birth for redaction purposes.
DOB_CONTEXT_KEYWORDS = [
    "date of birth", "dob", "born", "birth date", "birthdate",
]

# Minimum digit count for something to even be considered for CREDIT_CARD /
# PHONE / SSN classification once separators are stripped.
CREDIT_CARD_DIGIT_RANGE = (13, 19)
PHONE_DIGIT_RANGE = (7, 13)

# --------------------------------------------------------------------------- #
# spaCy NER label -> internal entity type mapping (Layer 2)
# --------------------------------------------------------------------------- #
SPACY_LABEL_MAP = {
    "PERSON": EntityType.PERSON,
    "ORG": EntityType.ORG,
    "GPE": EntityType.ADDRESS,   # cities/states/countries -> treated as address components
    "LOC": EntityType.ADDRESS,
    "FAC": EntityType.ADDRESS,   # named facilities/buildings
}

# --------------------------------------------------------------------------- #
# Microsoft Presidio label -> internal entity type mapping (Layer 3)
# --------------------------------------------------------------------------- #
PRESIDIO_LABEL_MAP = {
    "PERSON": EntityType.PERSON,
    "EMAIL_ADDRESS": EntityType.EMAIL,
    "PHONE_NUMBER": EntityType.PHONE,
    "ORGANIZATION": EntityType.ORG,
    "LOCATION": EntityType.ADDRESS,
    "US_SSN": EntityType.SSN,
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "DATE_TIME": EntityType.DOB,
    "IP_ADDRESS": EntityType.IP_ADDRESS,
}


# --------------------------------------------------------------------------- #
# False-positive guards
# --------------------------------------------------------------------------- #
# Numeric-looking strings preceded by these words should NOT be redacted as
# CREDIT_CARD/PHONE/SSN even if they match the numeric shape, unless the
# corresponding config flag below is explicitly turned on.
NON_PII_NUMBER_CONTEXT_WORDS = [
    "order no", "order number", "order id", "order #",
    "ticket no", "ticket number", "ticket id", "ticket #",
    "invoice no", "invoice number", "invoice id", "invoice #",
    "reference no", "reference number", "ref no", "ref.", "ref#",
    "case no", "case number", "case id",
    "tracking no", "tracking number", "tracking id",
    "receipt no", "receipt number",
    "po number", "po no",
    "cin:", "isin:", "regulation", "section", "page", "clause", "rule",
    "act,", "ifsc", "pin code", "pincode",
]

# Flip to True if the assignment wants order/ticket/invoice numbers treated
# as sensitive too. Default False, matching the assignment's stated default.
REDACT_NON_PII_IDENTIFIERS = False

# spaCy sometimes tags common financial/legal terms as ORG/PERSON in dense
# prospectus-style text. These are filtered out as known non-PII noise.
ORG_STOPLIST = {
    "sebi", "rbi", "nse", "bse", "gst", "pan", "tan", "icdr", "reit",
    "sme", "ipo", "qib", "nii", "rii", "kyc", "cin", "isin", "llp",
}
PERSON_STOPLIST: set[str] = set()

# Legal/company-entity suffixes. An ALL-CAPS ORG candidate is only trusted
# as a real organization name if it contains one of these -- otherwise dense
# legal/financial documents (prospectuses, contracts) cause spaCy to
# mis-tag section headings ("DEFINITIONS", "CURRENCY", "OFFER") as ORG,
# since headings are capitalized runs just like real company names.
ORG_SUFFIX_KEYWORDS = [
    "limited", "ltd", "llp", "inc", "incorporated", "corp", "corporation",
    "bank", "technologies", "industries", "company", "co.", "group",
    "trust", "enterprises", "solutions", "holdings", "capital", "ventures",
    "partners", "associates", "services",
]

# Generic capitalized words that are frequently mis-tagged as PERSON in
# headings/tables of legal documents ("Board", "Offer", "Company"...).
# A single-token PERSON candidate matching this list is rejected; multi-
# token candidates are still evaluated normally.
PERSON_SINGLE_TOKEN_STOPLIST = {
    "board", "offer", "company", "issuer", "promoter", "promoters",
    "director", "directors", "committee", "management", "trust", "group",
    "prospectus", "issue", "shares", "equity", "capital", "registrar",
    "underwriter", "lead", "manager", "bidder", "applicant", "allottee",
}

# ORG candidates that are actually a reference-number label ("Invoice No",
# "Order Number", "Case ID"...) rather than an organization name. Matched
# as a case-insensitive prefix against the full candidate text.
ORG_REFERENCE_LABEL_PREFIXES = [
    "invoice", "order", "ticket", "case", "reference", "tracking",
    "receipt", "po number", "po no",
]

# --------------------------------------------------------------------------- #
# Faker / determinism configuration
# --------------------------------------------------------------------------- #
FAKER_LOCALE = "en_IN"   # Indian locale gives realistic Indian-style fakes
FAKER_SEED = 42          # deterministic fake generation across runs

# --------------------------------------------------------------------------- #
# Global stoplist for common document terms to avoid false-positive NER matches
# --------------------------------------------------------------------------- #
GLOBAL_STOPWORDS = {
    "promoter", "promoters", "our promoters", "promoter group",
    "registered office", "corporate office", "registered", "office", "offices",
    "lead manager", "lead managers", "book running lead managers", "book running lead manager",
    "details of the offer", "the offer", "offer", "details of offer", "offers",
    "board of directors", "board", "director", "directors", "management", "committee",
    "table of contents", "contents", "glossary", "definitions", "abbreviations",
    "annexure", "annexures", "schedule", "schedules", "exhibit", "exhibits",
    "prospectus", "red herring", "red herring prospectus", "draft red herring prospectus", "drhp", "rhp",
    "equity shares", "shares", "equity", "share capital", "capital",
    "registrar", "registrars", "underwriter", "underwriters", "syndicate",
    "corporate", "incorporation", "history", "constitution",
    "financial statements", "financial statement", "audit report", "auditors", "auditor",
    "table", "page", "section", "summary", "overview", "index",
    "invoice no", "invoice number", "order no", "order number", "case id", "ticket id",
    "company", "companies", "issuer", "issuers", "bidder", "bidders", "allottee", "allottees",
    "sebi", "rbi", "nse", "bse", "act", "companies act", "dated", "date", "annual report"
}

# --------------------------------------------------------------------------- #
# spaCy model
# --------------------------------------------------------------------------- #
SPACY_MODEL = "en_core_web_sm"

# --------------------------------------------------------------------------- #
# Compiled regex cache (populated lazily by regex_detector.py)
# --------------------------------------------------------------------------- #
COMPILED_PATTERNS = {k: re.compile(v, re.IGNORECASE) for k, v in REGEX_PATTERNS.items()}
