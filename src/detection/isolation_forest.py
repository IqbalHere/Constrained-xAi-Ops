"""Isolation Forest Anomaly Detector for Microservice Telemetry.

Zero-leakage: fits strictly on pre-fault baseline data (t < inject_time - pre_buffer_sec).
Scores post-fault window and calibrates against pre-fault quantile distribution into [0.0, 1.0].
"""

from typing import Dict, List, Optional, Sequence
import numpy as np
from sklearn.ensemble import IsolationForest

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    group_metrics_by_service,
)
from src.schemas import TelemetryCase


class IsolationForestDetector:
    """Microservice Anomaly Detector powered by Scikit-Learn IsolationForest.

    Fits strictly on pre-fault feature matrices of service s.
    Evaluates post-fault decision function and calibrates into bounded probability A(s, w) in [0.0, 1.0].
    """

    def __init__(
        self,
        n_estimators: int = 100,
        contamination: str = "auto",
        seed: int = 42,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        threshold_offset: float = 1.0,
        scale_param: float = 2.5,
    ):
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.seed = seed
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.threshold_offset = threshold_offset
        self.scale_param = scale_param
        # service -> (fitted IsolationForest, med_pre, mad_pre)
        self.models_: Dict[str, tuple[IsolationForest, float, float]] = {}

    def _build_feature_matrix(
        self,
        metrics_dict: Dict[str, Sequence[float]],
        masks_dict: Optional[Dict[str, Sequence[int]]] = None,
    ) -> np.ndarray:
        """Constructs 2D feature matrix [features, indicators] from metric streams."""
        col_arrays = []
        for col_name, vals in sorted(metrics_dict.items()):
            arr = np.array(vals, dtype=float)
            col_arrays.append(arr)
            if masks_dict is not None and col_name in masks_dict:
                m_arr = np.array(masks_dict[col_name], dtype=float)
                col_arrays.append(m_arr)

        if not col_arrays:
            return np.empty((0, 0), dtype=float)

        return np.column_stack(col_arrays)

    def fit_service(
        self,
        service: str,
        metrics_pre: Dict[str, Sequence[float]],
        masks_pre: Optional[Dict[str, Sequence[int]]] = None,
    ) -> None:
        """Fits an Isolation Forest model strictly on pre-fault normal data for a service."""
        X_pre = self._build_feature_matrix(metrics_pre, masks_pre)
        if X_pre.shape[0] < 5 or X_pre.shape[1] == 0:
            return

        clf = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.seed,
        )
        clf.fit(X_pre)
        # In scikit-learn, -decision_function is higher for anomalous points
        scores_pre = -clf.decision_function(X_pre)
        med_pre = float(np.median(scores_pre))
        mad_pre = float(1.4826 * np.median(np.abs(scores_pre - med_pre)) + 1e-4)

        self.models_[service] = (clf, med_pre, mad_pre)

    def score_service(
        self,
        service: str,
        metrics_post: Dict[str, Sequence[float]],
        masks_post: Optional[Dict[str, Sequence[int]]] = None,
    ) -> float:
        """Scores post-fault feature matrix and maps to bounded probability A(s, w) in [0.0, 1.0]."""
        if service not in self.models_:
            return 0.0

        clf, med_pre, mad_pre = self.models_[service]
        X_post = self._build_feature_matrix(metrics_post, masks_post)
        if X_post.shape[0] == 0 or X_post.shape[1] == 0:
            return 0.0

        scores_post = -clf.decision_function(X_post)
        raw_post = float(np.percentile(scores_post, 90))

        # Calibrate relative to pre-fault baseline
        z = max(0.0, (raw_post - med_pre) / mad_pre)
        raw_diff = max(0.0, z - self.threshold_offset)
        score = float(1.0 - np.exp(-raw_diff / self.scale_param))
        return float(np.clip(score, 0.0, 1.0))

    def detect(
        self,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        services: Sequence[str] = KNOWN_ONLINE_BOUTIQUE_SERVICES,
    ) -> Dict[str, float]:
        """Runs zero-leakage Isolation Forest anomaly detection across all microservices."""
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
        col_to_idx = {c: i for i, c in enumerate(columns)} if mask is not None else {}

        # 1. Fit models strictly on pre-fault normal data
        for s in services:
            metrics = grouped.get(s, {})
            metrics_pre = {
                col: np.array(vals, dtype=float)[pre_mask].tolist()
                for col, vals in metrics.items()
            }
            masks_pre = None
            if mask is not None:
                masks_pre = {
                    col: mask[pre_mask, col_to_idx[col]].tolist()
                    for col in metrics.keys()
                    if col in col_to_idx
                }
            self.fit_service(s, metrics_pre, masks_pre)

        # 2. Score post-fault evaluation window
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
