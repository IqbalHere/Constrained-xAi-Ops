"""Four-State Conformal Selective Prediction Gate.

Routes microservice telemetry into validated SelectiveDecision states:
1. ESCALATE_MNAR_BLACKOUT (Crashed service during active incident)
2. ABSTAIN_LOW_TRUST (Degraded telemetry without incident cascade)
3. HIGH_CONFIDENCE_INCIDENT (Reliable telemetry with anomaly symptoms)
4. NORMAL (Reliable telemetry within baseline parameters)
"""

from typing import Dict, Optional, Sequence
import numpy as np

from src.abstention.mnar_escalator import detect_mnar_blackout
from src.correlation.topology import BaseTopology, OnlineBoutiqueTopology, _TOPOLOGY_SINGLETON, get_topology
from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    extract_services_from_metrics,
    get_system_services,
    group_metrics_by_service,
)
from src.quality.dimensions import compute_all_dimensions
from src.schemas import SelectiveDecision, TelemetryCase, TrustEvaluation


def decide_service(
    case_id: str,
    service: str,
    anomaly_score: float,
    trust_score: float,
    is_mnar_blackout: bool,
    tau_T: float,
    tau_A: float = 0.35,
) -> SelectiveDecision:
    """Routes an individual service's evaluation into a validated SelectiveDecision contract."""
    if is_mnar_blackout:
        outcome = "ESCALATE_MNAR_BLACKOUT"
    elif trust_score < tau_T:
        outcome = "ABSTAIN_LOW_TRUST"
    elif anomaly_score >= tau_A:
        outcome = "HIGH_CONFIDENCE_INCIDENT"
    else:
        outcome = "NORMAL"

    return SelectiveDecision(
        case_id=case_id,
        service=service,
        outcome=outcome,
        anomaly_score=float(anomaly_score),
        trust_score=float(trust_score),
    )


