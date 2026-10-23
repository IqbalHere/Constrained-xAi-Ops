"""Unit tests for Operator Feedback Store and Online Threshold Recalibrator."""

import tempfile
from pathlib import Path
import pytest

from src.feedback.recalibrator import OnlineThresholdRecalibrator
from src.feedback.store import FeedbackStore


def test_feedback_store_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = str(Path(tmpdir) / "test_feedback.jsonl")
        store = FeedbackStore(storage_path=store_path)

        assert store.count() == 0

        # Add records
        r1 = store.add_feedback("case-1", "cartservice", "CONFIRM_RCA", trust_score=0.92, anomaly_score=0.88)
        r2 = store.add_feedback("case-2", "frontend", "FALSE_POSITIVE", trust_score=0.45, anomaly_score=0.38)
        r3 = store.add_feedback("case-3", "checkoutservice", "CONFIRM_MNAR_CRASH", trust_score=0.52, anomaly_score=0.15)

        assert store.count() == 3
        all_recs = store.get_all_feedback()
        assert len(all_recs) == 3
        assert all_recs[0]["case_id"] == "case-1"
        assert all_recs[1]["verdict"] == "FALSE_POSITIVE"
        assert all_recs[2]["verdict"] == "CONFIRM_MNAR_CRASH"

        store.clear()
        assert store.count() == 0


def test_online_recalibrator_updates():
    recalibrator = OnlineThresholdRecalibrator(
        initial_tau_T=0.80,
        initial_tau_A=0.35,
        initial_lambda_mnar=3.5,
    )

    # 1. FALSE_POSITIVE -> should raise tau_T and tau_A
    state1 = recalibrator.step(verdict="FALSE_POSITIVE", trust_score=0.40, anomaly_score=0.40)
    assert state1["tau_T"] > 0.80
    assert state1["tau_A"] > 0.35
    assert state1["step"] == 1

    # 2. CONFIRM_MNAR_CRASH -> should boost lambda_mnar
    old_lambda = recalibrator.lambda_mnar
    state2 = recalibrator.step(verdict="CONFIRM_MNAR_CRASH", trust_score=0.50, anomaly_score=0.10)
    assert state2["lambda_mnar"] > old_lambda

    # 3. Batch processing respects bounds
    batch = [
        {"verdict": "FALSE_POSITIVE", "trust_score": 0.2, "anomaly_score": 0.5} for _ in range(50)
    ]
    final_state = recalibrator.process_batch(batch)
    assert final_state["tau_T"] <= 0.95
    assert final_state["tau_A"] <= 0.60
