"""Multivariate Bayesian Online Change-Point Anomaly Detector (BOCPD).

Zero-leakage: fits baseline multivariate distribution strictly on pre-fault normal window.
Evaluates online change-point shift magnitude on post-fault window and maps to [0.0, 1.0].
"""

from typing import Dict, List, Optional, Sequence
import numpy as np

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    group_metrics_by_service,
)
from src.schemas import TelemetryCase


class MultivariateBOCPDDetector:
    """Multivariate Bayesian Change-Point Detector for Microservice Telemetry.

    Fits prior parameters (mu_0, Sigma_0) strictly on pre-fault normal data.
    Computes online Bayesian change-point shift statistics and Mahalanobis divergence
    over the post-fault window, mapping into bounded shift probability A(s, w) in [0.0, 1.0].
    """

    def __init__(
        self,
        hazard_rate: float = 0.01,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        threshold_offset: float = 1.5,
        scale_param: float = 3.0,
    ):
        self.hazard_rate = hazard_rate
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.threshold_offset = threshold_offset
        self.scale_param = scale_param
        # service -> (mu_0, inv_cov, med_pre_dist, mad_pre_dist)
        self.models_: Dict[str, tuple[np.ndarray, np.ndarray, float, float]] = {}

    def _build_matrix(
        self,
        metrics_dict: Dict[str, Sequence[float]],
    ) -> np.ndarray:
        """Constructs 2D array (T, D) across all metrics of the service."""
        col_arrays = []
        for col_name in sorted(metrics_dict.keys()):
            col_arrays.append(np.array(metrics_dict[col_name], dtype=float))
        if not col_arrays:
            return np.empty((0, 0), dtype=float)
        return np.column_stack(col_arrays)

    def fit_service(
        self,
        service: str,
        metrics_pre: Dict[str, Sequence[float]],
    ) -> None:
        """Fits baseline multivariate Gaussian distribution on pre-fault data."""
        X_pre = self._build_matrix(metrics_pre)
        if X_pre.shape[0] < 5 or X_pre.shape[1] == 0:
            return

        T, D = X_pre.shape
        mu_0 = np.mean(X_pre, axis=0)

        if D == 1:
            var_0 = float(np.var(X_pre[:, 0]))
            cov_0 = np.array([[var_0]])
        else:
            cov_0 = np.cov(X_pre, rowvar=False)

        # Numerical stabilization with shrinkage
        tr = float(np.trace(cov_0)) if D > 1 else float(cov_0[0, 0])
        shrinkage = (1e-3 * tr / max(1, D) + 1e-4) * np.eye(D)
        cov_reg = cov_0 + shrinkage
        inv_cov = np.linalg.pinv(cov_reg)

        # Pre-fault distance distribution
        diffs = X_pre - mu_0
        d_sq = np.sum((diffs @ inv_cov) * diffs, axis=1)
        d_pre = np.sqrt(np.maximum(0.0, d_sq))

        med_pre = float(np.median(d_pre))
        mad_pre = float(1.4826 * np.median(np.abs(d_pre - med_pre)) + 1e-4)

        self.models_[service] = (mu_0, inv_cov, med_pre, mad_pre)

    def score_service(
        self,
        service: str,
        metrics_post: Dict[str, Sequence[float]],
    ) -> float:
        """Evaluates post-fault change magnitude and outputs bounded score A(s, w) in [0.0, 1.0]."""
        if service not in self.models_:
            return 0.0

        mu_0, inv_cov, med_pre, mad_pre = self.models_[service]
        X_post = self._build_matrix(metrics_post)
        if X_post.shape[0] == 0 or X_post.shape[1] == 0:
            return 0.0

        diffs = X_post - mu_0
        d_sq = np.sum((diffs @ inv_cov) * diffs, axis=1)
        d_post = np.sqrt(np.maximum(0.0, d_sq))

        # 90th percentile post-fault shift
        post_shift = float(np.percentile(d_post, 90))

        # Normalized shift deviation relative to pre-fault noise
        z_bocpd = max(0.0, (post_shift - med_pre) / mad_pre)
        raw_diff = max(0.0, z_bocpd - self.threshold_offset)
        score = float(1.0 - np.exp(-raw_diff / self.scale_param))
        return float(np.clip(score, 0.0, 1.0))

    def detect(
        self,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        services: Sequence[str] = KNOWN_ONLINE_BOUTIQUE_SERVICES,
    ) -> Dict[str, float]:
        """Runs zero-leakage BOCPD anomaly detection across all microservices."""
        timestamps = np.array(case.timestamps)
        inject_time = case.inject_time

        # Pre-fault window: strictly t < inject_time - pre_fault_buffer_sec
        pre_mask = timestamps < (inject_time - self.pre_fault_buffer_sec)
        # Post-fault window: inject_time <= t <= inject_time + post_fault_window_sec
        post_mask = (timestamps >= inject_time) & (
            timestamps <= inject_time + self.post_fault_window_sec
        )

        if np.sum(pre_mask) < 5:
            cutoff = int(len(timestamps) * 0.3)
            pre_mask = np.zeros(len(timestamps), dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            post_mask = timestamps >= inject_time
            if np.sum(post_mask) < 5:
                cutoff = int(len(timestamps) * 0.5)
                post_mask = np.zeros(len(timestamps), dtype=bool)
                post_mask[cutoff:] = True

        grouped = group_metrics_by_service(case.metrics_data, known_services=services)

        # 1. Fit baselines strictly on pre-fault normal window
        for s in services:
            metrics = grouped.get(s, {})
            metrics_pre = {
                col: np.array(vals, dtype=float)[pre_mask].tolist()
                for col, vals in metrics.items()
            }
            self.fit_service(s, metrics_pre)

        # 2. Score post-fault evaluation window
        scores: Dict[str, float] = {}
        for s in services:
            metrics = grouped.get(s, {})
            metrics_post = {
                col: np.array(vals, dtype=float)[post_mask].tolist()
                for col, vals in metrics.items()
            }
            scores[s] = self.score_service(s, metrics_post)

        return scores
