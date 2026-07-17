"""
regex_detector.py
------------------
Layer 1 of the detection pipeline: structured PII that has a predictable
shape and is best (and most precisely) caught with regular expressions:

    EMAIL, PHONE, SSN, CREDIT_CARD, IP_ADDRESS, DOB

Design notes:
    - Patterns are intentionally broad (e.g. PHONE, CREDIT_CARD) and then
      *narrowed* here with digit-count checks and contextual guards, rather
      than trying to cram every rule into the regex itself. This keeps the
      patterns in config.py readable and keeps disambiguation logic testable
      in one place.
    - A single numeric run in a document is often ambiguous between PHONE /
      CREDIT_CARD / plain-old-reference-number. `_classify_numeric` applies
      digit-count heuristics plus a look-behind context-word guard
      (config.NON_PII_NUMBER_CONTEXT_WORDS) to reduce false positives on
      order IDs, CIN numbers, page references, etc.
"""

from __future__ import annotations

from typing import List

import config
from utils import Entity, setup_logger

logger = setup_logger(__name__)


class RegexDetector:
    """Detects structured PII using compiled regular expressions."""

    def __init__(self) -> None:
        self.patterns = config.COMPILED_PATTERNS

    def detect(self, text: str) -> List[Entity]:
        entities: List[Entity] = []

        entities.extend(self._detect_simple(text, config.EntityType.EMAIL))
        entities.extend(self._detect_simple(text, config.EntityType.IP_ADDRESS))
        entities.extend(self._detect_ssn(text))
        entities.extend(self._detect_credit_card(text))
        entities.extend(self._detect_phone(text))
        entities.extend(self._detect_dob(text))

        logger.debug("Regex layer found %d entities", len(entities))
        return entities

    # ------------------------------------------------------------------ #
    # Simple, unambiguous patterns
    # ------------------------------------------------------------------ #
    def _detect_simple(self, text: str, label: str) -> List[Entity]:
        pattern = self.patterns[label]
        return [
            Entity(m.group(), label, m.start(), m.end(), source="regex", confidence=0.98)
            for m in pattern.finditer(text)
        ]

    def _detect_ssn(self, text: str) -> List[Entity]:
        pattern = self.patterns[config.EntityType.SSN]
        out = []
        for m in pattern.finditer(text):
            if self._is_flagged_as_non_pii(text, m.start()):
                continue
            out.append(Entity(m.group(), config.EntityType.SSN, m.start(), m.end(),
                               source="regex", confidence=0.95))
        return out

    # ------------------------------------------------------------------ #
    # Ambiguous numeric patterns (need digit-count + context disambiguation)
    # ------------------------------------------------------------------ #
    def _detect_credit_card(self, text: str) -> List[Entity]:
        pattern = self.patterns[config.EntityType.CREDIT_CARD]
        out = []
        for m in pattern.finditer(text):
            raw = m.group()
            digits = "".join(ch for ch in raw if ch.isdigit())
            lo, hi = config.CREDIT_CARD_DIGIT_RANGE
            if not (lo <= len(digits) <= hi):
                continue
            if not self._luhn_check(digits) and len(digits) in (13, 14, 15, 16, 17, 18, 19):
                # Not Luhn-valid: still allow 16-digit space/dash grouped
                # numbers (common in sample/test data that isn't a real
                # card), but reject long undifferentiated digit runs that
                # are almost certainly reference/tracking numbers.
                if " " not in raw and "-" not in raw:
                    continue
            if self._is_flagged_as_non_pii(text, m.start()):
                continue
            out.append(Entity(raw, config.EntityType.CREDIT_CARD, m.start(), m.end(),
                               source="regex", confidence=0.85))
        return out

    def _detect_phone(self, text: str) -> List[Entity]:
        pattern = self.patterns[config.EntityType.PHONE]
        out = []
        for m in pattern.finditer(text):
            raw = m.group()
            digits = "".join(ch for ch in raw if ch.isdigit())
            lo, hi = config.PHONE_DIGIT_RANGE
            if not (lo <= len(digits) <= hi):
                continue
            # Needs at least one separator/space/plus OR exactly 10 digits
            # (bare 10-digit Indian mobile numbers are common in the wild)
            has_separator = any(c in raw for c in " -.()") or raw.strip().startswith("+")
            if not has_separator and len(digits) != 10:
                continue
            if self._is_flagged_as_non_pii(text, m.start()):
                continue
            out.append(Entity(raw.strip(), config.EntityType.PHONE, m.start(),
                               m.start() + len(raw.strip()), source="regex", confidence=0.75))
        return out

    def _detect_dob(self, text: str) -> List[Entity]:
        """Detect date-shaped strings, then keep only ones near DOB context
        keywords (to avoid flooding a document full of unrelated dates, e.g.
        filing dates, incorporation dates, in a prospectus)."""
        pattern = self.patterns[config.EntityType.DOB]
        out = []
        for m in pattern.finditer(text):
            window_start = max(0, m.start() - 40)
            window = text[window_start:m.start()].lower()
            if any(kw in window for kw in config.DOB_CONTEXT_KEYWORDS):
                out.append(Entity(m.group(), config.EntityType.DOB, m.start(), m.end(),
                                   source="regex", confidence=0.9))
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_flagged_as_non_pii(text: str, match_start: int) -> bool:
        if config.REDACT_NON_PII_IDENTIFIERS:
            return False
        window_start = max(0, match_start - 25)
        window = text[window_start:match_start].lower()
        return any(word in window for word in config.NON_PII_NUMBER_CONTEXT_WORDS)

    @staticmethod
    def _luhn_check(digits: str) -> bool:
        if len(digits) not in (13, 14, 15, 16, 17, 18, 19):
            return False
        total = 0
        reversed_digits = digits[::-1]
        for i, ch in enumerate(reversed_digits):
            d = int(ch)
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        return total % 10 == 0
