"""Dual-Branch MNAR Crash-Distinction Escalator.

Resolves the MNAR Abstention Paradox: distinguishes uninformative random sensor
dropout (passive abstention) from incident-driven microservice crash blackouts
(active root-cause escalation) using localized trust deficit and neighbor symptom cascades.
"""

from typing import Dict, Optional
import numpy as np

from src.correlation.topology import BaseTopology, OnlineBoutiqueTopology, _TOPOLOGY_SINGLETON
from src.schemas import TrustEvaluation


def detect_mnar_blackout(
    service: str,
    trust_eval: TrustEvaluation,
    pre_completeness: Dict[str, float],
    post_completeness: Dict[str, float],
    neighbor_anomaly_scores: Dict[str, float],
    tau_T: float,
    tau_A: float = 0.35,
    topology: Optional[BaseTopology] = None,
    delta_trust_threshold: float = 0.05,
    delta_completeness_threshold: float = 0.15,
    post_completeness_floor: float = 0.75,
    post_effective_completeness: Optional[Dict[str, float]] = None,
) -> bool:
    """Detects whether a service's low trust is caused by an incident-driven MNAR crash.

    Uses Effective Information Completeness Drop:
      C_eff_post(s) = C_post(s) * L_post(s) * S_post(s) * V_post(s)
      delta_C_eff(s) = max(0.0, C_pre(s) - C_eff_post(s))

    Returns True if service exhibits:
    1. Localized trust drop or trust below tau_T.
    2. Substantial post-fault effective information completeness drop (delta_C_eff >= 0.15 or C_eff_post < 0.75).
    3. Reliable 1-hop neighbors in call-graph exhibiting active anomaly symptoms.
    """
    topo = topology or _TOPOLOGY_SINGLETON

    # 1. Effective Information Completeness Drop
    c_pre = pre_completeness.get(service, 1.0)
    c_post = post_completeness.get(service, 1.0)
    if post_effective_completeness is not None and service in post_effective_completeness:
        c_eff_post = post_effective_completeness[service]
    else:
        t_service = trust_eval.service_scores.get(service, 1.0)
        c_eff_post = min(c_post, c_post * t_service)

    delta_C_eff = max(0.0, c_pre - c_eff_post)

    # 2. Localized trust deficit relative to peers
    all_service_scores = list(trust_eval.service_scores.values())
    peer_median = float(np.median(all_service_scores)) if all_service_scores else 1.0
    t_service = trust_eval.service_scores.get(service, 1.0)
    delta_T_loc = max(0.0, peer_median - t_service)

    # 3. 1-hop neighbor anomaly severity weighted by neighbor trust
    neighbors = topo.get_neighbors(service)
    neighbor_severities = []
    for u in neighbors:
        t_u = trust_eval.service_scores.get(u, 1.0)
        a_u = neighbor_anomaly_scores.get(u, 0.0)
        neighbor_severities.append(t_u * a_u)

    A_neigh_max = max(neighbor_severities) if neighbor_severities else 0.0

    # Trigger dual-branch condition
    trust_compromised = (t_service < tau_T) or (delta_T_loc >= delta_trust_threshold)
    telemetry_dropped = (delta_C_eff >= delta_completeness_threshold) or (c_eff_post < post_completeness_floor)
    neighbors_symptomatic = A_neigh_max >= tau_A

    return bool(trust_compromised and telemetry_dropped and neighbors_symptomatic)
