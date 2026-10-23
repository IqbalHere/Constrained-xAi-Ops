"""Telemetry Alignment, Deduplication, and Normalization module.

Critical RCAEval fix: Handles duplicate `time` columns present in RE1 benchmark cases.
Snaps irregular timestamps and maps metric columns to structured TelemetryCase instances across
Online Boutique, Sock Shop, and Train Ticket systems.
"""

from typing import Dict, Iterable, List, Optional, Sequence
import numpy as np
import pandas as pd

from src.schemas import TelemetryCase

# The 10 canonical microservices of Google Cloud Online Boutique benchmark
KNOWN_ONLINE_BOUTIQUE_SERVICES = [
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

# The 13 canonical microservices of Sock Shop benchmark
KNOWN_SOCK_SHOP_SERVICES = [
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


class TelemetryAligner:
    """Aligns, cleans, and deduplicates raw multi-metric microservice telemetry."""

    def __init__(self, target_interval_sec: int = 1):
        self.target_interval_sec = target_interval_sec

    @staticmethod
    def deduplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Removes duplicate columns (critical for RCAEval where duplicate 'time' columns exist)."""
        # In pandas, reading a CSV with duplicate column headers like 'time' creates 'time.1', 'time.2', etc.
        # Normalize any mangled duplicate time columns back to 'time' so duplicated() catches them.
        new_cols = []
        for c in df.columns:
            c_str = str(c)
            c_lower = c_str.lower()
            if c_lower.startswith("time.") or c_lower == "time":
                new_cols.append("time")
            elif c_lower.startswith("timestamp.") or c_lower == "timestamp":
                new_cols.append("timestamp")
            else:
                new_cols.append(c_str)
        df.columns = new_cols

        # Enforce exact duplicate removal
        return df.loc[:, ~df.columns.duplicated()]

    @staticmethod
    def extract_service_name(
        col_name: str,
        known_services: Optional[Sequence[str]] = None,
    ) -> str:
        """Extracts microservice name by stripping prefix or matching known service names."""
        col_lower = col_name.lower()
        if known_services is not None:
            for s in known_services:
                if col_lower.startswith(f"{s.lower()}_") or col_lower == s.lower():
                    return s

        # Check known Online Boutique and Sock Shop services
        for s in KNOWN_ONLINE_BOUTIQUE_SERVICES + KNOWN_SOCK_SHOP_SERVICES:
            if col_lower.startswith(f"{s.lower()}_") or col_lower == s.lower():
                return s

        # Train Ticket ts-* microservices or general microservice pattern: split at first underscore
        if "_" in col_name:
            return col_name.split("_")[0]
        return col_name

    def align_and_structure(
        self,
        raw_df: pd.DataFrame,
        case_id: str,
        system: str = "OnlineBoutique",
        inject_time: int = 0,
        root_cause_service: str = "unknown",
        root_cause_indicator: str = "unknown",
        data_source_tag: str = "PUBLIC_BENCHMARK",
    ) -> TelemetryCase:
        """Deduplicates columns, aligns timestamps, cleans metric values, and returns TelemetryCase."""
        # 1. Deduplicate columns
        df = self.deduplicate_columns(raw_df).copy()

        # 2. Extract and sanitize timestamps
        time_col = None
        for candidate in ["time", "timestamp", "Timestamp", "Time"]:
            if candidate in df.columns:
                time_col = candidate
                break

        if time_col is not None:
            raw_times = df[time_col].values
            df = df.drop(columns=[time_col])
        else:
            raw_times = np.arange(len(df))

        # Handle float/int timestamps and potential epoch milliseconds
        try:
            numeric_times = pd.to_numeric(raw_times, errors="coerce")
            if np.nanmin(numeric_times) > 1e11:  # Milliseconds
                numeric_times = numeric_times / 1000.0
            aligned_times = [int(round(t)) for t in numeric_times]
        except Exception:
            aligned_times = list(range(len(df)))

        # 3. Clean and structure metrics (exclude any remaining time columns)
        metrics_data: dict[str, list[float]] = {}
        for col in df.columns:
            col_str = str(col)
            if col_str.lower() in ("time", "timestamp") or col_str.lower().startswith(("time.", "timestamp.")):
                continue
            series = pd.to_numeric(df[col], errors="coerce")
            # Fill missing values: forward fill then backward fill then 0.0
            series = series.ffill().bfill().fillna(0.0)
            metrics_data[col_str] = series.astype(float).tolist()

        return TelemetryCase(
            case_id=case_id,
            system=system,
            metrics_data=metrics_data,
            timestamps=aligned_times,
            inject_time=int(inject_time),
            root_cause_service=root_cause_service,
            root_cause_indicator=root_cause_indicator,
            data_source_tag=data_source_tag,
        )


def extract_services_from_metrics(
    metrics_data: dict[str, list[float]],
    known_services: Optional[Sequence[str]] = None,
) -> list[str]:
    """Returns a sorted list of unique microservices represented in metrics_data."""
    services = set()
    for col in metrics_data.keys():
        s = TelemetryAligner.extract_service_name(col, known_services)
        services.add(s)
    return sorted(list(services))


def group_metrics_by_service(
    metrics_data: dict[str, list[float]],
    known_services: Optional[Sequence[str]] = None,
) -> dict[str, dict[str, list[float]]]:
    """Groups metric series by their owning microservice."""
    grouped: dict[str, dict[str, list[float]]] = {}
    for col, values in metrics_data.items():
        s = TelemetryAligner.extract_service_name(col, known_services)
        if s not in grouped:
            grouped[s] = {}
        grouped[s][col] = values
    return grouped


def get_system_services(system: str = "OnlineBoutique", metrics_data: Optional[dict] = None) -> list[str]:
    """Returns canonical microservices list for target system (OB: 10, SS: 13, TT: dynamic ts-*)."""
    sys_lower = system.lower()
    if "online" in sys_lower or "boutique" in sys_lower:
        return list(KNOWN_ONLINE_BOUTIQUE_SERVICES)
    elif "sock" in sys_lower:
        return list(KNOWN_SOCK_SHOP_SERVICES)
    elif "train" in sys_lower:
        if metrics_data:
            ts_svcs = [s for s in extract_services_from_metrics(metrics_data) if s.startswith("ts-")]
            if ts_svcs:
                return sorted(list(set(ts_svcs)))
        return [
            "ts-ui-dashboard", "ts-auth-service", "ts-user-service", "ts-verification-code-service",
            "ts-station-service", "ts-train-service", "ts-config-service", "ts-security-service",
            "ts-execute-service", "ts-contacts-service", "ts-order-service", "ts-order-other-service",
            "ts-preserve-service", "ts-preserve-other-service", "ts-price-service", "ts-basic-service",
            "ts-ticketinfo-service", "ts-notification-service", "ts-inside-payment-service",
            "ts-payment-service", "ts-rebook-service", "ts-cancel-service", "ts-route-service",
            "ts-seat-service", "ts-travel-service", "ts-travel2-service", "ts-assurance-service",
            "ts-consign-service", "ts-consign-price-service", "ts-food-service", "ts-food-map-service",
            "ts-route-plan-service", "ts-travel-plan-service", "ts-voucher-service",
            "ts-admin-basic-info-service", "ts-admin-order-service", "ts-admin-route-service",
            "ts-admin-travel-service", "ts-admin-user-service",
        ]
    else:
        if metrics_data:
            return extract_services_from_metrics(metrics_data)
        return list(KNOWN_ONLINE_BOUTIQUE_SERVICES)
