"""Unit tests for Telemetry Trust Score, dimensions, and weight sensitivity."""

import numpy as np
import pandas as pd
import pytest

from src.missingness.generator import MissingnessGenerator, apply_stale_freeze, apply_tag_corruption
from src.quality.dimensions import compute_all_dimensions
from src.quality.trust_score import TelemetryTrustEvaluator
from src.quality.weights import (
    calibrate_logistic_weights,
    get_equal_weights,
    run_dirichlet_sensitivity,
)
from src.schemas import TelemetryCase


def create_baseline_case() -> TelemetryCase:
    """Creates a clean test case with valid Online Boutique services and timestamps."""
    rng = np.random.default_rng(999)
    T = 200
    timestamps = list(range(1000, 1000 + T))
    inject_time = 1100

    metrics = {
        "frontend_cpu": rng.normal(10.0, 1.0, size=T).tolist(),
        "frontend_latency": rng.normal(0.05, 0.005, size=T).tolist(),
        "cartservice_cpu": rng.normal(20.0, 2.0, size=T).tolist(),
        "cartservice_mem": rng.normal(100.0, 5.0, size=T).tolist(),
    }

    return TelemetryCase(
        case_id="trust_test_01",
        system="OnlineBoutique",
        metrics_data=metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_cpu",
        data_source_tag="SYNTHETIC_DEMO",
    )


def test_dimensions_strict_bounds():
    """All 5 dimensions (C, L, S, V, Q) must fall strictly inside [0.0, 1.0]."""
    case = create_baseline_case()
    gen = MissingnessGenerator(seed=42)
    df = pd.DataFrame(case.metrics_data)
    T, M = df.shape

    mask = gen.generate_mcar_mask((T, M), p_miss=0.3)
    data_mat = df.values.astype(float)

    dims = compute_all_dimensions(
        mask=mask,
        metrics_data=data_mat,
        columns=list(df.columns),
        timestamps=case.timestamps,
        pre_fault_cutoff=100,
    )

    for dim_name in ["C", "L", "S", "V", "Q"]:
        vals = dims[dim_name]
        assert np.all(vals >= 0.0), f"{dim_name} has values < 0"
        assert np.all(vals <= 1.0), f"{dim_name} has values > 1"


def test_multiplicative_floor_on_zero_validity_or_completeness():
    """V=0 or C=0 forces composite metric trust score to 0.0."""
    evaluator = TelemetryTrustEvaluator()
    case = create_baseline_case()
    df = pd.DataFrame(case.metrics_data)
    T, M = df.shape

    # 1. Total missingness on column 0 -> C=0
    mask_c0 = np.ones((T, M), dtype=np.uint8)
    mask_c0[:, 0] = 0

    eval_c0 = evaluator.evaluate_case(case, mask=mask_c0)
    # Service frontend should have degraded score, and specifically the metric has 0.0
    scores, dims = evaluator.evaluate_metric_scores(
        mask=mask_c0,
        metrics_data=df.values,
        columns=list(df.columns),
        timestamps=case.timestamps,
        pre_fault_cutoff=100,
    )
    assert scores[0] == 0.0, "C=0 must force metric score to 0.0"

    # 2. Corrupt tag -> V=0
    corrupted_cols = ["corrupted_cpu", "frontend_latency", "cartservice_cpu", "cartservice_mem"]
    scores_v0, _ = evaluator.evaluate_metric_scores(
        mask=np.ones((T, M), dtype=np.uint8),
        metrics_data=df.values,
        columns=corrupted_cols,
        timestamps=case.timestamps,
        pre_fault_cutoff=100,
    )
    assert scores_v0[0] == 0.0, "V=0 (corrupted schema) must force metric score to 0.0"


def test_monotonic_trust_degradation():
    """T_sys strictly decreases as missingness rate increases."""
    evaluator = TelemetryTrustEvaluator()
    case = create_baseline_case()
    gen = MissingnessGenerator(seed=42)
    df = pd.DataFrame(case.metrics_data)
    T, M = df.shape

    prev_score = 2.0
    for p_miss in [0.0, 0.2, 0.4, 0.8]:
        mask = gen.generate_mcar_mask((T, M), p_miss=p_miss)
        result = evaluator.evaluate_case(case, mask=mask)
        curr_score = result.dimensions["T_sys"]
        assert curr_score <= prev_score + 1e-4, f"Score increased at p_miss={p_miss}: {curr_score} > {prev_score}"
        prev_score = curr_score


def test_stale_freeze_detection():
    """apply_stale_freeze must drop timeliness L(m, w) significantly even when completeness is 1.0."""
    evaluator = TelemetryTrustEvaluator()
    case = create_baseline_case()
    df = pd.DataFrame(case.metrics_data)

    # Freeze cartservice for 60 steps
    frozen_df, freeze_mask = apply_stale_freeze(df, service="cartservice", start_idx=50, duration=60)
    all_ones_mask = np.ones(df.shape, dtype=np.uint8)  # Completeness is 100%!

    scores, dims = evaluator.evaluate_metric_scores(
        mask=all_ones_mask,
        metrics_data=frozen_df.values,
        columns=list(df.columns),
        timestamps=case.timestamps,
        pre_fault_cutoff=100,
    )

    # Cartservice columns are indices 2 and 3
    cart_timeliness_1 = dims["L"][2]
    cart_timeliness_2 = dims["L"][3]
    frontend_timeliness = dims["L"][0]

    assert dims["C"][2] == 1.0, "Completeness should be 1.0"
    assert cart_timeliness_1 < 0.85, f"Timeliness L should drop significantly due to freeze, got {cart_timeliness_1}"
    assert cart_timeliness_2 < 0.85, f"Timeliness L should drop significantly due to freeze, got {cart_timeliness_2}"
    assert frontend_timeliness > cart_timeliness_1


def test_dirichlet_sensitivity():
    """Dirichlet sensitivity analysis must sample 100 valid simplex vectors."""
    dims_dict = {"C": 0.8, "L": 0.9, "S": 0.85, "V": 1.0, "Q": 0.75}
    res = run_dirichlet_sensitivity(dims_dict, n_draws=100, seed=42)

    assert res["n_draws"] == 100.0
    assert 0.0 <= res["mean_score"] <= 1.0
    assert 0.0 <= res["min_score"] <= res["max_score"] <= 1.0
    assert res["iqr_score"] >= 0.0


def test_logistic_weight_calibration():
    """Logistic calibration returns normalized positive weights summing to 1.0."""
    rng = np.random.default_rng(42)
    # Synthetic dimension observations (N=50, 5)
    X = rng.uniform(0.2, 1.0, size=(50, 5))
    # Labels correlate heavily with dimension 0 (C) and dimension 4 (Q)
    y = ((X[:, 0] > 0.6) & (X[:, 4] > 0.6)).astype(int)

    weights = calibrate_logistic_weights(X, y)
    assert len(weights) == 5
    assert np.all(weights >= 0.0)
    assert np.isclose(np.sum(weights), 1.0)
