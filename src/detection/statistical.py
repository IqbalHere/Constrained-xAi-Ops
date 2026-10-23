"""Lightweight Statistical Robust Z-Score Anomaly Detector.

Zero-leakage: fits strictly on pre-fault baseline timestamps (t < inject_time - pre_buffer_sec).
Outputs continuous service-level anomaly scores A(s, w) in [0.0, 1.0].
"""

from typing import Dict, List, Optional, Sequence
import numpy as np

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    group_metrics_by_service,
)
from src.schemas import TelemetryCase


def compute_ewma(arr: np.ndarray, alpha: float = 0.3) -> np.ndarray:
    """Computes Exponentially Weighted Moving Average (EWMA) over a 1D sequence."""
    n = len(arr)
    if n == 0:
        return np.array([], dtype=float)
    out = np.empty(n, dtype=float)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


class RobustZScoreDetector:
    """Robust Z-Score Anomaly Detector using Median and Median Absolute Deviation (MAD).

    Pre-fault: computes median_pre and mad_pre for each metric m of service s.
    Post-fault: evaluates EWMA-smoothed robust z-scores z(m, t) = |EWMA(x(m, t)) - median_pre| / mad_pre.
    Service score: 90th percentile across metric z-scores, mapped to bounded probability:
      A(s, w) = 1.0 - exp(-max(0.0, z_service - 1.5) / 3.0) in [0.0, 1.0].
    """

    def __init__(
        self,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        ewma_alpha: float = 0.3,
        threshold_offset: float = 1.5,
        scale_param: float = 3.0,
    ):
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.ewma_alpha = ewma_alpha
        self.threshold_offset = threshold_offset
        self.scale_param = scale_param
        # Fitted pre-fault baselines: service -> metric -> (median_pre, mad_pre)
        self.baselines_: Dict[str, Dict[str, tuple[float, float]]] = {}

    def fit_service(
        self,
        service: str,
        metrics_pre: Dict[str, Sequence[float]],
    ) -> None:
        """Fits baseline statistics strictly on pre-fault normal data for a single service."""
        service_stats = {}
        for metric_name, vals in metrics_pre.items():
            arr = np.array(vals, dtype=float)
            if len(arr) == 0:
                continue
            med = float(np.median(arr))
            mad = float(1.4826 * np.median(np.abs(arr - med)) + 1e-4)
            service_stats[metric_name] = (med, mad)
        self.baselines_[service] = service_stats

    def score_service(
        self,
        service: str,
        metrics_post: Dict[str, Sequence[float]],
        masks_post: Optional[Dict[str, Sequence[int]]] = None,
    ) -> float:
        """Computes continuous service-level anomaly score A(s, w) in [0.0, 1.0]."""
        if service not in self.baselines_:
            return 0.0

        service_stats = self.baselines_[service]
        all_z_scores: List[float] = []

        for metric_name, vals in metrics_post.items():
            if metric_name not in service_stats:
                continue
            med_pre, mad_pre = service_stats[metric_name]
            arr = np.array(vals, dtype=float)

            # Filter to observed timestamps if mask is provided
            if masks_post is not None and metric_name in masks_post:
                m_arr = np.array(masks_post[metric_name], dtype=bool)
                if np.sum(m_arr) > 0:
                    arr = arr[m_arr]

            if len(arr) == 0:
                continue

            ewma_vals = compute_ewma(arr, alpha=self.ewma_alpha)
            z_t = np.abs(ewma_vals - med_pre) / mad_pre
            all_z_scores.extend(z_t.tolist())

        if not all_z_scores:
            return 0.0

        # Service raw score is 90th percentile across metrics
        z_service = float(np.percentile(all_z_scores, 90))
        # Bounded probability mapping
        raw_diff = max(0.0, z_service - self.threshold_offset)
        score = float(1.0 - np.exp(-raw_diff / self.scale_param))
        return float(np.clip(score, 0.0, 1.0))

    def detect(
        self,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        services: Sequence[str] = KNOWN_ONLINE_BOUTIQUE_SERVICES,
    ) -> Dict[str, float]:
        """Runs zero-leakage anomaly detection across all microservices for a case."""
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
        columns = list(case.metrics_data.keys())

        # Build column index map if mask is provided
        col_to_idx = {c: i for i, c in enumerate(columns)} if mask is not None else {}

        # 1. Fit baselines strictly on pre-fault window
        for s in services:
            metrics = grouped.get(s, {})
            metrics_pre = {
                col: np.array(vals, dtype=float)[pre_mask].tolist()
                for col, vals in metrics.items()
            }
            self.fit_service(s, metrics_pre)

        # 2. Score post-fault window
        scores: Dict[str, float] = {}
        for s in services:
            metrics = grouped.get(s, {})
            metrics_post = {
                col: np.array(vals, dtype=float)[post_mask].tolist()
                for col, vals in metrics.items()
            }
            masks_post = None
            if mask is not None:
                masks_post = {
                    col: mask[post_mask, col_to_idx[col]].tolist()
                    for col in metrics.keys()
                    if col in col_to_idx
                }
            scores[s] = self.score_service(s, metrics_post, masks_post)

        return scores
