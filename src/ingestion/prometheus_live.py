"""Live Prometheus Telemetry Loader and Bridge for Cloud-Native Testbed.

Queries Prometheus HTTP range vector APIs (/api/v1/query_range) across live Kubernetes
microservices (Online Boutique / Sock Shop / Train Ticket), parses metric series,
normalizes and aligns irregular telemetry, and constructs immutable TelemetryCase
instances with data_source_tag="LIVE_K8S_TESTBED".
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
import pandas as pd
import requests

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    TelemetryAligner,
    get_system_services,
)
from src.schemas import TelemetryCase, TrustEvaluation, SelectiveDecision
from src.quality.trust_score import TelemetryTrustEvaluator
from src.abstention.selective_gate import SelectiveGate

logger = logging.getLogger("PrometheusLiveLoader")

# Standard Prometheus metrics monitored in cloud-native testbed
DEFAULT_PROMETHEUS_METRICS = [
    "up",
    "container_cpu_usage_seconds_total",
    "container_memory_working_set_bytes",
    "container_network_receive_bytes_total",
    "container_network_transmit_bytes_total",
]


class PrometheusLiveLoader:
    """Queries Prometheus HTTP range API and converts payloads into TelemetryCase contracts."""

    def __init__(
        self,
        prometheus_url: str = "http://localhost:9090",
        namespace: str = "boutique",
        timeout_sec: int = 10,
    ):
        self.prometheus_url = prometheus_url.rstrip("/")
        self.namespace = namespace
        self.timeout_sec = timeout_sec

    def query_range(
        self,
        query: str,
        start: int,
        end: int,
        step: str = "15s",
    ) -> Dict[str, Any]:
        """Queries Prometheus range vector endpoint /api/v1/query_range."""
        endpoint = f"{self.prometheus_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": str(start),
            "end": str(end),
            "step": step,
        }
        try:
            resp = requests.get(endpoint, params=params, timeout=self.timeout_sec)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Failed to query Prometheus at %s: %s", endpoint, e)
            raise ConnectionError(f"Prometheus query failed: {e}") from e

    @staticmethod
    def extract_service_name_from_labels(
        labels: Dict[str, str],
        known_services: Optional[Sequence[str]] = None,
    ) -> str:
        """Extracts microservice identity from Prometheus metric labels."""
        candidates = [
            labels.get("container", ""),
            labels.get("app", ""),
            labels.get("pod", ""),
            labels.get("service", ""),
            labels.get("instance", ""),
        ]
        if known_services is None:
            known_services = KNOWN_ONLINE_BOUTIQUE_SERVICES

        for cand in candidates:
            if not cand:
                continue
            cand_clean = cand.lower().replace("_", "-")
            for svc in known_services:
                if svc.lower() in cand_clean:
                    return svc

        # Fallback to container or pod if non-empty
        for cand in candidates:
            if cand and cand not in ("POD", ""):
                # Strip pod hash suffixes
                parts = cand.split("-")
                if len(parts) > 2 and len(parts[-1]) >= 4:
                    return "-".join(parts[:-2])
                return cand
        return "unknown_service"

    def parse_range_matrix(
        self,
        payload: Dict[str, Any],
        metric_name: str,
        known_services: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """Parses Prometheus range query JSON response into a timestamp-indexed DataFrame."""
        if payload.get("status") != "success":
            raise ValueError(f"Prometheus query error: {payload.get('error', 'unknown error')}")

        data = payload.get("data", {})
        results = data.get("result", [])
        if not results:
            return pd.DataFrame()

        series_dict: Dict[str, Dict[int, float]] = {}
        all_timestamps = set()

        for item in results:
            labels = item.get("metric", {})
            svc = self.extract_service_name_from_labels(labels, known_services)
            col_name = f"{svc}_{metric_name}"

            values = item.get("values", [])
            val_map: Dict[int, float] = {}
            for t_val, v_val in values:
                try:
                    ts = int(float(t_val))
                    val = float(v_val)
                    val_map[ts] = val
                    all_timestamps.add(ts)
                except (ValueError, TypeError):
                    continue

            if col_name in series_dict:
                # Average or update if multiple replicas
                for ts, val in val_map.items():
                    if ts in series_dict[col_name]:
                        series_dict[col_name][ts] = (series_dict[col_name][ts] + val) / 2.0
                    else:
                        series_dict[col_name][ts] = val
            else:
                series_dict[col_name] = val_map

        if not all_timestamps:
            return pd.DataFrame()

        sorted_ts = sorted(list(all_timestamps))
        df = pd.DataFrame(index=sorted_ts)
        df.index.name = "time"

        for col_name, val_map in series_dict.items():
            df[col_name] = [val_map.get(ts, np.nan) for ts in sorted_ts]

        # Forward-fill, backward-fill, then 0.0 fill
        df = df.ffill().bfill().fillna(0.0)
        return df

    def fetch_live_telemetry(
        self,
        start_time: int,
        end_time: int,
        step: str = "15s",
        metrics: Optional[List[str]] = None,
        system: str = "OnlineBoutique",
    ) -> pd.DataFrame:
        """Queries multiple Prometheus metrics and joins them into a unified DataFrame."""
        if metrics is None:
            metrics = DEFAULT_PROMETHEUS_METRICS

        known_services = get_system_services(system)
        dfs: List[pd.DataFrame] = []

        for m in metrics:
            query = f'{m}{{namespace="{self.namespace}"}}'
            try:
                payload = self.query_range(query, start_time, end_time, step)
                df_m = self.parse_range_matrix(payload, metric_name=m, known_services=known_services)
                if not df_m.empty:
                    dfs.append(df_m)
            except Exception as e:
                logger.warning("Failed to collect metric %s: %s", m, e)

        if not dfs:
            return pd.DataFrame()

        combined = pd.concat(dfs, axis=1)
        combined = combined.loc[:, ~combined.columns.duplicated()]
        return combined.sort_index()

    def build_telemetry_case(
        self,
        df: pd.DataFrame,
        case_id: str,
        inject_time: int,
        root_cause_service: str = "cartservice",
        root_cause_indicator: str = "container_cpu_usage_seconds_total",
        system: str = "OnlineBoutique",
    ) -> TelemetryCase:
        """Converts an aligned metrics DataFrame into an immutable TelemetryCase contract."""
        if df.empty:
            raise ValueError("Cannot build TelemetryCase from empty DataFrame")

        timestamps = [int(t) for t in df.index]
        metrics_data: Dict[str, List[float]] = {}
        for col in df.columns:
            metrics_data[str(col)] = df[col].astype(float).tolist()

        return TelemetryCase(
            case_id=case_id,
            system=system,
            metrics_data=metrics_data,
            timestamps=timestamps,
            inject_time=inject_time,
            root_cause_service=root_cause_service,
            root_cause_indicator=root_cause_indicator,
            data_source_tag="LIVE_K8S_TESTBED",
        )

    @staticmethod
    def create_synthetic_prometheus_payload(
        services: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        start_time: int = 1700000000,
        end_time: int = 1700000900,
        step_sec: int = 15,
        inject_time: int = 1700000600,
        anomalous_service: str = "cartservice",
    ) -> Dict[str, Dict[str, Any]]:
        """Creates realistic Prometheus range-vector response JSON payloads for testing."""
        if services is None:
            services = KNOWN_ONLINE_BOUTIQUE_SERVICES
        if metrics is None:
            metrics = DEFAULT_PROMETHEUS_METRICS

        timestamps = list(range(start_time, end_time + 1, step_sec))
        payloads: Dict[str, Dict[str, Any]] = {}

        for metric in metrics:
            results = []
            for svc in services:
                values = []
                base_val = 10.0 if "cpu" in metric else (100.0 if "memory" in metric else 1.0)
                for t in timestamps:
                    val = base_val + np.random.normal(0, 0.5)
                    if svc == anomalous_service and t >= inject_time:
                        val *= 3.5  # Spike anomaly
                    values.append([t, f"{max(0.0, val):.4f}"])

                results.append({
                    "metric": {
                        "__name__": metric,
                        "container": svc,
                        "pod": f"{svc}-7557455855-abcde",
                        "namespace": "boutique",
                    },
                    "values": values,
                })

            payloads[metric] = {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": results,
                },
            }

        return payloads

    def run_live_pipeline(
        self,
        case: TelemetryCase,
        weights: Optional[Sequence[float]] = None,
        tau_T: float = 0.816,
    ) -> Dict[str, Any]:
        """Executes the 5D Trust Score and Selective Gate pipeline on live TelemetryCase."""
        evaluator = TelemetryTrustEvaluator(weights=weights)
        trust_eval: TrustEvaluation = evaluator.evaluate_case(case)

        # Baseline anomaly score heuristic for live case
        all_services = get_system_services(case.system, case.metrics_data)
        anomaly_scores: Dict[str, float] = {}
        for s in all_services:
            score = trust_eval.service_scores.get(s, 1.0)
            anomaly_scores[s] = 1.0 - score if score < tau_T else 0.1

        gate = SelectiveGate(tau_T=tau_T)
        decisions: Dict[str, SelectiveDecision] = gate.evaluate_case(
            case=case,
            trust_eval=trust_eval,
            anomaly_scores=anomaly_scores,
        )

        return {
            "case_id": case.case_id,
            "data_source_tag": case.data_source_tag,
            "trust_evaluation": trust_eval.model_dump(),
            "service_decisions": {s: d.model_dump() for s, d in decisions.items()},
            "overall_trust": trust_eval.dimensions.get("T_sys", 1.0),
        }
