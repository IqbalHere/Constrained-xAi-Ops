"""Microservice correlation analysis and call graph topology."""

from src.correlation.correlator import correlate_incident
from src.correlation.topology import (
    ONLINE_BOUTIQUE_CALL_GRAPH,
    ONLINE_BOUTIQUE_SERVICES,
    OnlineBoutiqueTopology,
    get_downstream_callees,
    get_neighbors,
    get_upstream_callers,
)

__all__ = [
    "OnlineBoutiqueTopology",
    "ONLINE_BOUTIQUE_SERVICES",
    "ONLINE_BOUTIQUE_CALL_GRAPH",
    "get_neighbors",
    "get_upstream_callers",
    "get_downstream_callees",
    "correlate_incident",
]
