"""Unit tests for Conformal Selective Prediction Gate & MNAR Escalator."""

import numpy as np
import pytest

from src.abstention.conformal import (
    calibrate_conformal_threshold,
    compute_risk_coverage_curve,
)
from src.abstention.mnar_escalator import detect_mnar_blackout
from src.abstention.selective_gate import SelectiveGate, decide_service
from src.schemas import SelectiveDecision, TrustEvaluation


def test_conformal_threshold_calibration():
    """Verify finite-sample conformal quantile threshold calculation."""
    # Synthetic calibration trust scores
    cal_scores = [0.95, 0.90, 0.88, 0.85, 0.82, 0.80, 0.75, 0.70, 0.60, 0.40]
    # For coverage 0.80, alpha = 0.20
    tau_T = calibrate_conformal_threshold(cal_scores, target_coverage=0.80)

    assert 0.40 <= tau_T <= 0.95
    # As target_coverage increases, tau_T decreases (more permissive trust accepted)
    tau_T_high_cov = calibrate_conformal_threshold(cal_scores, target_coverage=0.90)
    assert tau_T_high_cov <= tau_T


def test_risk_coverage_curve_and_aurc():
    """Verify Risk-Coverage Curve and AURC computation."""
    np.random.seed(42)
    N = 100
    # Trust scores and corresponding 0-1 error losses (better trust -> lower loss)
    trust_scores = np.linspace(0.9, 0.3, N)
    # Losses: low loss on high trust, high loss on low trust
    losses = [0.0 if s > 0.6 else 1.0 for s in trust_scores]

    res = compute_risk_coverage_curve(trust_scores, losses, num_thresholds=10)

    assert "coverages" in res
    assert "risks" in res
    assert "aurc" in res
    assert len(res["coverages"]) == 10
    assert len(res["risks"]) == 10
    assert 0.0 <= res["aurc"] <= 1.0
    # Risk should generally increase or stay flat as coverage expands from 0.1 to 1.0
    assert res["risks"][-1] >= res["risks"][0]


def test_four_selective_gate_states():
    """Verify decide_service cleanly routes into all 4 canonical selective states."""
    tau_T = 0.70
    tau_A = 0.35

    # 1. NORMAL: trust >= 0.70, anomaly < 0.35
    d1 = decide_service("c1", "cartservice", anomaly_score=0.10, trust_score=0.85, is_mnar_blackout=False, tau_T=tau_T, tau_A=tau_A)
    assert d1.outcome == "NORMAL"

    # 2. HIGH_CONFIDENCE_INCIDENT: trust >= 0.70, anomaly >= 0.35
    d2 = decide_service("c1", "cartservice", anomaly_score=0.75, trust_score=0.85, is_mnar_blackout=False, tau_T=tau_T, tau_A=tau_A)
    assert d2.outcome == "HIGH_CONFIDENCE_INCIDENT"

    # 3. ABSTAIN_LOW_TRUST: trust < 0.70, no blackout
    d3 = decide_service("c1", "cartservice", anomaly_score=0.10, trust_score=0.50, is_mnar_blackout=False, tau_T=tau_T, tau_A=tau_A)
    assert d3.outcome == "ABSTAIN_LOW_TRUST"

    # 4. ESCALATE_MNAR_BLACKOUT: is_mnar_blackout == True
    d4 = decide_service("c1", "cartservice", anomaly_score=0.10, trust_score=0.50, is_mnar_blackout=True, tau_T=tau_T, tau_A=tau_A)
    assert d4.outcome == "ESCALATE_MNAR_BLACKOUT"


def test_mnar_escalator_distinguishes_crash_from_random_drop():
    """Verify detect_mnar_blackout triggers on crashed service with symptomatic neighbors."""
    # Scenario: cartservice drops post-fault completeness to 0.4 (pre=1.0) and trust to 0.50
    # while its caller checkoutservice has high trust 0.90 and active anomaly 0.85
    trust_eval = TrustEvaluation(
        case_id="case_mnar_1",
        window_idx=0,
        service_scores={"cartservice": 0.50, "checkoutservice": 0.90, "frontend": 0.85},
        dimensions={"C": 0.7, "L": 0.8, "S": 0.8, "V": 1.0, "Q": 0.8},
    )
    pre_comp = {"cartservice": 1.0, "checkoutservice": 1.0, "frontend": 1.0}
    post_comp = {"cartservice": 0.40, "checkoutservice": 1.0, "frontend": 1.0}
    anomalies = {"cartservice": 0.05, "checkoutservice": 0.85, "frontend": 0.60}

    # cartservice should trigger MNAR blackout escalation
    is_blackout = detect_mnar_blackout(
        service="cartservice",
        trust_eval=trust_eval,
        pre_completeness=pre_comp,
        post_completeness=post_comp,
        neighbor_anomaly_scores=anomalies,
        tau_T=0.70,
        tau_A=0.35,
    )
    assert is_blackout is True

    # But if neighbors have NO anomaly (clean quiescent system, just random sensor packet drop):
    anomalies_quiescent = {"cartservice": 0.05, "checkoutservice": 0.02, "frontend": 0.01}
    is_not_blackout = detect_mnar_blackout(
        service="cartservice",
        trust_eval=trust_eval,
        pre_completeness=pre_comp,
        post_completeness=post_comp,
        neighbor_anomaly_scores=anomalies_quiescent,
        tau_T=0.70,
        tau_A=0.35,
    )
    # Should passively abstain, not escalate
    assert is_not_blackout is False


def test_adaptive_non_exchangeable_conformal_calibrator():
    """Verify exponentially-weighted non-exchangeable conformal prediction and online drift adaptation."""
    from src.abstention.conformal import AdaptiveNonExchangeableConformalCalibrator

    calibrator = AdaptiveNonExchangeableConformalCalibrator(target_coverage=0.80, gamma=0.98, eta=0.02)
    cal_scores = [0.95, 0.92, 0.90, 0.88, 0.85, 0.82, 0.80, 0.78, 0.75, 0.70]

    # Non-exchangeable threshold with recency weights
    tau = calibrator.calibrate_threshold(cal_scores)
    assert 0.65 <= tau <= 0.95

    # Online step-size update
    tau_next = calibrator.update_online(score=0.60, is_error=True, tau=tau)
    assert calibrator.alpha_t > 0.20  # Alpha increases to adapt to error
    assert 0.0 <= tau_next <= 1.0

    # Test static vs adaptive comparison under temporal drift
    drifted_test_scores = [0.90] * 30 + [0.72] * 30 + [0.85] * 40
    test_labels = [1] * 100
    comp = calibrator.compare_static_vs_adaptive(
        calibration_scores=cal_scores,
        test_scores=drifted_test_scores,
        test_labels=test_labels,
    )
    assert "static_conformal" in comp
    assert "adaptive_non_exchangeable" in comp
    assert 0.0 <= comp["adaptive_non_exchangeable"]["ece"] <= 1.0
    assert 0.0 <= comp["adaptive_non_exchangeable"]["coverage_stability_std"] <= 1.0
