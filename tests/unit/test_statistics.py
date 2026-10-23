"""Unit tests for Evaluation Metrics and Statistical Testing Suite."""

import numpy as np
import pytest

from src.evaluation.metrics_rca import compute_rca_metrics
from src.evaluation.metrics_selective import (
    compute_expected_calibration_error,
    compute_selective_metrics,
)
from src.evaluation.metrics_tsad import (
    compare_vus_pr_vs_paf1,
    compute_detection_delay,
    compute_faph,
    compute_point_adjusted_f1,
    compute_range_auc_pr,
    compute_vus_pr,
)
from src.evaluation.statistics import (
    compute_bootstrap_ci,
    compute_cliffs_delta,
    holm_bonferroni_correction,
    run_friedman_test,
    run_paired_wilcoxon_test,
)
from src.schemas import RCAResult


def test_vus_pr_and_paf1_comparison():
    res = compare_vus_pr_vs_paf1(n_points=300, anomaly_start=150, anomaly_end=200, noise_seed=42)

    assert "paf1_inflated_score" in res
    assert "vus_pr_score" in res
    assert "inflation_gap" in res
    # PA-F1 inflates the score significantly compared to VUS-PR
    assert res["inflation_gap"] > 0.0
    assert res["paf1_inflated_score"] >= res["vus_pr_score"]


def test_rca_retrieval_rerank_metrics():
    # Synthetic RCA results
    results = [
        RCAResult(
            case_id=f"c_{i}",
            ranked_services=["s1", "s2", "s3", "s4", "s5"],
            scores=[0.9, 0.8, 0.7, 0.6, 0.5],
            ground_truth_service="s1" if i < 6 else ("s3" if i < 9 else "s8"),
            hit_at_1=(i < 6),
            hit_at_3=(i < 9),
            hit_at_5=(i < 9),
            reciprocal_rank=1.0 if i < 6 else (1.0 / 3.0 if i < 9 else 1.0 / 8.0),
            runtime_ms=5.0,
        )
        for i in range(10)
    ]

    metrics = compute_rca_metrics(results, num_total_services=10)

    assert metrics["AC@1"] == 0.60
    assert metrics["AC@3"] == 0.90
    assert metrics["AC@5"] == 0.90
    assert metrics["Retrieval@5"] == 0.90
    # Rerank@1 = AC@1 / AC@5 = 0.6 / 0.9 = 0.6667
    assert abs(metrics["Rerank@1"] - (0.60 / 0.90)) < 1e-3
    assert metrics["Lift@5"] == 0.40  # 0.90 - 0.50


def test_statistical_significance_tests():
    # Two paired distributions: A strictly dominates B
    a = [0.8, 0.9, 0.85, 0.95, 0.75, 0.88, 0.92, 0.84, 0.91, 0.87]
    b = [0.2, 0.3, 0.25, 0.35, 0.15, 0.28, 0.32, 0.24, 0.31, 0.27]

    # 1. Wilcoxon test
    w_res = run_paired_wilcoxon_test(a, b)
    assert w_res["p_value"] < 0.01

    # 2. Cliff's Delta
    delta, mag = compute_cliffs_delta(a, b)
    assert delta == 1.0
    assert mag == "large"

    # 3. Bootstrap CI
    mean, ci_lo, ci_hi = compute_bootstrap_ci(a, n_boot=500)
    assert ci_lo <= mean <= ci_hi

    # 4. Friedman test
    c = [0.5, 0.6, 0.55, 0.65, 0.45, 0.58, 0.62, 0.54, 0.61, 0.57]
    f_res = run_friedman_test(a, b, c)
    assert f_res["p_value"] < 0.01

    # 5. Holm-Bonferroni correction
    p_dict = {"A_vs_B": 0.001, "A_vs_C": 0.02, "B_vs_C": 0.04}
    adj = holm_bonferroni_correction(p_dict, alpha=0.05)
    assert adj["A_vs_B"]["significant_at_05"] is True
