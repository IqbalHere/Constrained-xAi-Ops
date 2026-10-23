"""Unit tests for Phase 6 Multi-System Topologies, Causal Baselines, and Security Telemetry Defenses."""

import numpy as np
import pandas as pd
import pytest

from src.abstention.mnar_escalator import detect_mnar_blackout
from src.abstention.selective_gate import SelectiveGate
from src.correlation.topology import (
    BaseTopology,
    OnlineBoutiqueTopology,
    SockShopTopology,
    TrainTicketTopology,
    get_topology,
)
from src.missingness.generator import apply_adversarial_spoofing, apply_stale_freeze
from src.quality.trust_score import TelemetryTrustEvaluator
from src.rca.baselines import CIRCA, RCD, EpsilonDiagnosis, VanillaBARO
from src.schemas import TelemetryCase


def create_synthetic_multisystem_case(system: str = "SockShop") -> TelemetryCase:
    """Creates a synthetic multi-metric case for testing."""
    rng = np.random.default_rng(12345)
    T = 200
    timestamps = list(range(1000, 1000 + T))
    inject_time = 1100

    if system == "SockShop":
        # Multi-metric for Sock Shop with realistic coupling
        carts_cpu = rng.normal(12.0, 1.5, size=T)
        carts_lat = carts_cpu * 0.005 + rng.normal(0.02, 0.001, size=T)
        metrics = {
            "front-end_cpu": rng.normal(10.0, 1.0, size=T).tolist(),
            "front-end_latency": rng.normal(0.05, 0.005, size=T).tolist(),
            "orders_cpu": rng.normal(15.0, 2.0, size=T).tolist(),
            "orders_mem": rng.normal(200.0, 10.0, size=T).tolist(),
            "carts_cpu": carts_cpu.tolist(),
            "carts_latency": carts_lat.tolist(),
            "catalogue_cpu": rng.normal(8.0, 0.5, size=T).tolist(),
            "user_cpu": rng.normal(5.0, 0.5, size=T).tolist(),
            # Add a constant zero-variance column to test numerical resilience
            "payment_constant_zero": np.zeros(T).tolist(),
            "shipping_constant_val": (np.ones(T) * 42.0).tolist(),
        }
        # Inject anomalous spike in carts after inject_time
        metrics["carts_cpu"] = [
            v + (50.0 if t >= inject_time else 0.0) for t, v in zip(timestamps, metrics["carts_cpu"])
        ]
        return TelemetryCase(
            case_id="ss_test_01",
            system="SockShop",
            metrics_data=metrics,
            timestamps=timestamps,
            inject_time=inject_time,
            root_cause_service="carts",
            root_cause_indicator="cpu",
            data_source_tag="SYNTHETIC_DEMO",
        )
    else:
        # Train Ticket
        metrics = {
            "ts-ui-dashboard_cpu": rng.normal(20.0, 2.0, size=T).tolist(),
            "ts-travel-service_cpu": rng.normal(15.0, 1.5, size=T).tolist(),
            "ts-order-service_cpu": rng.normal(18.0, 2.0, size=T).tolist(),
            "ts-station-service_cpu": rng.normal(10.0, 1.0, size=T).tolist(),
            "ts-seat-service_zero_var": np.zeros(T).tolist(),
        }
        # Inject spike in ts-travel-service
        metrics["ts-travel-service_cpu"] = [
            v + (40.0 if t >= inject_time else 0.0) for t, v in zip(timestamps, metrics["ts-travel-service_cpu"])
        ]
        return TelemetryCase(
            case_id="tt_test_01",
            system="TrainTicket",
            metrics_data=metrics,
            timestamps=timestamps,
            inject_time=inject_time,
            root_cause_service="ts-travel-service",
            root_cause_indicator="cpu",
            data_source_tag="SYNTHETIC_DEMO",
        )


def test_circa_and_rcd_baseline_execution_and_resilience():
    """Tests that CIRCA and RCD execute smoothly with zero-variance and constant columns."""
    case = create_synthetic_multisystem_case(system="SockShop")

    # 1. CIRCA
    circa = CIRCA(pre_fault_buffer_sec=10, post_fault_window_sec=300, alpha=1.0)
    res_circa = circa.localize(case)

    assert res_circa.case_id == case.case_id
    assert len(res_circa.ranked_services) > 0
    assert not any(np.isnan(res_circa.scores))
    assert not any(np.isinf(res_circa.scores))
    assert res_circa.ground_truth_service == "carts"
    # Root cause 'carts' should be detected in top 3
    assert res_circa.hit_at_3 is True

    # 2. RCD
    rcd = RCD(pre_fault_buffer_sec=10, post_fault_window_sec=300)
    res_rcd = rcd.localize(case)

    assert res_rcd.case_id == case.case_id
    assert len(res_rcd.ranked_services) > 0
    assert not any(np.isnan(res_rcd.scores))
    assert not any(np.isinf(res_rcd.scores))
    assert res_rcd.ground_truth_service == "carts"
    assert res_rcd.hit_at_3 is True


