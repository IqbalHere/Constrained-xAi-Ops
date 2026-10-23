"""Unit tests for baseline RCA algorithms (BARO and epsilon-Diagnosis)."""

import numpy as np
from src.rca.baselines import VanillaBARO, EpsilonDiagnosis
from src.schemas import TelemetryCase


def create_synthetic_incident_case() -> TelemetryCase:
    """Creates a synthetic 3-service telemetry case with an injected shift on cartservice."""
    np.random.seed(42)
    # 200 time steps: inject_time at t=100
    timestamps = list(range(1000, 1200))
    inject_time = 1100

    n_pre = 100
    n_post = 100

    # Normal services: frontend and paymentservice (stationary Gaussian noise)
    frontend_cpu = np.random.normal(loc=10.0, scale=1.0, size=200).tolist()
    paymentservice_latency = np.random.normal(loc=0.05, scale=0.005, size=200).tolist()

    # Faulty service: cartservice (shifts dramatically post-injection)
    cartservice_pre = np.random.normal(loc=20.0, scale=1.0, size=n_pre)
    cartservice_post = np.random.normal(loc=95.0, scale=2.0, size=n_post)  # Severe shift
    cartservice_cpu = np.concatenate([cartservice_pre, cartservice_post]).tolist()

    metrics = {
        "frontend_cpu_utilization": frontend_cpu,
        "paymentservice_request_latency": paymentservice_latency,
        "cartservice_cpu_utilization": cartservice_cpu,
    }

    return TelemetryCase(
        case_id="synthetic_test_case_1",
        system="OnlineBoutique",
        metrics_data=metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_cpu_utilization",
        data_source_tag="SYNTHETIC_DEMO",
    )


def test_vanilla_baro_ranks_faulty_service_at_top1():
    case = create_synthetic_incident_case()
    baro = VanillaBARO(pre_fault_buffer_sec=10, post_fault_window_sec=300)
    result = baro.localize(case)

    assert result.case_id == "synthetic_test_case_1"
    assert result.hit_at_1 is True
    assert result.ranked_services[0] == "cartservice"
    assert result.reciprocal_rank == 1.0
    assert result.runtime_ms > 0.0


def test_epsilon_diagnosis_ranks_faulty_service_at_top1():
    case = create_synthetic_incident_case()
    eps = EpsilonDiagnosis(pre_fault_buffer_sec=10, post_fault_window_sec=300)
    result = eps.localize(case)

    assert result.case_id == "synthetic_test_case_1"
    assert result.hit_at_1 is True
    assert result.ranked_services[0] == "cartservice"
    assert result.reciprocal_rank == 1.0
    assert result.runtime_ms > 0.0
