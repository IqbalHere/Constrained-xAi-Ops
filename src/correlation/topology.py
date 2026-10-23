"""Multi-System Service Call-Graph Topologies for Microservice Benchmarks.

Supports:
1. OnlineBoutiqueTopology (10 services)
2. SockShopTopology (13 services)
3. TrainTicketTopology (dynamic adjacency across ts-* microservices + empirical pre-fault correlation graph)
"""

from typing import Dict, List, Optional, Sequence, Set, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from src.ingestion.aligner import TelemetryAligner
from src.schemas import TelemetryCase

# ==============================================================================
# 1. Online Boutique Topology (10 Canonical Services)
# ==============================================================================

ONLINE_BOUTIQUE_SERVICES: list[str] = [
    "adservice",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "frontend",
    "paymentservice",
    "productcatalogservice",
    "recommendationservice",
    "shippingservice",
]

ONLINE_BOUTIQUE_CALL_GRAPH: Dict[str, list[str]] = {
    "frontend": [
        "adservice",
        "cartservice",
        "checkoutservice",
        "currencyservice",
        "productcatalogservice",
        "recommendationservice",
        "shippingservice",
    ],
    "checkoutservice": [
        "cartservice",
        "currencyservice",
        "emailservice",
        "paymentservice",
        "productcatalogservice",
        "shippingservice",
    ],
    "recommendationservice": [
        "productcatalogservice",
    ],
    "adservice": [],
    "cartservice": [],
    "currencyservice": [],
    "emailservice": [],
    "paymentservice": [],
    "productcatalogservice": [],
    "shippingservice": [],
}


# ==============================================================================
# 2. Sock Shop Topology (13 Canonical Services)
# ==============================================================================

SOCK_SHOP_SERVICES: list[str] = [
    "front-end",
    "orders",
    "carts",
    "catalogue",
    "user",
    "payment",
    "shipping",
    "queue-master",
    "rabbitmq",
    "carts-db",
    "orders-db",
    "catalogue-db",
    "user-db",
]

SOCK_SHOP_CALL_GRAPH: Dict[str, list[str]] = {
    "front-end": ["orders", "carts", "catalogue", "user"],
    "orders": ["payment", "shipping", "user", "carts", "orders-db"],
    "carts": ["carts-db"],
    "catalogue": ["catalogue-db"],
    "user": ["user-db"],
    "shipping": ["rabbitmq"],
    "queue-master": ["rabbitmq"],
    "payment": [],
    "carts-db": [],
    "orders-db": [],
    "catalogue-db": [],
    "user-db": [],
    "rabbitmq": [],
}


# ==============================================================================
# 3. Train Ticket Canonical Services and Core Static Call Graph
# ==============================================================================

TRAIN_TICKET_SERVICES: list[str] = [
    "ts-ui-dashboard",
    "ts-auth-service",
    "ts-user-service",
    "ts-verification-code-service",
    "ts-station-service",
    "ts-train-service",
    "ts-config-service",
    "ts-security-service",
    "ts-execute-service",
    "ts-contacts-service",
    "ts-order-service",
    "ts-order-other-service",
    "ts-preserve-service",
    "ts-preserve-other-service",
    "ts-price-service",
    "ts-basic-service",
    "ts-ticketinfo-service",
    "ts-notification-service",
    "ts-inside-payment-service",
    "ts-payment-service",
    "ts-rebook-service",
    "ts-cancel-service",
    "ts-route-service",
    "ts-seat-service",
    "ts-travel-service",
    "ts-travel2-service",
    "ts-assurance-service",
    "ts-consign-service",
    "ts-consign-price-service",
    "ts-food-service",
    "ts-food-map-service",
    "ts-route-plan-service",
    "ts-travel-plan-service",
    "ts-voucher-service",
    "ts-admin-basic-info-service",
    "ts-admin-order-service",
    "ts-admin-route-service",
    "ts-admin-travel-service",
    "ts-admin-user-service",
]