def test_sock_shop_and_train_ticket_topologies():
    """Tests neighbor lookup, call graph traversal, and dynamic empirical augmentation."""
    # 1. Sock Shop Topology
    ss_topo = SockShopTopology()
    assert "front-end" in ss_topo.services
    assert "orders" in ss_topo.services
    assert "carts" in ss_topo.services

    fe_neighbors = ss_topo.get_neighbors("front-end")
    assert "orders" in fe_neighbors
    assert "carts" in fe_neighbors
    assert "catalogue" in fe_neighbors
    assert "user" in fe_neighbors

    # Check connection queries
    assert ss_topo.are_connected("front-end", "orders") is True
    assert ss_topo.are_connected("orders", "payment") is True
    assert ss_topo.are_connected("carts", "carts-db") is True

    # 2. Train Ticket Topology
    tt_topo = TrainTicketTopology()
    assert "ts-travel-service" in tt_topo.services
    travel_neighbors = tt_topo.get_neighbors("ts-travel-service")
    assert len(travel_neighbors) > 0

    # Test dynamic empirical augmentation on case
    case = create_synthetic_multisystem_case(system="TrainTicket")
    augmented_topo = tt_topo.build_empirical_topology(case)
    assert len(augmented_topo.get_neighbors("ts-station-service")) > 0

    # 3. Factory lookup
    topo_ob = get_topology("OnlineBoutique")
    topo_ss = get_topology("SockShop")
    topo_tt = get_topology("TrainTicket", case=case)

    assert isinstance(topo_ob, OnlineBoutiqueTopology)
    assert isinstance(topo_ss, SockShopTopology)
    assert isinstance(topo_tt, TrainTicketTopology)


def test_stale_freeze_and_adversarial_spoofing_detection():
    """Tests that the 5D Trust Score and Escalation Gate catch Stale-Freeze and Adversarial Spoofing."""
    evaluator = TelemetryTrustEvaluator()
    case = create_synthetic_multisystem_case(system="SockShop")
    df = pd.DataFrame(case.metrics_data)

    # 1. Stale-Freeze Defense: Exporter hangs on carts
    frozen_df, freeze_mask = apply_stale_freeze(df, service="carts", start_idx=100, duration=80)
    frozen_case = TelemetryCase(
        case_id="frozen_test",
        system=case.system,
        metrics_data={col: frozen_df[col].tolist() for col in frozen_df.columns},
        timestamps=case.timestamps,
        inject_time=case.inject_time,
        root_cause_service=case.root_cause_service,
        root_cause_indicator=case.root_cause_indicator,
        data_source_tag="SYNTHETIC_DEMO",
    )

    all_ones_mask = np.ones(df.shape, dtype=np.uint8)  # Completeness is 100%!
    eval_frozen = evaluator.evaluate_case(frozen_case, mask=all_ones_mask)

    # Carts trust should drop significantly due to timeliness (L) drop
    carts_trust = eval_frozen.service_scores["carts"]
    assert carts_trust <= 0.93, f"Expected carts trust <= 0.93, got {carts_trust}"
    assert eval_frozen.dimensions["L"] < 0.95

    # 2. Adversarial Spoofing Defense ("AI Oops")
    spoofed_case, spoof_mask = apply_adversarial_spoofing(case, service="carts", seed=42)
    eval_spoofed = evaluator.evaluate_case(spoofed_case, mask=all_ones_mask)

    # Consistency (S) and Validity (V) must drop
    carts_spoofed_trust = eval_spoofed.service_scores["carts"]
    assert carts_spoofed_trust <= 0.92, f"Expected carts spoofed trust <= 0.92, got {carts_spoofed_trust}"
    assert eval_spoofed.dimensions["V"] < 0.98 or eval_spoofed.dimensions["S"] < 0.98

    # 3. Escalator / Selective Gate responds safely
    gate = SelectiveGate(tau_T=0.95, tau_A=0.35)
    decisions = gate.evaluate_case(
        case=spoofed_case,
        trust_eval=eval_spoofed,
        anomaly_scores={"carts": 0.5, "orders": 0.1, "front-end": 0.1},
        mask=all_ones_mask,
    )
    # The spoofed carts service should have low trust and be abstained or escalated
    carts_decision = decisions["carts"]
    assert carts_decision.outcome in ("ABSTAIN_FLAGGED", "ABSTAIN_DEGRADED", "ESCALATE_CRITICAL", "ABSTAIN_LOW_TRUST", "ESCALATE_MNAR_BLACKOUT")
