"""
ner_detector.py
----------------
Layer 2 of the detection pipeline: free-text PII that has no fixed shape and
requires contextual language understanding — names, organizations, and
addresses. Uses spaCy's statistical NER model.

Labels consumed from spaCy (see config.SPACY_LABEL_MAP):
    PERSON          -> PERSON
    ORG             -> ORG
    GPE / LOC / FAC -> ADDRESS (components; adjacent components are merged
                        into a single ADDRESS span by `_merge_address_runs`)

Filtering:
    - `config.ORG_STOPLIST` / `PERSON_STOPLIST` drop common regulatory
      acronyms (SEBI, RBI, GST...) that spaCy sometimes mis-tags as
      ORG/PERSON in dense financial/legal text.
    - Single-token ALL-CAPS "words" that are pure section headers (e.g.
      "ANNEXURE") are filtered via a light heuristic.
"""

from __future__ import annotations

from typing import List

import spacy

import config
from utils import Entity, setup_logger

logger = setup_logger(__name__)


class NERDetector:
    """Detects PERSON / ORG / ADDRESS entities using spaCy NER."""

    def __init__(self, model_name: str = config.SPACY_MODEL) -> None:
        try:
            # Disable unused pipeline components to save memory and CPU on cloud hosts
            self.nlp = spacy.load(
                model_name,
                disable=["tagger", "parser", "attribute_ruler", "lemmatizer"]
            )
        except OSError as exc:
            raise RuntimeError(
                f"spaCy model '{model_name}' is not installed. "
                f"Run: python -m spacy download {model_name}"
            ) from exc
        # Docs can be long (multi-page reports); raise the length ceiling.
        self.nlp.max_length = 3_000_000

    def detect(self, text: str) -> List[Entity]:
        entities: List[Entity] = []
        doc = self.nlp(text)

        raw_address_spans = []
        for ent in doc.ents:
            label = config.SPACY_LABEL_MAP.get(ent.label_)
            if label is None:
                continue

            if label == config.EntityType.PERSON:
                if ent.text.strip().lower() in config.PERSON_STOPLIST:
                    continue
                if not self._looks_like_name(ent.text):
                    continue
                if self._is_generic_single_token_person(ent.text):
                    continue
                entities.append(Entity(ent.text, label, ent.start_char, ent.end_char,
                                        source="ner", confidence=0.85))

            elif label == config.EntityType.ORG:
                if ent.text.strip().lower() in config.ORG_STOPLIST:
                    continue
                if len(ent.text.strip()) < 2:
                    continue
                if self._is_untrusted_allcaps_heading(ent.text):
                    continue
                if self._is_generic_single_token_person(ent.text):
                    # The stoplist ("board", "offer", "company"...) covers
                    # generic vocabulary that spaCy mis-tags as ORG just as
                    # often as PERSON in this kind of document.
                    continue
                if self._is_reference_label(ent.text):
                    continue
                entities.append(Entity(ent.text, label, ent.start_char, ent.end_char,
                                        source="ner", confidence=0.75))

            elif label == config.EntityType.ADDRESS:
                raw_address_spans.append((ent.start_char, ent.end_char, ent.text))

        entities.extend(self._merge_address_runs(text, raw_address_spans))

        logger.debug("NER layer found %d entities", len(entities))
        return entities

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _looks_like_name(text: str) -> bool:
        """Reject spaCy PERSON hits that are clearly not human names, e.g.
        stray single lowercase words or pure punctuation artifacts from OCR
        tables."""
        stripped = text.strip()
        if len(stripped) < 2:
            return False
        if not any(ch.isalpha() for ch in stripped):
            return False
        return True

    @staticmethod
    def _is_generic_single_token_person(text: str) -> bool:
        """Reject single-word PERSON hits that are common generic legal/
        financial vocabulary ("Board", "Offer") rather than a name. Multi-
        word candidates (typical "First Last" names) are never rejected
        here."""
        tokens = text.strip().split()
        if len(tokens) != 1:
            return False
        return tokens[0].lower() in config.PERSON_SINGLE_TOKEN_STOPLIST

    @staticmethod
    def _is_untrusted_allcaps_heading(text: str) -> bool:
        """ALL-CAPS spans in legal/financial documents are frequently
        section headings (DEFINITIONS, CURRENCY, RISK FACTORS) rather than
        organization names, and spaCy tags both the same way. Only trust an
        ALL-CAPS ORG candidate if it contains a recognizable company/legal
        suffix (LIMITED, LLP, BANK, ...); mixed/title-case candidates are
        left untouched since they are far less likely to be headings."""
        stripped = text.strip()
        if not stripped.isupper():
            return False
        lowered = stripped.lower()
        return not any(kw in lowered for kw in config.ORG_SUFFIX_KEYWORDS)

    @staticmethod
    def _is_reference_label(text: str) -> bool:
        lowered = text.strip().lower()
        return any(lowered.startswith(p) for p in config.ORG_REFERENCE_LABEL_PREFIXES)

    @staticmethod
    def _merge_address_runs(text: str, spans: list[tuple[int, int, str]]) -> List[Entity]:
        """GPE/LOC/FAC tokens that sit close together (e.g. 'Pune', '--',
        '410 501', 'Maharashtra') usually form one physical address in
        source text. Merge spans that are within a short character gap of
        each other into a single ADDRESS entity so redaction reads
        naturally, instead of replacing each city/state token separately.
        """
        if not spans:
            return []
        spans = sorted(spans)
        merged: List[Entity] = []
        cur_start, cur_end, _ = spans[0]

        MAX_GAP = 12  # characters allowed between adjacent components

        for start, end, _ in spans[1:]:
            gap_text = text[cur_end:start]
            if start - cur_end <= MAX_GAP and "\n\n" not in gap_text:
                cur_end = max(cur_end, end)
            else:
                merged.append(Entity(text[cur_start:cur_end], config.EntityType.ADDRESS,
                                      cur_start, cur_end, source="ner", confidence=0.6))
                cur_start, cur_end = start, end
        merged.append(Entity(text[cur_start:cur_end], config.EntityType.ADDRESS,
                              cur_start, cur_end, source="ner", confidence=0.6))
        return merged
