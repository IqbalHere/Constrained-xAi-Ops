"""Unit and integration tests for Nezha loader and live Kubernetes Prometheus loader."""

import os
import json
import pytest
import numpy as np

from src.ingestion.nezha_loader import NezhaLoader, run_nezha_and_live_k8s_verification
from src.ingestion.prometheus_live import PrometheusLiveLoader
from src.schemas import TelemetryCase, SelectiveDecision


def test_nezha_synthetic_trace_creation():
    """Verify that NezhaLoader generates valid TelemetryCase contracts for PodChaos."""
    loader = NezhaLoader(system="OnlineBoutique")
    case, mask, gt_indicator = loader.create_synthetic_nezha_trace(
        chaos_type="PodChaos",
        target_service="cartservice",
        duration_sec=300,
        step_sec=15,
        inject_time=1700000150,
        start_time=1700000000,
        seed=42,
    )

    assert isinstance(case, TelemetryCase)
    assert case.system == "OnlineBoutique"
    assert case.root_cause_service == "cartservice"
    assert "cartservice" in gt_indicator
    assert case.data_source_tag == "PUBLIC_BENCHMARK"
    assert len(case.timestamps) == 21
    assert mask.shape == (21, len(case.metrics_data))
    assert np.all((mask == 0) | (mask == 1))


def test_nezha_explanation_evaluation():
    """Verify that TreeSHAP explanation evaluation runs and produces fidelity metrics."""
    loader = NezhaLoader(system="OnlineBoutique")
    case, mask, gt_indicator = loader.create_synthetic_nezha_trace(
        chaos_type="NetworkChaos",
        target_service="checkoutservice",
        duration_sec=300,
        step_sec=15,
        inject_time=1700000150,
        start_time=1700000000,
        seed=1024,
    )

    eval_res = loader.evaluate_explanation_on_case(case, mask, gt_indicator, seed=1024)
    assert "constrained_xaiops" in eval_res
    assert "naive_treeshap" in eval_res
    assert "fidelity_at_1" in eval_res["constrained_xaiops"]
    assert "fidelity_at_3" in eval_res["constrained_xaiops"]
    assert "jaccard_at_3" in eval_res["constrained_xaiops"]
    assert 0.0 <= eval_res["constrained_xaiops"]["fidelity_at_3"] <= 1.0


def test_live_k8s_prometheus_loader_podkill_escalation():
    """Verify that PrometheusLiveLoader produces LIVE_K8S_TESTBED case and triggers ESCALATE_MNAR_BLACKOUT."""
    prom_loader = PrometheusLiveLoader(namespace="boutique")
    start_time = 1700000000
    inject_time = 1700000600
    end_time = 1700000900
    step_sec = 15

    payloads = prom_loader.create_synthetic_prometheus_payload(
        start_time=start_time,
        end_time=end_time,
        step_sec=step_sec,
        inject_time=inject_time,
        anomalous_service="cartservice",
    )

    dfs = []
    for metric_name, payload in payloads.items():
        df_m = prom_loader.parse_range_matrix(payload, metric_name=metric_name)
        if not df_m.empty:
            dfs.append(df_m)
    import pandas as pd
    df = pd.concat(dfs, axis=1)
    df = df.loc[:, ~df.columns.duplicated()].sort_index()

    case = prom_loader.build_telemetry_case(
        df=df,
        case_id="test_live_k8s_case",
        inject_time=inject_time,
        root_cause_service="cartservice",
    )

    assert isinstance(case, TelemetryCase)
    assert case.data_source_tag == "LIVE_K8S_TESTBED"
    assert case.root_cause_service == "cartservice"


def test_end_to_end_nezha_and_live_k8s_validation(tmp_path):
    """Verify the full execution of run_nezha_and_live_k8s_verification."""
    test_out = str(tmp_path / "test_nezha_validation.json")
    res = run_nezha_and_live_k8s_verification(output_path=test_out)

    assert res["status"] == "VERIFIED_COMPLIANT"
    assert res["live_k8s_testbed_verification"]["triggered_escalate_mnar_blackout"] is True
    assert res["live_k8s_testbed_verification"]["cartservice_outcome"] == "ESCALATE_MNAR_BLACKOUT"
    assert res["live_k8s_testbed_verification"]["data_source_tag"] == "LIVE_K8S_TESTBED"
    assert os.path.exists(test_out)
