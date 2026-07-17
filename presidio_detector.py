"""
presidio_detector.py
--------------------
Layer 3 of the detection pipeline: Microsoft Presidio Analyzer.
Provides robust context-aware PII detection, complementing Regex and spaCy NER.

We map Presidio entity types to our internal EntityType representations.
For dates, we apply the same context-check heuristic to avoid redacting non-birth dates.
"""

from __future__ import annotations

from typing import List

from presidio_analyzer import AnalyzerEngine

import config
from utils import Entity, setup_logger

logger = setup_logger(__name__)


class PresidioDetector:
    """Detects PII using the Microsoft Presidio Analyzer."""

    def __init__(self) -> None:
        try:
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            # Use lightweight en_core_web_sm to prevent RAM exhaustion (OOM) on free cloud tiers
            provider_config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
            }
            provider = NlpEngineProvider(nlp_configuration=provider_config)
            nlp_engine = provider.create_engine()
            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        except Exception as exc:
            logger.error("Failed to initialize Microsoft Presidio Analyzer Engine: %s", exc)
            raise RuntimeError("Presidio Analyzer initialization failed.") from exc

    def detect(self, text: str) -> List[Entity]:
        if not text or not text.strip():
            return []

        try:
            results = self.analyzer.analyze(text=text, language="en")
        except Exception as exc:
            logger.error("Presidio analyze error: %s", exc)
            return []

        entities: List[Entity] = []

        for res in results:
            label = config.PRESIDIO_LABEL_MAP.get(res.entity_type)
            if label is None:
                continue

            matched_text = text[res.start:res.end]

            # Specific guard for DOB: Date-Time should only be redacted if it is actually a DOB
            if label == config.EntityType.DOB:
                window_start = max(0, res.start - 40)
                window = text[window_start:res.start].lower()
                if not any(kw in window for kw in config.DOB_CONTEXT_KEYWORDS):
                    continue

            # Standard context stoplist / false-positive guards for numbers
            if label in (config.EntityType.CREDIT_CARD, config.EntityType.PHONE, config.EntityType.SSN):
                # Check for context keywords indicating a ticket ID, order ID, etc.
                window_start = max(0, res.start - 25)
                window = text[window_start:res.start].lower()
                if not config.REDACT_NON_PII_IDENTIFIERS:
                    if any(word in window for word in config.NON_PII_NUMBER_CONTEXT_WORDS):
                        continue

            entities.append(
                Entity(
                    text=matched_text,
                    label=label,
                    start=res.start,
                    end=res.end,
                    source="presidio",
                    confidence=res.score
                )
            )

        logger.debug("Presidio layer found %d entities", len(entities))
        return entities
