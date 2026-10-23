"""Reliability-Weighted BARO with MNAR Blackout Prior.

Incorporates multi-dimensional Telemetry Trust Scores and incident-driven MNAR
blackout priors to recover root-cause localization when failing microservices
suffer severe sensor dropout or pod crashes.
"""

import time
from typing import Dict, List, Literal, Optional, Sequence
import numpy as np

from src.correlation.topology import BaseTopology, OnlineBoutiqueTopology, _TOPOLOGY_SINGLETON, get_topology
from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    extract_services_from_metrics,
    get_system_services,
    group_metrics_by_service,
)
from src.quality.dimensions import compute_all_dimensions
from src.quality.trust_score import TelemetryTrustEvaluator
from src.schemas import RCAResult, TelemetryCase, TrustEvaluation


class TrustWeightedBARO:
    """Trust-Weighted BARO Root Cause Localizer with MNAR Blackout Prior.

    Combines:
    1. Observed-only non-parametric robust scoring weighted by telemetry trust:
       S_obs_baro(s)
    2. Topological MNAR Blackout Prior:
       P_mnar(s) = lambda_mnar * (1.0 - T(s) + delta_T_loc(s)) * (delta_C(s) + delta_T_loc(s)) * UpstreamSymptom(s)
    Yielding composite root cause score:
       S_RCA(s) = T_service(s) * S_obs_baro_norm(s) + P_mnar(s)
    """

    def __init__(
        self,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        aggregation: Literal["max", "mean"] = "max",
        lambda_mnar: float = 3.5,
        imputation_certainty: float = 0.8,
        topology: Optional[BaseTopology] = None,
    ):
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.aggregation = aggregation
        self.lambda_mnar = lambda_mnar
        self.imputation_certainty = imputation_certainty
        self.topology = topology
        self.trust_evaluator = TelemetryTrustEvaluator()

    def score_metric_observed(
        self,
        pre_vals: np.ndarray,
        post_vals: np.ndarray,
        post_mask_m: Optional[np.ndarray] = None,
    ) -> float:
        """Computes observed-only robust deviation score for a single metric."""
        if len(pre_vals) == 0 or len(post_vals) == 0:
            return 0.0

        median_pre = float(np.median(pre_vals))
        q75, q25 = np.percentile(pre_vals, [75, 25])
        iqr_pre = float(q75 - q25)
        denom = iqr_pre + 1e-4

        if post_mask_m is not None and len(post_mask_m) == len(post_vals):
            obs_indices = post_mask_m == 1
            c_m = float(np.mean(post_mask_m))
            if np.sum(obs_indices) > 0:
                s_obs = float(np.abs(np.median(post_vals[obs_indices]) - median_pre) / denom)
            else:
                s_obs = 0.0
            s_imp = float(np.abs(np.median(post_vals) - median_pre) / denom)
            score = c_m * s_obs + (1.0 - c_m) * self.imputation_certainty * s_imp
        else:
            score = float(np.abs(np.median(post_vals) - median_pre) / denom)

        return float(score) if not np.isnan(score) else 0.0

    def localize(
        self,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        trust_eval: Optional[TrustEvaluation] = None,
        enable_mnar_prior: bool = True,
    ) -> RCAResult:
        """Runs Trust-Weighted BARO localization on a single TelemetryCase."""
        start_time = time.perf_counter()

        timestamps = np.array(case.timestamps)
        inject_time = case.inject_time
        T = len(timestamps)
        columns = list(case.metrics_data.keys())
        M = len(columns)

        if mask is None:
            mask = np.ones((T, M), dtype=np.uint8)

        # Zero-leakage temporal slices
        pre_mask = timestamps < (inject_time - self.pre_fault_buffer_sec)
        post_mask = (timestamps >= inject_time) & (
            timestamps <= inject_time + self.post_fault_window_sec
        )

        if np.sum(pre_mask) < 5:
            cutoff = int(T * 0.3)
            pre_mask = np.zeros(T, dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            post_mask = timestamps >= inject_time
            if np.sum(post_mask) < 5:
                cutoff = int(T * 0.5)
                post_mask = np.zeros(T, dtype=bool)
                post_mask[cutoff:] = True

        # 1. Compute trust evaluation if not provided
        if trust_eval is None:
            trust_eval = self.trust_evaluator.evaluate_case(case, mask=mask)

        # Resolve system topology and services
        topo = self.topology or get_topology(case.system, case=case)
        all_services = get_system_services(case.system, case.metrics_data)
        if not all_services:
            all_services = list(topo.services)

        # 2. Compute observed-only BARO scores per metric and service
        grouped = group_metrics_by_service(case.metrics_data)
        col_to_idx = {c: i for i, c in enumerate(columns)}

        service_obs_scores: Dict[str, float] = {}
        pre_completeness: Dict[str, float] = {}
        post_completeness: Dict[str, float] = {}

        for s in all_services:
            metrics = grouped.get(s, {})
            if not metrics:
                service_obs_scores[s] = 0.0
                pre_completeness[s] = 1.0
                post_completeness[s] = 1.0
                continue

            s_indices = [col_to_idx[c] for c in metrics.keys() if c in col_to_idx]
            if s_indices:
                pre_comp_s = float(np.mean(mask[pre_mask][:, s_indices]))
                post_comp_s = float(np.mean(mask[post_mask][:, s_indices]))
            else:
                pre_comp_s = 1.0
                post_comp_s = 1.0

            pre_completeness[s] = pre_comp_s
            post_completeness[s] = post_comp_s

            metric_scores: List[float] = []
            for col, values in metrics.items():
                arr = np.array(values, dtype=float)
                c_idx = col_to_idx.get(col)
                m_post = mask[post_mask, c_idx] if c_idx is not None else None
                s_m = self.score_metric_observed(
                    pre_vals=arr[pre_mask],
                    post_vals=arr[post_mask],
                    post_mask_m=m_post,
                )
                metric_scores.append(s_m)

            if metric_scores:
                if self.aggregation == "max":
                    service_obs_scores[s] = float(np.max(metric_scores))
                else:
                    service_obs_scores[s] = float(np.mean(metric_scores))
            else:
                service_obs_scores[s] = 0.0

        # Normalize observed BARO scores to [0, 1]
        max_obs = max(service_obs_scores.values()) if service_obs_scores else 0.0
        norm_obs_scores: Dict[str, float] = {
            s: service_obs_scores[s] / (max_obs + 1e-4)
            for s in all_services
        }

        # 3. Compute post-fault dimensions across metrics to derive Effective Information Completeness
        data_matrix = np.column_stack([np.array(case.metrics_data[c], dtype=float) for c in columns])
        post_cutoff = max(5, np.where(post_mask)[0][0] if np.any(post_mask) else int(T * 0.5))
        dims_post = compute_all_dimensions(
            mask=mask,
            metrics_data=data_matrix,
            columns=columns,
            timestamps=case.timestamps,
            pre_fault_cutoff=post_cutoff,
            window_slice=slice(post_cutoff, T),
        )

        post_eff_completeness: Dict[str, float] = {}
        for s in all_services:
            metrics = grouped.get(s, {})
            if not metrics:
                post_eff_completeness[s] = 1.0
                continue
            s_indices = [col_to_idx[c] for c in metrics.keys() if c in col_to_idx]
            if s_indices:
                c_post_s = post_completeness.get(s, 1.0)
                l_post_s = float(np.mean(dims_post["L"][s_indices]))
                s_post_s = float(np.mean(dims_post["S"][s_indices]))
                v_post_s = float(np.mean(dims_post["V"][s_indices]))
                c_eff_post_s = float(np.clip(c_post_s * l_post_s * s_post_s * v_post_s, 0.0, 1.0))
            else:
                c_eff_post_s = 1.0
            post_eff_completeness[s] = c_eff_post_s

        # 4. Compute peer median trust and localized trust deficit
        all_trust_vals = [trust_eval.service_scores.get(s, 1.0) for s in all_services]
        peer_median_trust = float(np.median(all_trust_vals)) if all_trust_vals else 1.0

        # 5. Compute composite Constrained-xAIOps Root-Cause Score
        final_scores: Dict[str, float] = {}

        for s in all_services:
            t_s = trust_eval.service_scores.get(s, 1.0)
            c_eff_s = post_eff_completeness.get(s, post_completeness.get(s, 1.0))
            delta_C_eff_s = max(0.0, pre_completeness.get(s, 1.0) - c_eff_s)
            delta_T_loc_s = max(0.0, peer_median_trust - t_s)

            # Upstream symptom spike across 1-hop neighbors
            neighbors = topo.get_neighbors(s)
            neighbor_symptoms = [
                trust_eval.service_scores.get(u, 1.0) * norm_obs_scores.get(u, 0.0)
                for u in neighbors
            ]
            upstream_symptom_s = max(neighbor_symptoms) if neighbor_symptoms else 0.0

            # MNAR Blackout Prior with Effective Information Completeness Drop
            has_blackout = (delta_C_eff_s > 0.08) or (c_eff_s < 0.80 and delta_T_loc_s > 0.05)
            if enable_mnar_prior and has_blackout:
                blackout_intensity = max(delta_C_eff_s, delta_T_loc_s)
                p_mnar_s = (
                    self.lambda_mnar
                    * (1.0 - t_s + delta_T_loc_s)
                    * (1.0 + 3.0 * blackout_intensity)
                    * (delta_C_eff_s + delta_T_loc_s)
                    * max(0.25, upstream_symptom_s)
                )
            else:
                p_mnar_s = 0.0

            # Composite Root Cause Score
            score_rca = t_s * norm_obs_scores.get(s, 0.0) + p_mnar_s
            final_scores[s] = float(score_rca)

        ranked = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
        ranked_services = [s for s, _ in ranked]
        ranked_scores = [score for _, score in ranked]

        gt = case.root_cause_service
        if gt in ranked_services:
            rank = ranked_services.index(gt) + 1
        else:
            rank = len(ranked_services) + 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return RCAResult(
            case_id=case.case_id,
            ranked_services=ranked_services,
            scores=ranked_scores,
            ground_truth_service=gt,
            hit_at_1=(rank == 1),
            hit_at_3=(rank <= 3),
            hit_at_5=(rank <= 5),
            reciprocal_rank=float(1.0 / rank),
            runtime_ms=round(elapsed_ms, 3),
        )