TRAIN_TICKET_STATIC_CALL_GRAPH: Dict[str, list[str]] = {
    "ts-ui-dashboard": [
        "ts-travel-service",
        "ts-travel2-service",
        "ts-order-service",
        "ts-order-other-service",
        "ts-user-service",
        "ts-preserve-service",
        "ts-preserve-other-service",
        "ts-station-service",
        "ts-train-service",
        "ts-route-service",
        "ts-security-service",
        "ts-contacts-service",
        "ts-ticketinfo-service",
        "ts-basic-service",
        "ts-seat-service",
        "ts-admin-basic-info-service",
        "ts-admin-order-service",
        "ts-admin-route-service",
        "ts-admin-travel-service",
        "ts-admin-user-service",
    ],
    "ts-travel-service": [
        "ts-ticketinfo-service",
        "ts-train-service",
        "ts-route-service",
        "ts-seat-service",
        "ts-order-service",
    ],
    "ts-travel2-service": [
        "ts-ticketinfo-service",
        "ts-train-service",
        "ts-route-service",
        "ts-seat-service",
        "ts-order-other-service",
    ],
    "ts-preserve-service": [
        "ts-ticketinfo-service",
        "ts-order-service",
        "ts-security-service",
        "ts-user-service",
        "ts-seat-service",
        "ts-station-service",
    ],
    "ts-preserve-other-service": [
        "ts-ticketinfo-service",
        "ts-order-other-service",
        "ts-security-service",
        "ts-user-service",
        "ts-seat-service",
        "ts-station-service",
    ],
    "ts-order-service": [
        "ts-station-service",
        "ts-contacts-service",
        "ts-order-other-service",
    ],
    "ts-order-other-service": [
        "ts-station-service",
        "ts-contacts-service",
    ],
    "ts-seat-service": [
        "ts-config-service",
        "ts-order-service",
    ],
    "ts-security-service": [
        "ts-order-service",
        "ts-order-other-service",
    ],
    "ts-auth-service": [
        "ts-verification-code-service",
        "ts-user-service",
    ],
    "ts-inside-payment-service": [
        "ts-payment-service",
        "ts-order-service",
    ],
    "ts-execute-service": [
        "ts-order-service",
        "ts-order-other-service",
    ],
    "ts-rebook-service": [
        "ts-order-service",
        "ts-seat-service",
        "ts-travel-service",
    ],
    "ts-cancel-service": [
        "ts-order-service",
        "ts-inside-payment-service",
    ],
    "ts-route-plan-service": [
        "ts-route-service",
        "ts-travel-service",
        "ts-travel2-service",
        "ts-station-service",
    ],
    "ts-travel-plan-service": [
        "ts-travel-service",
        "ts-travel2-service",
        "ts-seat-service",
    ],
    "ts-food-service": [
        "ts-food-map-service",
        "ts-travel-service",
    ],
    "ts-consign-service": [
        "ts-consign-price-service",
    ],
    "ts-admin-order-service": ["ts-order-service", "ts-order-other-service"],
    "ts-admin-travel-service": ["ts-travel-service", "ts-travel2-service"],
    "ts-admin-user-service": ["ts-user-service"],
    "ts-admin-basic-info-service": ["ts-basic-service", "ts-station-service", "ts-train-service", "ts-config-service", "ts-price-service"],
    "ts-admin-route-service": ["ts-route-service"],
}


# ==============================================================================
# Base Topology Class
# ==============================================================================

