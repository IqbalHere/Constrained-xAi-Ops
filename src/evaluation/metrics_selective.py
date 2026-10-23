"""Selective Classification and Trust Calibration Metrics Suite.

Implements:
1. Coverage, Selective Risk, Abstention Rate, and MNAR Crash Recovery Rate.
2. Area Under Risk-Coverage Curve (AURC).
3. Expected Calibration Error (ECE) across trust bins.
"""

from typing import Dict, List, Sequence
import numpy as np

from src.abstention.conformal import compute_risk_coverage_curve


def compute_expected_calibration_error(
    trust_scores: Sequence[float],
    success_indicators: Sequence[int],
    num_bins: int = 10,
) -> float:
    """Computes Expected Calibration Error (ECE) between trust scores and RCA success."""
    t_arr = np.array(trust_scores, dtype=float)
    s_arr = np.array(success_indicators, dtype=float)
    n = len(t_arr)
    if n == 0:
        return 0.0

    bins = np.linspace(0.0, 1.0, num_bins + 1)
    ece = 0.0

    for i in range(num_bins):
        low, high = bins[i], bins[i + 1]
        if i == num_bins - 1:
            in_bin = (t_arr >= low) & (t_arr <= high)
        else:
            in_bin = (t_arr >= low) & (t_arr < high)

        bin_count = np.sum(in_bin)
        if bin_count > 0:
            mean_conf = float(np.mean(t_arr[in_bin]))
            mean_acc = float(np.mean(s_arr[in_bin]))
            ece += (bin_count / n) * abs(mean_acc - mean_conf)

    return float(round(ece, 4))


def compute_selective_metrics(
    accepted_mask: Sequence[bool],
    hit_at_3_indicators: Sequence[bool],
    trust_scores: Sequence[float],
    recovered_indicators: Sequence[bool],
) -> Dict[str, float]:
    """Computes comprehensive selective prediction metrics."""
    acc_arr = np.array(accepted_mask, dtype=bool)
    hit3_arr = np.array(hit_at_3_indicators, dtype=bool)
    trust_arr = np.array(trust_scores, dtype=float)
    rec_arr = np.array(recovered_indicators, dtype=bool)
    N = len(acc_arr)

    if N == 0:
        return {
            "coverage": 0.0,
            "abstention_rate": 1.0,
            "selective_risk": 0.0,
            "aurc": 0.0,
            "ece": 0.0,
            "mnar_recovery_rate": 0.0,
        }

    cov = float(np.mean(acc_arr))
    abst = 1.0 - cov

    # Selective risk on accepted cases: 1.0 - AC@3
    if np.sum(acc_arr) > 0:
        sel_risk = float(1.0 - np.mean(hit3_arr[acc_arr]))
    else:
        sel_risk = 0.0

    # AURC
    losses = [0.0 if h else 1.0 for h in hit3_arr]
    curve = compute_risk_coverage_curve(trust_arr, losses, num_thresholds=10)
    aurc = float(curve["aurc"])

    # ECE
    ece = compute_expected_calibration_error(
        trust_scores=trust_arr,
        success_indicators=[1 if h else 0 for h in hit3_arr],
        num_bins=10,
    )

    # MNAR recovery rate
    rec_rate = float(np.mean(rec_arr)) if len(rec_arr) > 0 else 0.0

    return {
        "coverage": round(cov, 4),
        "abstention_rate": round(abst, 4),
        "selective_risk": round(sel_risk, 4),
        "aurc": round(aurc, 4),
        "ece": round(ece, 4),
        "mnar_recovery_rate": round(rec_rate, 4),
    }
