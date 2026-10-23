"""Service Incident Correlation Engine across Call-Graph Topology.

Groups active anomaly symptoms and MNAR blackout signals along service invocation edges,
localizing propagation subgraphs and candidate root-cause clusters.
"""

from typing import Dict, List, Optional, Set
from src.correlation.topology import OnlineBoutiqueTopology, _TOPOLOGY_SINGLETON
from src.schemas import SelectiveDecision, TrustEvaluation


def correlate_incident(
    decisions: Dict[str, SelectiveDecision],
    trust_eval: TrustEvaluation,
    topology: Optional[OnlineBoutiqueTopology] = None,
) -> Dict[str, object]:
    """Correlates selective decisions across the call-graph topology.

    Groups active anomalies (HIGH_CONFIDENCE_INCIDENT) and blackouts (ESCALATE_MNAR_BLACKOUT)
    into connected incident subgraphs and identifies candidate root causes.
    """
    topo = topology or _TOPOLOGY_SINGLETON

    active_incidents = [
        s for s, d in decisions.items() if d.outcome == "HIGH_CONFIDENCE_INCIDENT"
    ]
    escalated_blackouts = [
        s for s, d in decisions.items() if d.outcome == "ESCALATE_MNAR_BLACKOUT"
    ]
    involved_nodes = set(active_incidents) | set(escalated_blackouts)

    # 1. Connected components among involved nodes
    visited: Set[str] = set()
    clusters: List[List[str]] = []

    for node in sorted(list(involved_nodes)):
        if node not in visited:
            cluster: List[str] = []
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                cluster.append(curr)
                for neighbor in topo.get_neighbors(curr):
                    if neighbor in involved_nodes and neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(sorted(cluster))

    # 2. Score candidate root causes within each cluster
    candidate_root_causes: List[str] = []
    for cluster in clusters:
        # Prioritize escalated blackouts (crashed services causing cascade)
        blackouts = [s for s in cluster if s in escalated_blackouts]
        if blackouts:
            candidate_root_causes.extend(blackouts)
        else:
            # Rank by anomaly score weighted by trust
            ranked = sorted(
                cluster,
                key=lambda s: decisions[s].anomaly_score * decisions[s].trust_score,
                reverse=True,
            )
            if ranked:
                candidate_root_causes.append(ranked[0])

    return {
        "active_incidents": active_incidents,
        "escalated_blackouts": escalated_blackouts,
        "involved_nodes": sorted(list(involved_nodes)),
        "clusters": clusters,
        "candidate_root_causes": candidate_root_causes,
    }
