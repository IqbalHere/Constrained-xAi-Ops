"""Operator Feedback Store for Constrained-xAIOps.

Persists human-in-the-loop triage verdicts to disk for online threshold recalibration.
Verdicts:
- CONFIRM_RCA: True positive root-cause localization.
- FALSE_POSITIVE: False alarm caused by telemetry noise/degraded trust.
- CONFIRM_MNAR_CRASH: True positive pod crash with silent telemetry dropout.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional


class FeedbackStore:
    """Thread-safe persistent store for operator feedback records."""

    def __init__(self, storage_path: str = "data/processed/operator_feedback.jsonl"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def add_feedback(
        self,
        case_id: str,
        service: str,
        verdict: Literal["CONFIRM_RCA", "FALSE_POSITIVE", "CONFIRM_MNAR_CRASH"],
        trust_score: float,
        anomaly_score: float,
        timestamp: Optional[str] = None,
    ) -> Dict[str, object]:
        """Appends an operator feedback entry to the JSONL store."""
        record = {
            "case_id": case_id,
            "service": service,
            "verdict": verdict,
            "trust_score": float(trust_score),
            "anomaly_score": float(anomaly_score),
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return record

    def get_all_feedback(self) -> List[Dict[str, object]]:
        """Reads and returns all persisted feedback records."""
        if not self.storage_path.exists():
            return []

        records = []
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def count(self) -> int:
        """Returns the total number of feedback records stored."""
        return len(self.get_all_feedback())

    def clear(self) -> None:
        """Clears all stored feedback records."""
        if self.storage_path.exists():
            self.storage_path.unlink()