class SelectiveGate:
    """Evaluates and routes all services in a TelemetryCase across the four selective states."""

    def __init__(
        self,
        tau_T: float = 0.70,
        tau_A: float = 0.35,
        enable_mnar_escalation: bool = True,
        topology: Optional[BaseTopology] = None,
    ):
        self.tau_T = tau_T
        self.tau_A = tau_A
        self.enable_mnar_escalation = enable_mnar_escalation
        self.topology = topology

    def compute_service_completeness(
        self,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        pre_buffer_sec: int = 10,
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        """Computes pre-fault and post-fault empirical completeness per service."""
        pre_c, post_c, _ = self.compute_service_effective_completeness(case, mask=mask, pre_buffer_sec=pre_buffer_sec)
        return pre_c, post_c

    def compute_service_effective_completeness(
        self,
        case: TelemetryCase,
        mask: Optional[np.ndarray] = None,
        pre_buffer_sec: int = 10,
    ) -> tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """Computes pre-fault, post-fault, and effective information completeness per service."""
        columns = list(case.metrics_data.keys())
        T = len(case.timestamps)
        M = len(columns)

        if mask is None:
            mask = np.ones((T, M), dtype=np.uint8)

        timestamps = np.array(case.timestamps)
        pre_mask = timestamps < (case.inject_time - pre_buffer_sec)
        post_mask = timestamps >= case.inject_time

        if np.sum(pre_mask) < 5:
            cutoff = int(T * 0.3)
            pre_mask = np.zeros(T, dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            cutoff = int(T * 0.5)
            post_mask = np.zeros(T, dtype=bool)
            post_mask[cutoff:] = True

        grouped = group_metrics_by_service(case.metrics_data)
        col_to_idx = {c: i for i, c in enumerate(columns)}

        topo = self.topology or get_topology(case.system, case=case)
        all_services = get_system_services(case.system, case.metrics_data)
        if not all_services:
            all_services = list(topo.services)

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

        pre_completeness: Dict[str, float] = {}
        post_completeness: Dict[str, float] = {}
        post_eff_completeness: Dict[str, float] = {}

        for s in all_services:
            s_cols = list(grouped.get(s, {}).keys())
            indices = [col_to_idx[c] for c in s_cols if c in col_to_idx]
            if not indices:
                pre_completeness[s] = 1.0
                post_completeness[s] = 1.0
                post_eff_completeness[s] = 1.0
                continue

            s_mask_pre = mask[pre_mask][:, indices]
            s_mask_post = mask[post_mask][:, indices]

            pre_comp_s = float(np.mean(s_mask_pre)) if s_mask_pre.size > 0 else 1.0
            post_comp_s = float(np.mean(s_mask_post)) if s_mask_post.size > 0 else 1.0

            l_post_s = float(np.mean(dims_post["L"][indices]))
            s_post_s = float(np.mean(dims_post["S"][indices]))
            v_post_s = float(np.mean(dims_post["V"][indices]))
            c_eff_post_s = float(np.clip(post_comp_s * l_post_s * s_post_s * v_post_s, 0.0, 1.0))

            pre_completeness[s] = pre_comp_s
            post_completeness[s] = post_comp_s
            post_eff_completeness[s] = c_eff_post_s

        return pre_completeness, post_completeness, post_eff_completeness

    def evaluate_case(
        self,
        case: TelemetryCase,
        trust_eval: TrustEvaluation,
        anomaly_scores: Dict[str, float],
        mask: Optional[np.ndarray] = None,
    ) -> Dict[str, SelectiveDecision]:
        """Evaluates all services in a TelemetryCase, returning SelectiveDecisions."""
        pre_comp, post_comp, post_eff_comp = self.compute_service_effective_completeness(case, mask=mask)

        topo = self.topology or get_topology(case.system, case=case)
        all_services = get_system_services(case.system, case.metrics_data)
        if not all_services:
            all_services = list(topo.services)

        timestamps = np.array(case.timestamps)
        pre_mask = timestamps < (case.inject_time - 10)
        post_mask = timestamps >= case.inject_time
        if np.sum(pre_mask) < 5:
            pre_mask = np.zeros(len(timestamps), dtype=bool)
            pre_mask[:int(len(timestamps) * 0.3)] = True
        if np.sum(post_mask) < 5:
            post_mask = np.zeros(len(timestamps), dtype=bool)
            post_mask[int(len(timestamps) * 0.5):] = True

        grouped = group_metrics_by_service(case.metrics_data)

        # Empirical neighbor symptom detection
        effective_anomaly_scores = dict(anomaly_scores)
        for s in all_services:
            s_cols = list(grouped.get(s, {}).keys())
            if s_cols:
                col_drifts = []
                for c in s_cols:
                    arr = np.array(case.metrics_data[c], dtype=float)
                    p_pre = arr[pre_mask]
                    p_post = arr[post_mask]
                    if len(p_pre) > 2 and len(p_post) > 2:
                        iqr = float(np.percentile(p_pre, 75) - np.percentile(p_pre, 25)) + 1e-4
                        med_shift = abs(float(np.median(p_post) - np.median(p_pre))) / iqr
                        col_drifts.append(med_shift)
                if col_drifts:
                    max_d = float(np.max(col_drifts))
                    s_emp = float(np.clip(max_d / 2.0, 0.0, 1.0))
                    effective_anomaly_scores[s] = max(effective_anomaly_scores.get(s, 0.0), s_emp)

        decisions: Dict[str, SelectiveDecision] = {}
        for s in all_services:
            t_s = trust_eval.service_scores.get(s, 1.0)
            a_s = effective_anomaly_scores.get(s, 0.0)

            is_blackout = False
            if self.enable_mnar_escalation:
                is_blackout = detect_mnar_blackout(
                    service=s,
                    trust_eval=trust_eval,
                    pre_completeness=pre_comp,
                    post_completeness=post_comp,
                    neighbor_anomaly_scores=effective_anomaly_scores,
                    tau_T=self.tau_T,
                    tau_A=self.tau_A,
                    topology=topo,
                    post_effective_completeness=post_eff_comp,
                )

            decisions[s] = decide_service(
                case_id=case.case_id,
                service=s,
                anomaly_score=a_s,
                trust_score=t_s,
                is_mnar_blackout=is_blackout,
                tau_T=self.tau_T,
                tau_A=self.tau_A,
            )

        return decisions
