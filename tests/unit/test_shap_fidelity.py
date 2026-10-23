"""Unit tests for Missingness-Aware TreeSHAP and Explanation Fidelity."""

import numpy as np
import pytest

from src.explainability.fidelity import (
    compute_fidelity_at_k,
    compute_jaccard_at_k,
    evaluate_explanation_fidelity,
    match_indicator,
)
from src.explainability.shap_explainer import (
    MissingnessAwareSHAPExplainer,
    compute_gini_index,
)
from src.schemas import TelemetryCase


def create_synthetic_shap_case() -> tuple[TelemetryCase, np.ndarray]:
    """Creates a synthetic case with cartservice having cpu and memory metrics."""
    rng = np.random.default_rng(42)
    T = 150
    timestamps = list(range(1000, 1000 + T))
    inject_time = 1080

    # cartservice metrics: CPU spikes post-fault, memory stays stationary
    cpu_pre = rng.normal(20.0, 1.0, size=80)
    cpu_post = rng.normal(85.0, 2.0, size=70)
    cart_cpu = np.concatenate([cpu_pre, cpu_post]).tolist()

    mem_pre = rng.normal(40.0, 1.0, size=80)
    mem_post = rng.normal(41.0, 1.0, size=70)
    cart_mem = np.concatenate([mem_pre, mem_post]).tolist()

    metrics = {
        "cartservice_cpu_utilization": cart_cpu,
        "cartservice_memory_working_set": cart_mem,
    }

    # Mask: 40% post-fault points missing in CPU
    mask = np.ones((T, 2), dtype=np.uint8)
    drop_indices = rng.choice(np.arange(80, 150), size=28, replace=False)
    mask[drop_indices, 0] = 0

    case = TelemetryCase(
        case_id="shap_test_case",
        system="OnlineBoutique",
        metrics_data=metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cpu",
        data_source_tag="SYNTHETIC_DEMO",
    )

    return case, mask


def test_missingness_aware_shap_explainer():
    case, mask = create_synthetic_shap_case()
    explainer = MissingnessAwareSHAPExplainer(mode="constrained_xaiops", seed=42)

    res = explainer.explain_service("cartservice", case, mask=mask)

    assert res["service"] == "cartservice"
    assert "metric_attributions" in res
    assert len(res["ranked_metrics"]) == 2
    # Attributions sum to approximately 1.0
    total_attr = sum(res["metric_attributions"].values())
    assert abs(total_attr - 1.0) < 1e-4

    # CPU was the true spike -> should rank #1
    assert res["ranked_metrics"][0] == "cartservice_cpu_utilization"
    # Gini sparsity in [0, 1]
    assert 0.0 <= res["gini_sparsity"] <= 1.0
    # Reliability score in [0, 1]
    assert 0.0 <= res["reliability_score"] <= 1.0


def test_explanation_fidelity_and_stability():
    case, mask = create_synthetic_shap_case()
    explainer = MissingnessAwareSHAPExplainer(mode="constrained_xaiops", seed=42)

    res_corrupt = explainer.explain_service("cartservice", case, mask=mask)
    res_oracle = explainer.explain_service("cartservice", case, mask=None)

    fidelity = evaluate_explanation_fidelity(res_corrupt, res_oracle, gt_indicator="cpu")

    assert fidelity["fidelity_at_1"] == 1.0
    assert fidelity["fidelity_at_3"] == 1.0
    assert 0.0 <= fidelity["jaccard_at_3"] <= 1.0
    assert 0.0 <= fidelity["gini_sparsity"] <= 1.0


def test_indicator_matching():
    assert match_indicator("cartservice_cpu_utilization", "cpu") is True
    assert match_indicator("cartservice_memory_working_set", "mem") is True
    assert match_indicator("frontend_request_latency", "latency") is True
    assert match_indicator("paymentservice_network_rx", "net") is True
    assert match_indicator("frontend_cpu", "disk") is False
