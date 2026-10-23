"""Telemetry Trust Score Evaluator and Aggregator.

Implements the multi-dimensional Telemetry Trust Score with multiplicative floor:
  T_metric(m, w) = I(V(m, w) > 0) * I(C(m, w) > 0) * sum_{j=1}^5 w_j * d_j(m, w)
Aggregates to service-level T_service(s, w) and system-level T_sys(w),
producing an immutable Pydantic v2 TrustEvaluation contract.
"""

from typing import Dict, List, Literal, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    TelemetryAligner,
    extract_services_from_metrics,
    get_system_services,
    group_metrics_by_service,
)
from src.quality.dimensions import compute_all_dimensions
from src.quality.weights import get_equal_weights
from src.schemas import TelemetryCase, TrustEvaluation


class TelemetryTrustEvaluator:
    """Evaluates multi-dimensional telemetry trust scores over evaluation windows."""

    def __init__(
        self,
        weights: Optional[Sequence[float]] = None,
        nominal_dt: float = 1.0,
    ):
        self.weights = np.array(weights if weights is not None else get_equal_weights(), dtype=float)
        # Normalize weights
        s = np.sum(self.weights)
        if s > 0:
            self.weights = self.weights / s
        else:
            self.weights = get_equal_weights()
        self.nominal_dt = nominal_dt

    def evaluate_metric_scores(
        self,
        mask: np.ndarray,
        metrics_data: np.ndarray,
        columns: Sequence[str],
        timestamps: Sequence[int],
        pre_fault_cutoff: int,
        window_slice: Optional[slice] = None,
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Computes trust score for each individual metric column."""
        dims = compute_all_dimensions(
            mask=mask,
            metrics_data=metrics_data,
            columns=columns,
            timestamps=timestamps,
            pre_fault_cutoff=pre_fault_cutoff,
            window_slice=window_slice,
        )

        c = dims["C"]
        l = dims["L"]
        s = dims["S"]
        v = dims["V"]
        q = dims["Q"]

        # Multiplicative floor: if V == 0 or C == 0, score collapses to 0.0
        floor = (v > 0.0) & (c > 0.0)

        # Weighted combination: [w_C, w_L, w_S, w_V, w_Q]
        w = self.weights
        composite = (
            w[0] * c +
            w[1] * l +
            w[2] * s +
            w[3] * v +
            w[4] * q
        )

        t_metric = np.where(floor, composite, 0.0)
        t_metric = np.clip(t_metric, 0.0, 1.0)
        return t_metric, dims

    def evaluate_case(
        self,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        window_idx: int = 0,
        window_slice: Optional[slice] = None,
    ) -> TrustEvaluation:
        """Evaluates trust scores for a TelemetryCase across all microservices.

        Returns an immutable Pydantic v2 TrustEvaluation contract.
        """
        columns = list(case.metrics_data.keys())
        T = len(case.timestamps)
        M = len(columns)

        if mask is None:
            mask = np.ones((T, M), dtype=np.uint8)

        data_matrix = np.column_stack([np.array(case.metrics_data[c], dtype=float) for c in columns])

        # Pre-fault cutoff index
        timestamps = np.array(case.timestamps)
        inject_indices = np.where(timestamps >= case.inject_time)[0]
        inject_idx = int(inject_indices[0]) if len(inject_indices) > 0 else T // 2
        pre_fault_cutoff = max(5, inject_idx - 10)

        t_metric, dims = self.evaluate_metric_scores(
            mask=mask,
            metrics_data=data_matrix,
            columns=columns,
            timestamps=case.timestamps,
            pre_fault_cutoff=pre_fault_cutoff,
            window_slice=window_slice,
        )

        # Determine services for the target system
        system_services = get_system_services(case.system, case.metrics_data)

        # Group metrics by service and aggregate
        service_scores: Dict[str, float] = {}
        for s in system_services:
            matching_indices = [
                i for i, col in enumerate(columns)
                if TelemetryAligner.extract_service_name(col) == s
            ]
            if matching_indices:
                score = float(np.mean(t_metric[matching_indices]))
                service_scores[s] = round(float(np.clip(score, 0.0, 1.0)), 4)
            else:
                service_scores[s] = 1.0

        # System dimensions breakdown
        dim_summary = {
            "C": round(float(np.mean(dims["C"])), 4),
            "L": round(float(np.mean(dims["L"])), 4),
            "S": round(float(np.mean(dims["S"])), 4),
            "V": round(float(np.mean(dims["V"])), 4),
            "Q": round(float(np.mean(dims["Q"])), 4),
            "T_sys": round(float(np.mean(list(service_scores.values()))), 4),
        }

        return TrustEvaluation(
            case_id=case.case_id,
            window_idx=window_idx,
            service_scores=service_scores,
            dimensions=dim_summary,
        )
