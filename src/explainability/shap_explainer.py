"""Missingness-Aware TreeSHAP Attribution & Explanation Reliability Badge.

Implements feature attribution on microservice time-series telemetry under missingness:
1. Compares Naive Imputation vs. Missingness-Augmented Feature Matrix [X_imp, M_mask, delta_C].
2. Computes exact TreeSHAP attributions using tree ensembles.
3. Folds attribution back to physical metrics.
4. Calculates Explanation Reliability Badge R_exp(s, w) and Gini Sparsity.
"""

from typing import Dict, List, Literal, Optional, Sequence, Tuple
import numpy as np
import shap
from sklearn.ensemble import ExtraTreesClassifier

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    group_metrics_by_service,
)
from src.schemas import TelemetryCase


def compute_gini_index(weights: Sequence[float]) -> float:
    """Computes the Gini Sparsity Index of attribution weights in [0.0, 1.0].

    Higher Gini = more sparse/concentrated attributions (clearer explanation for operators).
    """
    w = np.array(weights, dtype=float)
    if len(w) <= 1 or np.sum(w) <= 0:
        return 0.0
    w = np.sort(np.maximum(0.0, w))
    n = len(w)
    total = np.sum(w)
    if total <= 1e-12:
        return 0.0
    cum_w = np.cumsum(w)
    gini = (2.0 * np.sum((np.arange(1, n + 1)) * w) / (n * total)) - (n + 1) / n
    return float(np.clip(gini, 0.0, 1.0))


class MissingnessAwareSHAPExplainer:
    """TreeSHAP explainer for microservice anomaly attribution under telemetry missingness."""

    def __init__(
        self,
        mode: Literal["naive", "constrained_xaiops"] = "constrained_xaiops",
        n_estimators: int = 30,
        max_depth: int = 5,
        seed: int = 42,
    ):
        self.mode = mode
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.seed = seed

    def explain_service(
        self,
        service: str,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        pre_buffer_sec: int = 10,
        post_window_sec: int = 300,
        q_dimensions: Optional[Dict[str, float]] = None,
    ) -> Dict[str, object]:
        """Explains anomalies on `service` using TreeSHAP attributions."""
        timestamps = np.array(case.timestamps)
        inject_time = case.inject_time
        T = len(timestamps)
        all_columns = list(case.metrics_data.keys())
        M = len(all_columns)

        if mask is None:
            mask = np.ones((T, M), dtype=np.uint8)

        # Pre/post temporal masks
        pre_mask = timestamps < (inject_time - pre_buffer_sec)
        post_mask = (timestamps >= inject_time) & (timestamps <= inject_time + post_window_sec)

        if np.sum(pre_mask) < 5:
            cutoff = int(T * 0.3)
            pre_mask = np.zeros(T, dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            cutoff = int(T * 0.5)
            post_mask = np.zeros(T, dtype=bool)
            post_mask[cutoff:] = True

        grouped = group_metrics_by_service(case.metrics_data)
        service_metrics = grouped.get(service, {})

        if not service_metrics:
            return {
                "service": service,
                "metric_attributions": {},
                "ranked_metrics": [],
                "top3_metrics": [],
                "reliability_score": 1.0,
                "low_reliability_warning": False,
                "gini_sparsity": 0.0,
            }

        sorted_metric_names = sorted(list(service_metrics.keys()))
        col_to_idx = {c: i for i, c in enumerate(all_columns)}

        # Build feature matrices
        val_matrix = np.column_stack([np.array(service_metrics[c], dtype=float) for c in sorted_metric_names])
        mask_matrix = np.column_stack([mask[:, col_to_idx[c]] for c in sorted_metric_names])

        if self.mode == "naive":
            # Imputed values only
            X_all = val_matrix
        else:
            # Constrained-xAIOps: [X_imp, M_mask, delta_C_col]
            # Pre-fault completeness per column
            c_pre_cols = np.mean(mask_matrix[pre_mask], axis=0) if np.sum(pre_mask) > 0 else np.ones(len(sorted_metric_names))
            delta_c_matrix = np.maximum(0.0, c_pre_cols - mask_matrix)
            X_all = np.column_stack([val_matrix, mask_matrix, delta_c_matrix])

        X_pre = X_all[pre_mask]
        X_post = X_all[post_mask]

        # Labels: 0 for pre-fault (normal), 1 for post-fault (anomaly)
        y_pre = np.zeros(len(X_pre), dtype=int)
        y_post = np.ones(len(X_post), dtype=int)

        X_train = np.vstack([X_pre, X_post])
        y_train = np.concatenate([y_pre, y_post])

        # Train fast tree ensemble
        clf = ExtraTreesClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            random_state=self.seed,
        )
        clf.fit(X_train, y_train)

        # Compute exact TreeSHAP attributions on post-fault window
        explainer = shap.TreeExplainer(clf)
        raw_shap = explainer.shap_values(X_post)

        # Handle diverse shap return structures across versions
        if isinstance(raw_shap, list) and len(raw_shap) >= 2:
            shap_post = raw_shap[1]
        elif isinstance(raw_shap, np.ndarray) and raw_shap.ndim == 3 and raw_shap.shape[2] >= 2:
            shap_post = raw_shap[:, :, 1]
        elif isinstance(raw_shap, np.ndarray):
            shap_post = raw_shap
        else:
            shap_post = np.zeros_like(X_post)

        # Mean absolute attribution per feature
        mean_abs_attributions = np.mean(np.abs(shap_post), axis=0)
        K = len(sorted_metric_names)

        # Fold attributions back to physical metrics
        metric_scores: Dict[str, float] = {}
        if self.mode == "naive":
            for i, col in enumerate(sorted_metric_names):
                metric_scores[col] = float(mean_abs_attributions[i])
        else:
            for i, col in enumerate(sorted_metric_names):
                val_attr = mean_abs_attributions[i]
                mask_attr = mean_abs_attributions[K + i] if len(mean_abs_attributions) > K + i else 0.0
                delta_attr = mean_abs_attributions[2 * K + i] if len(mean_abs_attributions) > 2 * K + i else 0.0
                metric_scores[col] = float(val_attr + mask_attr + delta_attr)

        total_score = sum(metric_scores.values())
        if total_score > 0:
            norm_attributions = {c: float(s / total_score) for c, s in metric_scores.items()}
        else:
            norm_attributions = {c: 1.0 / K for c in sorted_metric_names}

        # Rank metrics in descending order of attribution
        ranked = sorted(norm_attributions.items(), key=lambda x: x[1], reverse=True)
        ranked_metrics = [c for c, _ in ranked]
        top3_metrics = ranked_metrics[:3]

        # Explanation Reliability Badge: R_exp = mean_{m in top3} Q_m
        q_scores = []
        for c in top3_metrics:
            if q_dimensions is not None and c in q_dimensions:
                q_scores.append(q_dimensions[c])
            else:
                c_idx = col_to_idx.get(c, 0)
                post_comp = float(np.mean(mask[post_mask, c_idx])) if np.sum(post_mask) > 0 else 1.0
                q_scores.append(post_comp)

        r_exp = float(np.mean(q_scores)) if q_scores else 1.0
        r_exp = float(np.clip(r_exp, 0.0, 1.0))
        low_reliability = bool(r_exp < 0.70)

        gini = compute_gini_index(list(norm_attributions.values()))

        return {
            "service": service,
            "metric_attributions": norm_attributions,
            "ranked_metrics": ranked_metrics,
            "top3_metrics": top3_metrics,
            "reliability_score": round(r_exp, 4),
            "low_reliability_warning": low_reliability,
            "gini_sparsity": round(gini, 4),
        }
