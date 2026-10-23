"""Conformal Quantile Calibrator and Risk-Coverage Evaluator.

Calibrates finite-sample conformal trust thresholds and computes Area Under the
Risk-Coverage Curve (AURC) for selective prediction guarantees.
"""

from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
import scipy.integrate

# Future-proof trapezoid integration
if hasattr(np, "trapezoid"):
    _trapz = np.trapezoid
elif hasattr(np, "trapz"):
    _trapz = np.trapz
else:
    _trapz = scipy.integrate.trapezoid


def calibrate_conformal_threshold(
    calibration_trust_scores: Sequence[float],
    target_coverage: float = 0.80,
    alpha: Union[float, None] = None,
) -> float:
    """Computes the finite-sample conformal quantile threshold for trust scores.

    If target_coverage is 0.80, alpha = 0.20 (abstention rate).
    Threshold is the (floor((n+1)*alpha) / n)-th quantile of calibration scores.
    """
    scores = np.array(calibration_trust_scores, dtype=float)
    n = len(scores)
    if n == 0:
        return 0.50

    if alpha is None:
        alpha = max(0.0, min(1.0, 1.0 - target_coverage))

    q_level = float(np.clip(np.floor((n + 1) * alpha) / n, 0.0, 1.0))
    tau_T = float(np.quantile(scores, q_level))
    return float(np.clip(tau_T, 0.0, 1.0))


def compute_risk_coverage_curve(
    trust_scores: Sequence[float],
    losses: Sequence[float],
    num_thresholds: int = 20,
) -> Dict[str, Union[List[float], float]]:
    """Evaluates Selective Risk R_sel(Phi) sweeping coverage Phi from 0.10 to 1.00.

    Orders samples by descending trust score (confidence).
    At coverage Phi, calculates selective risk on the top ceil(Phi * N) accepted samples.
    Integrates the curve via trapezoidal rule to compute AURC.
    """
    scores = np.array(trust_scores, dtype=float)
    losses_arr = np.array(losses, dtype=float)
    N = len(scores)

    if N == 0:
        return {"coverages": [1.0], "risks": [0.0], "aurc": 0.0}

    # Sort in descending order of trust/confidence
    order = np.argsort(-scores)
    sorted_losses = losses_arr[order]

    coverages: List[float] = []
    risks: List[float] = []

    # Sweep coverage Phi from 0.10 to 1.00
    phi_grid = np.linspace(0.10, 1.00, num_thresholds)
    for phi in phi_grid:
        k = max(1, int(np.ceil(phi * N)))
        sel_risk = float(np.mean(sorted_losses[:k]))
        coverages.append(float(phi))
        risks.append(float(sel_risk))

    # Compute AURC (Area Under Risk-Coverage Curve)
    aurc = float(_trapz(risks, coverages))

    return {
        "coverages": coverages,
        "risks": risks,
        "aurc": max(0.0, aurc),
    }