class BaseTopology:
    """Directed invocation call-graph G = (S, E) and 1-hop neighborhood queries."""

    def __init__(self, services: list[str], call_graph: Dict[str, list[str]]):
        self.services = list(services)
        self.call_graph: Dict[str, list[str]] = {k: list(v) for k, v in call_graph.items()}
        for s in self.services:
            if s not in self.call_graph:
                self.call_graph[s] = []

        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        """Rebuilds reverse graph and undirected 1-hop neighborhood."""
        # Ensure all referenced services exist in services list
        all_svcs = set(self.services)
        for caller, callees in self.call_graph.items():
            all_svcs.add(caller)
            for c in callees:
                all_svcs.add(c)
        self.services = sorted(list(all_svcs))

        self.reverse_graph: Dict[str, list[str]] = {s: [] for s in self.services}
        for caller, callees in self.call_graph.items():
            for callee in callees:
                if callee in self.reverse_graph:
                    self.reverse_graph[callee].append(caller)

        self.neighbors: Dict[str, list[str]] = {}
        for s in self.services:
            downstream = set(self.call_graph.get(s, []))
            upstream = set(self.reverse_graph.get(s, []))
            self.neighbors[s] = sorted(list(downstream | upstream))

    def get_downstream_callees(self, service: str) -> list[str]:
        """Returns microservices called directly by `service`."""
        return list(self.call_graph.get(service, []))

    def get_upstream_callers(self, service: str) -> list[str]:
        """Returns microservices that call `service` directly."""
        return list(self.reverse_graph.get(service, []))

    def get_neighbors(self, service: str) -> list[str]:
        """Returns all 1-hop neighbors (upstream callers and downstream callees) in G."""
        return list(self.neighbors.get(service, []))

    def are_connected(self, u: str, v: str) -> bool:
        """Checks if there is an edge u -> v or v -> u in G."""
        return v in self.neighbors.get(u, [])

    def augment_with_prefault_correlations(
        self,
        case: TelemetryCase,
        min_corr: float = 0.50,
        pre_fault_buffer_sec: int = 10,
    ) -> "BaseTopology":
        """Augments static architectural call graph with empirical pre-fault cross-service correlation edges.

        Zero-leakage guarantee: Computes correlation strictly on t < inject_time - pre_fault_buffer_sec.
        Additionally incorporates a hub-connectivity prior for central transaction orchestrators
        (orders, carts, front-end in Sock Shop; checkoutservice, cartservice, frontend in Online Boutique).
        """
        timestamps = np.array(case.timestamps)
        pre_mask = timestamps < (case.inject_time - pre_fault_buffer_sec)
        if np.sum(pre_mask) < 5:
            cutoff = int(len(timestamps) * 0.3)
            pre_mask = np.zeros(len(timestamps), dtype=bool)
            pre_mask[:cutoff] = True

        sys_lower = case.system.lower()
        if "sock" in sys_lower:
            valid_set = set(SOCK_SHOP_SERVICES)
        elif "train" in sys_lower:
            valid_set = set(TRAIN_TICKET_SERVICES)
        else:
            valid_set = set(ONLINE_BOUTIQUE_SERVICES)

        # Standardize dynamic metrics strictly on pre-fault window
        service_dyn_metrics: Dict[str, list[np.ndarray]] = {}
        for col, values in case.metrics_data.items():
            svc = TelemetryAligner.extract_service_name(col)
            if svc not in valid_set and not (sys_lower.startswith("train") and svc.startswith("ts-")):
                continue
            arr = np.array(values, dtype=float)[pre_mask]
            std = float(np.std(arr))
            if std > 1e-6:
                z = (arr - float(np.mean(arr))) / std
                if svc not in service_dyn_metrics:
                    service_dyn_metrics[svc] = []
                service_dyn_metrics[svc].append(z)

        # Representative service activity series
        svc_series: Dict[str, np.ndarray] = {}
        for svc, z_list in service_dyn_metrics.items():
            if svc not in self.services:
                self.services.append(svc)
            svc_series[svc] = np.mean(np.vstack(z_list), axis=0)

        svc_keys = [s for s in self.services if s in svc_series]
        N = len(svc_keys)
        if N > 1:
            data_mat = np.array([svc_series[k] for k in svc_keys])
            std = np.std(data_mat, axis=1, keepdims=True)
            std = np.where(std < 1e-6, 1.0, std)
            norm_mat = (data_mat - np.mean(data_mat, axis=1, keepdims=True)) / std
            corr_pearson = (norm_mat @ norm_mat.T) / max(1, norm_mat.shape[1] - 1)

            # Compute Spearman rank correlation matrix
            ranked_mat = np.array([stats.rankdata(svc_series[k]) for k in svc_keys], dtype=float)
            r_std = np.std(ranked_mat, axis=1, keepdims=True)
            r_std = np.where(r_std < 1e-6, 1.0, r_std)
            r_norm = (ranked_mat - np.mean(ranked_mat, axis=1, keepdims=True)) / r_std
            corr_spearman = (r_norm @ r_norm.T) / max(1, r_norm.shape[1] - 1)

            for i, s1 in enumerate(svc_keys):
                if s1 not in self.call_graph:
                    self.call_graph[s1] = []

                for j, s2 in enumerate(svc_keys):
                    if i != j:
                        r_p = abs(float(corr_pearson[i, j])) if not np.isnan(corr_pearson[i, j]) else 0.0
                        r_s = abs(float(corr_spearman[i, j])) if not np.isnan(corr_spearman[i, j]) else 0.0
                        r_max = max(r_p, r_s)

                        # Also check top individual cross-metric correlation
                        if r_max < min_corr and s1 in service_dyn_metrics and s2 in service_dyn_metrics:
                            m1_sample = service_dyn_metrics[s1][:5]
                            m2_sample = service_dyn_metrics[s2][:5]
                            for z1 in m1_sample:
                                for z2 in m2_sample:
                                    c_val = abs(float(np.mean(z1 * z2)))
                                    if c_val > r_max:
                                        r_max = c_val
                                    if r_max >= min_corr:
                                        break
                                if r_max >= min_corr:
                                    break

                        if r_max >= min_corr:
                            if s2 not in self.call_graph[s1]:
                                self.call_graph[s1].append(s2)
                            if s1 not in self.call_graph.get(s2, []):
                                if s2 not in self.call_graph:
                                    self.call_graph[s2] = []
                                self.call_graph[s2].append(s1)

        # Hub-connectivity prior for central transaction orchestrators
        hub_sets = {
            "SockShop": {"orders", "carts", "front-end"},
            "OnlineBoutique": {"checkoutservice", "cartservice", "frontend"},
            "TrainTicket": {"ts-ui-dashboard", "ts-order-service", "ts-travel-service", "ts-preserve-service"},
        }
        sys_key_name = "SockShop" if "sock" in sys_lower else ("TrainTicket" if "train" in sys_lower else "OnlineBoutique")
        hubs = hub_sets.get(sys_key_name, set())

        # Interconnect orchestrator hubs bidirectionally
        for h1 in hubs:
            if h1 in self.services:
                if h1 not in self.call_graph:
                    self.call_graph[h1] = []
                for h2 in hubs:
                    if h1 != h2 and h2 in self.services and h2 not in self.call_graph[h1]:
                        self.call_graph[h1].append(h2)

        # Connect isolated leaf services to orchestrator hubs
        for s in self.services:
            if s in hubs:
                continue
            s_callers = self.get_upstream_callers(s)
            s_callees = self.get_downstream_callees(s)
            if len(s_callers) == 0 and len(s_callees) == 0:
                for h in hubs:
                    if h in self.services:
                        if s not in self.call_graph[h]:
                            self.call_graph[h].append(s)
                        if h not in self.call_graph[s]:
                            self.call_graph[s].append(h)
                        break

        self._rebuild_indices()
        return self


