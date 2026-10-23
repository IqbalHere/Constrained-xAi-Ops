"""Unit tests for TelemetryAligner and deduplication."""

import pandas as pd
from src.ingestion.aligner import (
    TelemetryAligner,
    extract_services_from_metrics,
    group_metrics_by_service,
)


def test_aligner_deduplicates_duplicate_time_column():
    """RCAEval RE1-OB specific fix: 50 cases have duplicate 'time' columns."""
    aligner = TelemetryAligner()

    # Synthetic dataframe with duplicate 'time' column
    data = {
        "time": [1000, 1001, 1002],
        "time_dup": [1000, 1001, 1002],
        "cartservice_cpu": [0.1, 0.4, 0.8],
        "frontend_memory": [100.0, 102.0, 105.0],
    }
    raw_df = pd.DataFrame(data)
    # Rename duplicate to have identical column name 'time'
    raw_df.columns = ["time", "time", "cartservice_cpu", "frontend_memory"]
    assert list(raw_df.columns).count("time") == 2

    # Deduplicate and structure
    case = aligner.align_and_structure(
        raw_df=raw_df,
        case_id="test_dup_case",
        inject_time=1001,
        root_cause_service="cartservice",
    )

    # Assertions
    assert case.case_id == "test_dup_case"
    assert case.timestamps == [1000, 1001, 1002]
    assert "time" not in case.metrics_data
    assert "cartservice_cpu" in case.metrics_data
    assert "frontend_memory" in case.metrics_data
    assert case.metrics_data["cartservice_cpu"] == [0.1, 0.4, 0.8]
    assert case.metrics_data["frontend_memory"] == [100.0, 102.0, 105.0]


def test_service_extraction_and_grouping():
    metrics = {
        "cartservice_cpu_utilization": [0.1, 0.2],
        "cartservice_memory_working_set": [50.0, 52.0],
        "frontend_request_duration_seconds": [0.01, 0.02],
        "paymentservice_qps": [100.0, 105.0],
    }
    services = extract_services_from_metrics(metrics)
    assert "cartservice" in services
    assert "frontend" in services
    assert "paymentservice" in services

    grouped = group_metrics_by_service(metrics)
    assert len(grouped["cartservice"]) == 2
    assert len(grouped["frontend"]) == 1
    assert len(grouped["paymentservice"]) == 1