class AdaptiveNonExchangeableConformalCalibrator:
    """Adaptive Non-Exchangeable Conformal Calibrator for Time-Series Telemetry Streams.

    Implements:
    1. Exponential recency weighting (Barber et al., 2023):
       w_i = gamma^(n - 1 - i) with gamma = 0.98.
       Computes non-exchangeable conformal quantiles over sequential calibration buffers.
    2. Online step-size adaptation (Gibbs & Candes, 2021; ACI):
       alpha_{t+1} = clip(alpha_t + eta * (err_t - alpha_target), min_alpha, max_alpha)
       where err_t = I(score_t < tau_t).
    3. Evaluation utilities for Expected Calibration Error (ECE) and coverage stability under temporal drift.
    """

    def __init__(
        self,
        target_coverage: float = 0.80,
        gamma: float = 0.98,
        eta: float = 0.02,
        min_alpha: float = 0.01,
        max_alpha: float = 0.50,
    ):
        self.target_coverage = float(target_coverage)
        self.alpha_target = float(max(0.0, min(1.0, 1.0 - target_coverage)))
        self.alpha_t = self.alpha_target
        self.gamma = float(gamma)
        self.eta = float(eta)
        self.min_alpha = float(min_alpha)
        self.max_alpha = float(max_alpha)
        self.history_scores: List[float] = []
        self.history_errors: List[float] = []
        self.history_thresholds: List[float] = []

    def calibrate_threshold(
        self,
        calibration_scores: Sequence[float],
        alpha: Optional[float] = None,
    ) -> float:
        """Computes non-exchangeable conformal quantile threshold with recency weights.

        For trust scores where higher is more reliable:
        Weights w_i = gamma^(n - 1 - i) for i = 0, ..., n-1.
        Includes hypothetical test point with weight 1.0.
        Finds the weighted quantile at level alpha.
        """
        scores = np.array(calibration_scores, dtype=float)
        n = len(scores)
        if n == 0:
            return 0.50

        target_alpha = alpha if alpha is not None else self.alpha_t
        target_alpha = float(np.clip(target_alpha, self.min_alpha, self.max_alpha))

        # Exponential recency weights: w_i = gamma^(n - 1 - i)
        exponents = np.arange(n - 1, -1, -1)
        w = np.power(self.gamma, exponents)

        w_test = 1.0
        w_total = np.sum(w) + w_test

        sort_idx = np.argsort(scores)
        sorted_scores = scores[sort_idx]
        sorted_w = w[sort_idx]

        cum_w = np.cumsum(sorted_w) / w_total

        idx = np.searchsorted(cum_w, target_alpha, side="left")
        if idx >= n:
            tau = sorted_scores[-1]
        else:
            tau = sorted_scores[idx]

        return float(np.clip(tau, 0.0, 1.0))

    def update_online(
        self,
        score: float,
        is_error: Optional[bool] = None,
        tau: Optional[float] = None,
    ) -> float:
        """Online step-size adaptation under distribution drift.

        alpha_{t+1} = clip(alpha_t + eta * (err_t - alpha_target), min_alpha, max_alpha)
        Updates internal history and returns current threshold tau_{t+1}.
        """
        curr_tau = tau if tau is not None else self.calibrate_threshold(self.history_scores or [score])

        if is_error is None:
            err_t = 1.0 if score < curr_tau else 0.0
        else:
            err_t = 1.0 if is_error else 0.0

        self.alpha_t = float(np.clip(
            self.alpha_t + self.eta * (err_t - self.alpha_target),
            self.min_alpha,
            self.max_alpha,
        ))

        self.history_scores.append(float(score))
        self.history_errors.append(float(err_t))
        self.history_thresholds.append(float(curr_tau))

        next_tau = self.calibrate_threshold(self.history_scores)
        return next_tau

    @staticmethod
    def compute_ece(
        scores: Sequence[float],
        labels: Sequence[int],
        num_bins: int = 10,
    ) -> float:
        """Computes Expected Calibration Error (ECE) across confidence bins."""
        s_arr = np.array(scores, dtype=float)
        l_arr = np.array(labels, dtype=float)
        n = len(s_arr)
        if n == 0:
            return 0.0

        bin_edges = np.linspace(0.0, 1.0, num_bins + 1)
        ece = 0.0

        for b in range(num_bins):
            if b == num_bins - 1:
                bin_mask = (s_arr >= bin_edges[b]) & (s_arr <= bin_edges[b + 1])
            else:
                bin_mask = (s_arr >= bin_edges[b]) & (s_arr < bin_edges[b + 1])
            bin_size = int(np.sum(bin_mask))
            if bin_size > 0:
                bin_acc = float(np.mean(l_arr[bin_mask]))
                bin_conf = float(np.mean(s_arr[bin_mask]))
                ece += (bin_size / n) * abs(bin_acc - bin_conf)

        return float(round(ece, 4))

    @staticmethod
    def compute_coverage_stability(
        accepted_mask: Sequence[bool],
        window_size: int = 25,
    ) -> float:
        """Computes standard deviation of rolling-window coverage under drift."""
        acc = np.array(accepted_mask, dtype=float)
        if len(acc) < window_size:
            return 0.0
        import pandas as pd
        rolling_cov = pd.Series(acc).rolling(window=window_size).mean().dropna().values
        return float(round(float(np.std(rolling_cov)), 4))

    def compare_static_vs_adaptive(
        self,
        calibration_scores: Sequence[float],
        test_scores: Sequence[float],
        test_labels: Sequence[int],
    ) -> Dict[str, Any]:
        """Compares static split conformal vs. adaptive non-exchangeable conformal.

        Returns ECE and coverage stability (rolling std) under temporal drift.
        """
        cal_arr = list(calibration_scores)
        test_arr = list(test_scores)
        labels = list(test_labels)

        # 1. Static Split Conformal (fixed threshold)
        static_tau = calibrate_conformal_threshold(cal_arr, target_coverage=self.target_coverage)
        static_accepted = [bool(s >= static_tau) for s in test_arr]
        static_cov = float(np.mean(static_accepted)) if test_arr else 1.0
        static_stability = self.compute_coverage_stability(static_accepted)
        static_ece = self.compute_ece(test_arr, labels)

        # 2. Adaptive Non-Exchangeable Conformal
        adaptive_calibrator = AdaptiveNonExchangeableConformalCalibrator(
            target_coverage=self.target_coverage,
            gamma=self.gamma,
            eta=self.eta,
        )
        adaptive_calibrator.history_scores = list(cal_arr)

        adaptive_accepted = []
        adaptive_thresholds = []

        for s, lab in zip(test_arr, labels):
            tau_curr = adaptive_calibrator.calibrate_threshold(adaptive_calibrator.history_scores[-len(cal_arr):])
            acc = bool(s >= tau_curr)
            adaptive_accepted.append(acc)
            adaptive_thresholds.append(tau_curr)
            is_err = not acc if lab == 1 else acc
            adaptive_calibrator.update_online(score=s, is_error=is_err, tau=tau_curr)

        adaptive_cov = float(np.mean(adaptive_accepted)) if test_arr else 1.0
        adaptive_stability = self.compute_coverage_stability(adaptive_accepted)
        adaptive_ece = self.compute_ece(test_arr, labels)

        return {
            "target_coverage": self.target_coverage,
            "static_conformal": {
                "threshold": float(round(static_tau, 4)),
                "coverage": float(round(static_cov, 4)),
                "ece": float(round(static_ece, 4)),
                "coverage_stability_std": float(round(static_stability, 4)),
            },
            "adaptive_non_exchangeable": {
                "gamma": self.gamma,
                "eta": self.eta,
                "coverage": float(round(adaptive_cov, 4)),
                "ece": float(round(adaptive_ece, 4)),
                "coverage_stability_std": float(round(adaptive_stability, 4)),
                "stability_improvement_pct": float(round(
                    max(0.0, (static_stability - adaptive_stability) / (static_stability + 1e-4) * 100.0), 2
                )),
            },
        }