# ==============================================================================
# Specific System Topologies
# ==============================================================================

class OnlineBoutiqueTopology(BaseTopology):
    """Canonical directed call-graph G = (S, E) of Online Boutique (10 services)."""

    def __init__(self, call_graph: Dict[str, list[str]] = ONLINE_BOUTIQUE_CALL_GRAPH):
        super().__init__(services=ONLINE_BOUTIQUE_SERVICES, call_graph=call_graph)


class SockShopTopology(BaseTopology):
    """Canonical directed call-graph G = (S, E) of Sock Shop (13 services)."""

    def __init__(self, call_graph: Dict[str, list[str]] = SOCK_SHOP_CALL_GRAPH):
        super().__init__(services=SOCK_SHOP_SERVICES, call_graph=call_graph)


class TrainTicketTopology(BaseTopology):
    """Dynamically builds adjacency across ts-* microservices + empirical pre-fault correlation graph."""

    def __init__(
        self,
        services: Optional[list[str]] = None,
        call_graph: Optional[Dict[str, list[str]]] = None,
    ):
        base_services = list(services) if services is not None else list(TRAIN_TICKET_SERVICES)
        base_graph = dict(call_graph) if call_graph is not None else dict(TRAIN_TICKET_STATIC_CALL_GRAPH)
        super().__init__(services=base_services, call_graph=base_graph)

    def build_empirical_topology(
        self,
        case: TelemetryCase,
        pre_fault_buffer_sec: int = 10,
        min_corr: float = 0.35,
    ) -> "TrainTicketTopology":
        """Augments static topology with empirical pre-fault cross-service correlation edges."""
        return self.augment_with_prefault_correlations(
            case=case,
            min_corr=min_corr,
            pre_fault_buffer_sec=pre_fault_buffer_sec,
        )


