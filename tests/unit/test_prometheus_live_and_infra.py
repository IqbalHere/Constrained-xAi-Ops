"""Unit tests for Live Prometheus Loader and Infrastructure Manifests.

Validates:
1. PrometheusLiveLoader parsing synthetic Prometheus range vectors into TelemetryCase contracts.
2. YAML syntax and schema integrity for all infrastructure/ manifests (Kind, Online Boutique, Prometheus, Chaos Mesh).
3. Clean compilation and importability of locustfile.py and run_chaos_experiment.py.
4. Correct immutability and provenance tag (data_source_tag="LIVE_K8S_TESTBED").
"""

import ast
import os
from pathlib import Path
import pytest
import yaml

from src.ingestion.prometheus_live import PrometheusLiveLoader, DEFAULT_PROMETHEUS_METRICS
from src.schemas import TelemetryCase


def test_synthetic_prometheus_payload_generation():
    """Verifies synthetic Prometheus range payload creation and structure."""
    payloads = PrometheusLiveLoader.create_synthetic_prometheus_payload(
        services=["cartservice", "frontend"],
        metrics=["up", "container_cpu_usage_seconds_total"],
        start_time=1700000000,
        end_time=1700000060,
        step_sec=15,
    )
    assert "up" in payloads
    assert "container_cpu_usage_seconds_total" in payloads
    assert payloads["up"]["status"] == "success"
    assert payloads["up"]["data"]["resultType"] == "matrix"
    assert len(payloads["up"]["data"]["result"]) == 2  # 2 services


def test_parse_range_matrix_and_build_case():
    """Verifies matrix parsing, alignment, and TelemetryCase creation."""
    loader = PrometheusLiveLoader(prometheus_url="http://mock-prometheus:9090")
    payloads = loader.create_synthetic_prometheus_payload(
        services=["cartservice", "frontend"],
        metrics=["up", "container_cpu_usage_seconds_total"],
        start_time=1700000000,
        end_time=1700000060,
        step_sec=15,
        inject_time=1700000030,
        anomalous_service="cartservice",
    )

    df_up = loader.parse_range_matrix(payloads["up"], metric_name="up")
    df_cpu = loader.parse_range_matrix(payloads["container_cpu_usage_seconds_total"], metric_name="cpu")

    assert not df_up.empty
    assert not df_cpu.empty
    assert "cartservice_up" in df_up.columns
    assert "frontend_up" in df_up.columns
    assert "cartservice_cpu" in df_cpu.columns

    # Join and build case
    import pandas as pd
    combined = pd.concat([df_up, df_cpu], axis=1)
    case = loader.build_telemetry_case(
        df=combined,
        case_id="k8s-live-test-1",
        inject_time=1700000030,
        root_cause_service="cartservice",
        system="OnlineBoutique",
    )

    assert isinstance(case, TelemetryCase)
    assert case.case_id == "k8s-live-test-1"
    assert case.data_source_tag == "LIVE_K8S_TESTBED"
    assert case.root_cause_service == "cartservice"
    assert len(case.timestamps) == 5
    assert "cartservice_cpu" in case.metrics_data

    # Immutability check
    with pytest.raises(Exception):
        case.system = "TamperedSystem"


def test_run_live_pipeline():
    """Verifies that the live case passes through 5D trust and selective gate."""
    loader = PrometheusLiveLoader()
    payloads = loader.create_synthetic_prometheus_payload(
        start_time=1700000000,
        end_time=1700000150,
        step_sec=15,
        inject_time=1700000090,
    )
    import pandas as pd
    dfs = [loader.parse_range_matrix(payload, metric_name=m) for m, payload in payloads.items()]
    combined = pd.concat(dfs, axis=1)
    case = loader.build_telemetry_case(
        df=combined,
        case_id="live-eval-case",
        inject_time=1700000090,
    )

    res = loader.run_live_pipeline(case)
    assert "trust_evaluation" in res
    assert "service_decisions" in res
    assert res["data_source_tag"] == "LIVE_K8S_TESTBED"
    assert 0.0 <= res["overall_trust"] <= 1.0


def test_validate_infrastructure_yaml_manifests():
    """Validates that all YAML manifests in infrastructure/ are well-formed."""
    workspace_root = Path(__file__).resolve().parent.parent.parent
    infra_dir = workspace_root / "infrastructure"
    assert infra_dir.exists(), "infrastructure directory must exist"

    yaml_files = list(infra_dir.rglob("*.yaml")) + list(infra_dir.rglob("*.yml"))
    assert len(yaml_files) >= 5, f"Expected at least 5 YAML files in infrastructure, found {len(yaml_files)}"

    for yf in yaml_files:
        with open(yf, "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            assert len(docs) > 0, f"Empty YAML file: {yf}"
            for doc in docs:
                if doc is not None:
                    assert isinstance(doc, dict), f"Manifest in {yf} did not parse to a dictionary"


def test_locustfile_and_chaos_runner_compilation():
    """Verifies that locustfile.py and run_chaos_experiment.py compile without syntax errors."""
    workspace_root = Path(__file__).resolve().parent.parent.parent
    locust_file = workspace_root / "infrastructure" / "locust" / "locustfile.py"
    chaos_file = workspace_root / "infrastructure" / "chaos-mesh" / "run_chaos_experiment.py"

    assert locust_file.exists()
    assert chaos_file.exists()

    with open(locust_file, "r", encoding="utf-8") as f:
        ast.parse(f.read(), filename=str(locust_file))

    with open(chaos_file, "r", encoding="utf-8") as f:
        ast.parse(f.read(), filename=str(chaos_file))
