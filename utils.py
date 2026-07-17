"""
utils.py
--------
Shared data structures and helper functions used across the detection and
redaction pipeline:

    - `Entity`         : a single detected PII span
    - `merge_entities`  : overlap-resolution across regex / NER detectors
    - `setup_logger`    : consistent logging configuration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List


def setup_logger(name: str = "pii_redactor", level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger that writes to stdout with a compact format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger


@dataclass
class Entity:
    """A single detected PII span within a piece of text.

    Attributes:
        text: The exact substring detected.
        label: Internal entity type (see config.EntityType).
        start: Character offset (inclusive) within the source text.
        end: Character offset (exclusive) within the source text.
        source: Which detector layer produced this ("regex", "ner").
        confidence: Rough confidence score, used to break ties on overlap.
    """
    text: str
    label: str
    start: int
    end: int
    source: str
    confidence: float = 1.0

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)

    def overlaps(self, other: "Entity") -> bool:
        return self.start < other.end and other.start < self.end

    def __len__(self) -> int:
        return self.end - self.start


# Source/label priority used only to break ties when two entities cover the
# *exact* same span. Regex is generally more precise for structured PII
# (email/phone/ssn/card/ip/date); NER is more precise for free-text names,
# organizations, and locations.
_LABEL_PRIORITY = {
    "EMAIL": 3, "SSN": 3, "CREDIT_CARD": 3, "IP_ADDRESS": 3, "DOB": 2,
    "PHONE": 2, "PERSON": 2, "ORG": 1, "ADDRESS": 1,
}


def merge_entities(entities: List[Entity]) -> List[Entity]:
    """Resolve overlapping spans from multiple detectors into a single
    non-overlapping list.

    Strategy:
        1. Sort by span length (longer spans win — e.g. a full address
           beats a single GPE token inside it) then by priority/confidence.
        2. Greedily accept entities that do not overlap anything already
           accepted.
    """
    if not entities:
        return []

    ranked = sorted(
        entities,
        key=lambda e: (len(e), _LABEL_PRIORITY.get(e.label, 0), e.confidence),
        reverse=True,
    )

    accepted: List[Entity] = []
    for candidate in ranked:
        if not any(candidate.overlaps(a) for a in accepted):
            accepted.append(candidate)

    accepted.sort(key=lambda e: e.start)
    return accepted


def normalize_key(text: str, label: str) -> str:
    """Normalize an entity's surface text into a stable dictionary key so the
    *same* real-world value always maps to the *same* fake value, even if it
    appears with different casing/whitespace across the document.
    """
    collapsed = " ".join(text.split())
    if label in ("EMAIL",):
        return collapsed.lower()
    if label in ("PHONE", "SSN", "CREDIT_CARD"):
        return "".join(ch for ch in collapsed if ch.isdigit())
    return collapsed.lower()
