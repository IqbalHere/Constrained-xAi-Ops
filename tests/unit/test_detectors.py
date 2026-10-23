"""Unit tests for Lightweight Anomaly Detection Suite.

Verifies RobustZScoreDetector, IsolationForestDetector, and MultivariateBOCPDDetector:
1. Output scores strictly bounded in [0.0, 1.0].
2. Accurately assign a higher anomaly score to anomalous service vs. stationary normal services.
"""

import numpy as np
import pytest

from src.detection.bocpd import MultivariateBOCPDDetector
from src.detection.isolation_forest import IsolationForestDetector
from src.detection.statistical import RobustZScoreDetector
from src.schemas import TelemetryCase


def create_detector_test_case() -> TelemetryCase:
    """Creates a deterministic synthetic case with 3 services where cartservice spikes."""
    rng = np.random.default_rng(42)
    T = 200
    timestamps = list(range(1000, 1000 + T))
    inject_time = 1100  # Step 100

    # Normal services: frontend and paymentservice (stationary noise)
    frontend_cpu = rng.normal(loc=15.0, scale=1.0, size=T).tolist()
    frontend_lat = rng.normal(loc=0.05, scale=0.005, size=T).tolist()
    payment_mem = rng.normal(loc=40.0, scale=2.0, size=T).tolist()

    # Faulty service: cartservice (shifts dramatically from 20 to 95 after inject_time)
    cart_pre = rng.normal(loc=20.0, scale=1.0, size=100)
    cart_post = rng.normal(loc=95.0, scale=2.0, size=100)
    cart_cpu = np.concatenate([cart_pre, cart_post]).tolist()

    metrics = {
        "frontend_cpu": frontend_cpu,
        "frontend_latency": frontend_lat,
        "paymentservice_mem": payment_mem,
        "cartservice_cpu": cart_cpu,
    }

    return TelemetryCase(
        case_id="detector_test_case_1",
        system="OnlineBoutique",
        metrics_data=metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_cpu",
        data_source_tag="SYNTHETIC_DEMO",
    )


def test_robust_zscore_detector_bounds_and_ranking():
    case = create_detector_test_case()
    detector = RobustZScoreDetector(pre_fault_buffer_sec=10, post_fault_window_sec=300)
    scores = detector.detect(case)

    # Check bounds [0.0, 1.0]
    for s, score in scores.items():
        assert 0.0 <= score <= 1.0, f"Score for {s} out of bounds: {score}"

    # Faulty service cartservice must have high anomaly score
    assert scores["cartservice"] > 0.80
    # Normal services must have significantly lower anomaly scores
    assert scores["cartservice"] > scores["frontend"]
    assert scores["cartservice"] > scores["paymentservice"]


def test_isolation_forest_detector_bounds_and_ranking():
    case = create_detector_test_case()
    detector = IsolationForestDetector(seed=42, pre_fault_buffer_sec=10, post_fault_window_sec=300)
    scores = detector.detect(case)

    for s, score in scores.items():
        assert 0.0 <= score <= 1.0, f"Score for {s} out of bounds: {score}"

    # Faulty service cartservice must score highest
    assert scores["cartservice"] > scores["frontend"]
    assert scores["cartservice"] > scores["paymentservice"]


def test_bocpd_detector_bounds_and_ranking():
    case = create_detector_test_case()
    detector = MultivariateBOCPDDetector(pre_fault_buffer_sec=10, post_fault_window_sec=300)
    scores = detector.detect(case)

    for s, score in scores.items():
        assert 0.0 <= score <= 1.0, f"Score for {s} out of bounds: {score}"

    # Faulty service cartservice must score highest
    assert scores["cartservice"] > 0.80
    assert scores["cartservice"] > scores["frontend"]
    assert scores["cartservice"] > scores["paymentservice"]
