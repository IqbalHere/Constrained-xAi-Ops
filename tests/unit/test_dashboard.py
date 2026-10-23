"""Unit tests for FastAPI Operational Backend & Dashboard API."""

import pytest
from starlette.testclient import TestClient

from src.dashboard.api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["cpu_logical_cores"] >= 4
    assert data["hardware_concurrency_threads"] >= 4
    assert "ram_total_gb" in data


def test_dashboard_cases_listing(client):
    response = client.get("/cases")
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) > 0
    first = cases[0]
    assert "case_id" in first
    assert "root_cause_service" in first
    assert "system" in first


def test_dashboard_simulation_pipeline(client):
    cases_res = client.get("/cases")
    first_case_id = cases_res.json()[0]["case_id"]

    sim_payload = {
        "case_id": first_case_id,
        "mechanism": "MNAR",
        "p_miss": 0.40,
        "enable_escalation": True,
        "explain_root_cause": True,
    }

    response = client.post("/simulate", json=sim_payload)
    assert response.status_code == 200
    res = response.json()

    assert res["case_id"] == first_case_id
    assert "trust_evaluation" in res
    assert 0.0 <= res["trust_evaluation"]["T_sys"] <= 1.0

    assert "selective_decisions" in res
    assert len(res["selective_decisions"]) == 10

    assert "rca_comparison" in res
    assert "vanilla_baro" in res["rca_comparison"]
    assert "constrained_xaiops" in res["rca_comparison"]

    assert "explanation" in res
    assert "runtime_ms" in res
    assert res["runtime_ms"] > 0.0


def test_dashboard_feedback_and_recalibration(client):
    cases_res = client.get("/cases")
    first_case_id = cases_res.json()[0]["case_id"]

    fb_payload = {
        "case_id": first_case_id,
        "service": "cartservice",
        "verdict": "FALSE_POSITIVE",
        "trust_score": 0.35,
        "anomaly_score": 0.45,
    }

    response = client.post("/feedback", json=fb_payload)
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "success"
    assert "updated_thresholds" in res
    assert "tau_T" in res["updated_thresholds"]


def test_dashboard_benchmarks(client):
    response = client.get("/benchmarks")
    assert response.status_code == 200
    data = response.json()
    assert "main_missingness_grid" in data
    assert "statistical_tests" in data


def test_dashboard_multisystem_benchmarks(client):
    response = client.get("/benchmarks/multisystem")
    assert response.status_code == 200
    data = response.json()
    assert "experiment_a_multisystem" in data
    assert "experiment_b_zeroshot_transfer" in data
    assert "experiment_c_security_defense" in data
    assert "OnlineBoutique" in data["experiment_a_multisystem"]
    assert "SockShop" in data["experiment_a_multisystem"]
    assert "TrainTicket" in data["experiment_a_multisystem"]
