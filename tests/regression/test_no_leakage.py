"""Zero-Leakage Regression Test Suite for Constrained-xAIOps.

Mandatory Scientific Rule: Post-fault telemetry (t >= inject_time) must NEVER touch
pre-fault model fitting, normalization baselines, or covariance matrices.
Proves that inflating post-fault data by 1000x results in bit-for-bit identical pre-fault states.
"""

import numpy as np
import pandas as pd
import pytest

from src.detection.bocpd import MultivariateBOCPDDetector
from src.detection.isolation_forest import IsolationForestDetector
from src.detection.statistical import RobustZScoreDetector
from src.preprocessing.imputer import CausalImputer
from src.quality.trust_score import TelemetryTrustEvaluator
from src.schemas import TelemetryCase


def create_baseline_test_case() -> tuple[TelemetryCase, TelemetryCase]:
    """Creates a base case and an extreme post-fault corrupted case (1000x post-fault inflation)."""
    rng = np.random.default_rng(1024)
    T = 200
    timestamps = list(range(1000, 1000 + T))
    inject_time = 1100  # Step 100

    # Normal stationary pre-fault data
    cart_pre = rng.normal(loc=25.0, scale=2.0, size=100)
    cart_post = rng.normal(loc=30.0, scale=2.0, size=100)
    cart_base = np.concatenate([cart_pre, cart_post])

    # Extreme post-fault corruption: 1000x multiplication
    cart_corrupted = np.concatenate([cart_pre, cart_post * 1000.0])

    frontend_pre = rng.normal(loc=10.0, scale=1.0, size=100)
    frontend_post = rng.normal(loc=12.0, scale=1.0, size=100)
    frontend_base = np.concatenate([frontend_pre, frontend_post])
    frontend_corrupted = np.concatenate([frontend_pre, frontend_post * 1000.0])

    base_metrics = {
        "cartservice_cpu": cart_base.tolist(),
        "frontend_cpu": frontend_base.tolist(),
    }
    corrupted_metrics = {
        "cartservice_cpu": cart_corrupted.tolist(),
        "frontend_cpu": frontend_corrupted.tolist(),
    }

    base_case = TelemetryCase(
        case_id="base_case",
        system="OnlineBoutique",
        metrics_data=base_metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_cpu",
        data_source_tag="SYNTHETIC_DEMO",
    )

    corrupted_case = TelemetryCase(
        case_id="corrupted_case",
        system="OnlineBoutique",
        metrics_data=corrupted_metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_cpu",
        data_source_tag="SYNTHETIC_DEMO",
    )

    return base_case, corrupted_case


def test_zero_leakage_robust_zscore_detector():
    """Verify RobustZScoreDetector pre-fault baseline parameters are bit-for-bit identical."""
    base_case, corrupted_case = create_baseline_test_case()

    det_base = RobustZScoreDetector()
    det_base.detect(base_case)

    det_corr = RobustZScoreDetector()
    det_corr.detect(corrupted_case)

    # Check that baselines_ (fitted pre-fault median and MAD) match bit-for-bit
    for s in ["cartservice", "frontend"]:
        assert s in det_base.baselines_
        assert s in det_corr.baselines_
        for metric in det_base.baselines_[s]:
            base_med, base_mad = det_base.baselines_[s][metric]
            corr_med, corr_mad = det_corr.baselines_[s][metric]
            assert base_med == corr_med, f"Leakage detected in {s} {metric} median!"
            assert base_mad == corr_mad, f"Leakage detected in {s} {metric} MAD!"


def test_zero_leakage_bocpd_detector():
    """Verify MultivariateBOCPDDetector pre-fault parameters are bit-for-bit identical."""
    base_case, corrupted_case = create_baseline_test_case()

    det_base = MultivariateBOCPDDetector()
    det_base.detect(base_case)

    det_corr = MultivariateBOCPDDetector()
    det_corr.detect(corrupted_case)

    for s in ["cartservice", "frontend"]:
        assert s in det_base.models_
        assert s in det_corr.models_
        mu_b, inv_cov_b, med_b, mad_b = det_base.models_[s]
        mu_c, inv_cov_c, med_c, mad_c = det_corr.models_[s]
        np.testing.assert_array_equal(mu_b, mu_c, err_msg=f"Leakage in {s} BOCPD mean!")
        np.testing.assert_array_equal(inv_cov_b, inv_cov_c, err_msg=f"Leakage in {s} BOCPD inv_cov!")
        assert med_b == med_c, f"Leakage in {s} BOCPD med_pre!"
        assert mad_b == mad_c, f"Leakage in {s} BOCPD mad_pre!"


def test_zero_leakage_isolation_forest_detector():
    """Verify IsolationForestDetector pre-fault calibration values are bit-for-bit identical."""
    base_case, corrupted_case = create_baseline_test_case()

    det_base = IsolationForestDetector(seed=42)
    det_base.detect(base_case)

    det_corr = IsolationForestDetector(seed=42)
    det_corr.detect(corrupted_case)

    for s in ["cartservice", "frontend"]:
        assert s in det_base.models_
        assert s in det_corr.models_
        _, med_b, mad_b = det_base.models_[s]
        _, med_c, mad_c = det_corr.models_[s]
        assert med_b == med_c, f"Leakage in {s} IsolationForest med_pre!"
        assert mad_b == mad_c, f"Leakage in {s} IsolationForest mad_pre!"


def test_zero_leakage_causal_imputation():
    """Verify CausalImputer produces bit-for-bit identical pre-fault imputations."""
    base_case, corrupted_case = create_baseline_test_case()
    df_base = pd.DataFrame(base_case.metrics_data)
    df_corr = pd.DataFrame(corrupted_case.metrics_data)

    T, M = df_base.shape
    # Add random missingness in pre-fault window
    mask = np.ones((T, M), dtype=np.uint8)
    mask[20:30, :] = 0  # Missing block in pre-fault

    imputer = CausalImputer(method="forward_fill")
    imp_base = imputer.impute(df_base, mask=mask, inject_time_idx=100)
    imp_corr = imputer.impute(df_corr, mask=mask, inject_time_idx=100)

    # Pre-fault rows (0 to 100) must be bit-for-bit identical
    np.testing.assert_array_equal(
        imp_base.iloc[:100].values,
        imp_corr.iloc[:100].values,
        err_msg="Causal imputer leaked future values into pre-fault window!",
    )
