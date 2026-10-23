"""Online Conformal Threshold & Blackout Prior Recalibrator.

Implements bounded Robbins-Monro stochastic approximation to update
tau_T, tau_A, and lambda_mnar based on streaming operator feedback.
"""

from typing import Dict, List, Literal, Optional
import numpy as np


class OnlineThresholdRecalibrator:
    """Dynamically recalibrates thresholds using operator feedback."""

    def __init__(
        self,
        initial_tau_T: float = 0.85,
        initial_tau_A: float = 0.35,
        initial_lambda_mnar: float = 3.5,
        gamma_0: float = 0.05,
        beta: float = 0.01,
        tau_T_bounds: tuple[float, float] = (0.50, 0.95),
        tau_A_bounds: tuple[float, float] = (0.20, 0.60),
        lambda_mnar_bounds: tuple[float, float] = (1.0, 6.0),
    ):
        self.tau_T = initial_tau_T
        self.tau_A = initial_tau_A
        self.lambda_mnar = initial_lambda_mnar
        self.gamma_0 = gamma_0
        self.beta = beta
        self.tau_T_bounds = tau_T_bounds
        self.tau_A_bounds = tau_A_bounds
        self.lambda_mnar_bounds = lambda_mnar_bounds
        self.step_count = 0

    def step(
        self,
        verdict: Literal["CONFIRM_RCA", "FALSE_POSITIVE", "CONFIRM_MNAR_CRASH"],
        trust_score: float,
        anomaly_score: float,
    ) -> Dict[str, float]:
        """Applies a single feedback step and updates parameters."""
        self.step_count += 1
        gamma_t = self.gamma_0 / (1.0 + self.beta * self.step_count)

        if verdict == "FALSE_POSITIVE":
            # Operator flagged a false alarm -> raise trust requirement and anomaly threshold
            delta_tau_T = gamma_t * max(0.0, 1.0 - trust_score)
            delta_tau_A = gamma_t * 0.05
            self.tau_T = min(self.tau_T_bounds[1], self.tau_T + delta_tau_T)
            self.tau_A = min(self.tau_A_bounds[1], self.tau_A + delta_tau_A)

        elif verdict == "CONFIRM_MNAR_CRASH":
            # Operator confirmed a silent crash -> boost MNAR prior and prevent over-abstention
            self.lambda_mnar = min(self.lambda_mnar_bounds[1], self.lambda_mnar + gamma_t * 0.25)
            self.tau_T = max(self.tau_T_bounds[0], self.tau_T - gamma_t * 0.02)

        elif verdict == "CONFIRM_RCA":
            # Confirmed correct localization -> slight stability adjustment
            pass

        # Clamp all parameters to safety bounds
        self.tau_T = float(np.clip(self.tau_T, self.tau_T_bounds[0], self.tau_T_bounds[1]))
        self.tau_A = float(np.clip(self.tau_A, self.tau_A_bounds[0], self.tau_A_bounds[1]))
        self.lambda_mnar = float(np.clip(self.lambda_mnar, self.lambda_mnar_bounds[0], self.lambda_mnar_bounds[1]))

        return {
            "tau_T": round(self.tau_T, 4),
            "tau_A": round(self.tau_A, 4),
            "lambda_mnar": round(self.lambda_mnar, 4),
            "step": self.step_count,
            "learning_rate": round(gamma_t, 5),
        }

    def process_batch(self, feedback_records: List[Dict[str, object]]) -> Dict[str, float]:
        """Processes a sequence of feedback records."""
        last_state = {}
        for rec in feedback_records:
            last_state = self.step(
                verdict=rec["verdict"],
                trust_score=float(rec["trust_score"]),
                anomaly_score=float(rec["anomaly_score"]),
            )
        return last_state or {
            "tau_T": self.tau_T,
            "tau_A": self.tau_A,
            "lambda_mnar": self.lambda_mnar,
            "step": self.step_count,
        }
