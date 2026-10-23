"""Unit tests for Pydantic v2 core schemas."""

import pytest
from pydantic import ValidationError

from src.schemas import (
    TelemetryCase,
    TrustEvaluation,
    SelectiveDecision,
    RCAResult,
)


def test_telemetry_case_valid():
    case = TelemetryCase(
        case_id="case-001",
        system="OnlineBoutique",
        metrics_data={"frontend_cpu": [0.1, 0.2, 0.3], "cartservice_mem": [10.0, 11.0, 12.0]},
        timestamps=[100, 101, 102],
        inject_time=101,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_mem",
        data_source_tag="PUBLIC_BENCHMARK",
    )
    assert case.case_id == "case-001"
    assert case.inject_time == 101
    assert case.root_cause_service == "cartservice"
    assert case.data_source_tag == "PUBLIC_BENCHMARK"


def test_telemetry_case_immutable():
    case = TelemetryCase(
        case_id="case-001",
        system="OnlineBoutique",
        metrics_data={"m1": [1.0]},
        timestamps=[100],
        inject_time=100,
        root_cause_service="cartservice",
        root_cause_indicator="m1",
    )
    with pytest.raises(ValidationError):
        # Attempt to mutate frozen model
        case.case_id = "new-id"  # type: ignore


def test_telemetry_case_invalid_missing_fields():
    with pytest.raises(ValidationError):
        TelemetryCase(
            case_id="case-001",
            # missing system, metrics_data, etc.
        )


def test_trust_evaluation_valid():
    te = TrustEvaluation(
        case_id="case-001",
        window_idx=0,
        service_scores={"cartservice": 0.95, "frontend": 0.88},
        dimensions={"completeness": 0.99, "freshness": 0.92},
    )
    assert te.service_scores["cartservice"] == 0.95
    assert te.dimensions["completeness"] == 0.99


def test_selective_decision_valid():
    decision = SelectiveDecision(
        case_id="case-001",
        service="cartservice",
        outcome="HIGH_CONFIDENCE_INCIDENT",
        anomaly_score=4.52,
        trust_score=0.94,
    )
    assert decision.outcome == "HIGH_CONFIDENCE_INCIDENT"
    assert decision.anomaly_score == 4.52


def test_selective_decision_invalid_outcome():
    with pytest.raises(ValidationError):
        SelectiveDecision(
            case_id="case-001",
            service="cartservice",
            outcome="INVALID_OUTCOME",  # type: ignore
            anomaly_score=1.0,
            trust_score=0.5,
        )


def test_rca_result_valid():
    result = RCAResult(
        case_id="case-001",
        ranked_services=["cartservice", "frontend", "paymentservice"],
        scores=[5.2, 1.1, 0.4],
        ground_truth_service="cartservice",
        hit_at_1=True,
        hit_at_3=True,
        hit_at_5=True,
        reciprocal_rank=1.0,
        runtime_ms=12.5,
    )
    assert result.hit_at_1 is True
    assert result.reciprocal_rank == 1.0
