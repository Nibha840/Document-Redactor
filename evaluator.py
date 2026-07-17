"""
evaluator.py
------------
Computes precision / recall / F1 / accuracy for the detection pipeline
against a ground-truth annotation file, and writes:

    reports/evaluation_report.csv   (per-entity-type metrics table)
    reports/evaluation_report.md    (human-readable summary)

Ground truth format (JSON):
    [
      {"text": "Rohan Dey", "label": "PERSON"},
      {"text": "rohan.dey@gmail.com", "label": "EMAIL"},
      ...
    ]

Matching strategy:
    A predicted entity is a True Positive for a ground-truth item if they
    share the same label and the predicted text, normalized, either exactly
    matches or contains/​is-contained-by the ground truth text (handles
    minor boundary differences, e.g. NER including/excluding a title like
    "Mr."). Each ground-truth item can be matched at most once.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from utils import Entity, normalize_key, setup_logger

logger = setup_logger(__name__)


@dataclass
class EntityMetrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


class Evaluator:
    """Compares detected entities against a ground-truth annotation file."""

    def __init__(self) -> None:
        self.metrics: dict[str, EntityMetrics] = {}

    def load_ground_truth(self, path: str) -> List[dict]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    def evaluate(self, predicted: List[Entity], ground_truth: List[dict]) -> dict:
        gt_remaining = [dict(g, matched=False) for g in ground_truth]
        self.metrics = {}

        def metrics_for(label: str) -> EntityMetrics:
            return self.metrics.setdefault(label, EntityMetrics())

        # Match predictions -> ground truth (greedy, one-to-one)
        for pred in predicted:
            match = self._find_match(pred, gt_remaining)
            m = metrics_for(pred.label)
            if match is not None:
                match["matched"] = True
                m.tp += 1
            else:
                m.fp += 1

        # Anything left unmatched in ground truth is a false negative
        for g in gt_remaining:
            if not g["matched"]:
                metrics_for(g["label"]).fn += 1

        return self.metrics

    @staticmethod
    def _find_match(pred: Entity, gt_remaining: List[dict]) -> dict | None:
        pred_key = normalize_key(pred.text, pred.label)
        for g in gt_remaining:
            if g["matched"] or g["label"] != pred.label:
                continue
            gt_key = normalize_key(g["text"], g["label"])
            if pred_key == gt_key or gt_key in pred_key or pred_key in gt_key:
                return g
        return None

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #
    def overall_accuracy(self) -> float:
        total_tp = sum(m.tp for m in self.metrics.values())
        total_fp = sum(m.fp for m in self.metrics.values())
        total_fn = sum(m.fn for m in self.metrics.values())
        denom = total_tp + total_fp + total_fn
        return total_tp / denom if denom else 0.0

    def write_reports(self, csv_path: str, md_path: str) -> None:
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Entity Type", "TP", "FP", "FN", "Precision", "Recall", "F1"])
            for label in sorted(self.metrics):
                m = self.metrics[label]
                writer.writerow([label, m.tp, m.fp, m.fn,
                                  f"{m.precision:.3f}", f"{m.recall:.3f}", f"{m.f1:.3f}"])
            total_tp = sum(m.tp for m in self.metrics.values())
            total_fp = sum(m.fp for m in self.metrics.values())
            total_fn = sum(m.fn for m in self.metrics.values())
            overall = EntityMetrics(total_tp, total_fp, total_fn)
            writer.writerow(["OVERALL", total_tp, total_fp, total_fn,
                              f"{overall.precision:.3f}", f"{overall.recall:.3f}",
                              f"{overall.f1:.3f}"])

        lines = ["# PII Redaction — Evaluation Report", ""]
        lines.append(f"**Overall accuracy (micro TP / (TP+FP+FN)):** "
                      f"{self.overall_accuracy():.3f}")
        lines.append("")
        lines.append("| Entity Type | TP | FP | FN | Precision | Recall | F1 |")
        lines.append("|---|---|---|---|---|---|---|")
        for label in sorted(self.metrics):
            m = self.metrics[label]
            lines.append(f"| {label} | {m.tp} | {m.fp} | {m.fn} | "
                          f"{m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} |")
        total_tp = sum(m.tp for m in self.metrics.values())
        total_fp = sum(m.fp for m in self.metrics.values())
        total_fn = sum(m.fn for m in self.metrics.values())
        overall = EntityMetrics(total_tp, total_fp, total_fn)
        lines.append(f"| **OVERALL** | {total_tp} | {total_fp} | {total_fn} | "
                      f"**{overall.precision:.3f}** | **{overall.recall:.3f}** | "
                      f"**{overall.f1:.3f}** |")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        logger.info("Evaluation reports written: %s, %s", csv_path, md_path)