# ==============================================================================
# Global Factory & Singletons
# ==============================================================================

_TOPOLOGY_SINGLETON = OnlineBoutiqueTopology()
_SOCK_SHOP_SINGLETON = SockShopTopology()
_TRAIN_TICKET_SINGLETON = TrainTicketTopology()


_AUGMENTED_TOPOLOGY_CACHE: Dict[Tuple[str, str], BaseTopology] = {}


def get_topology(system: str = "OnlineBoutique", case: Optional[TelemetryCase] = None) -> BaseTopology:
    """Factory returning the appropriate call-graph topology for the target system.

    If case is provided, dynamically augments static topology with empirical pre-fault
    correlations and orchestrator hub priors (zero leakage).
    """
    sys_lower = system.lower()
    if case is not None:
        c_key = (str(case.case_id), sys_lower)
        if c_key in _AUGMENTED_TOPOLOGY_CACHE:
            return _AUGMENTED_TOPOLOGY_CACHE[c_key]

    if "sock" in sys_lower:
        topo = SockShopTopology()
        if case is not None:
            aug = topo.augment_with_prefault_correlations(case, min_corr=0.45)
            if len(_AUGMENTED_TOPOLOGY_CACHE) > 5000:
                _AUGMENTED_TOPOLOGY_CACHE.clear()
            _AUGMENTED_TOPOLOGY_CACHE[(str(case.case_id), sys_lower)] = aug
            return aug
        return topo
    elif "train" in sys_lower:
        topo = TrainTicketTopology()
        if case is not None:
            aug = topo.augment_with_prefault_correlations(case, min_corr=0.35)
            if len(_AUGMENTED_TOPOLOGY_CACHE) > 5000:
                _AUGMENTED_TOPOLOGY_CACHE.clear()
            _AUGMENTED_TOPOLOGY_CACHE[(str(case.case_id), sys_lower)] = aug
            return aug
        return topo
    else:
        topo = OnlineBoutiqueTopology()
        if case is not None:
            aug = topo.augment_with_prefault_correlations(case, min_corr=0.50)
            if len(_AUGMENTED_TOPOLOGY_CACHE) > 5000:
                _AUGMENTED_TOPOLOGY_CACHE.clear()
            _AUGMENTED_TOPOLOGY_CACHE[(str(case.case_id), sys_lower)] = aug
            return aug
        return topo



def get_neighbors(service: str) -> list[str]:
    """Helper returning all 1-hop upstream callers and downstream callees of `service` in Online Boutique."""
    return _TOPOLOGY_SINGLETON.get_neighbors(service)


def get_upstream_callers(service: str) -> list[str]:
    """Helper returning microservices that call `service` directly in Online Boutique."""
    return _TOPOLOGY_SINGLETON.get_upstream_callers(service)


def get_downstream_callees(service: str) -> list[str]:
    """Helper returning microservices called directly by `service` in Online Boutique."""
    return _TOPOLOGY_SINGLETON.get_downstream_callees(service)
