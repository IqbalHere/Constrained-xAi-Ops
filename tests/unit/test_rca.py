"""Unit tests for Reliability-Weighted BARO with MNAR Blackout Prior."""

import numpy as np
import pytest

from src.quality.trust_score import TelemetryTrustEvaluator
from src.rca.baro_trust import TrustWeightedBARO
from src.rca.baselines import VanillaBARO
from src.schemas import TelemetryCase


def create_mnar_blackout_incident_case() -> tuple[TelemetryCase, np.ndarray]:
    """Creates a synthetic incident where cartservice crashes and stops reporting telemetry.

    Checkoutservice (caller) experiences severe latency degradation.
    Vanilla BARO forward-fills the flatline for cartservice, missing it.
    TrustWeightedBARO leverages the MNAR Blackout Prior to localize cartservice.
    """
    rng = np.random.default_rng(7777)
    T = 200
    timestamps = list(range(1000, 1000 + T))
    inject_time = 1100  # Step 100

    # 1. cartservice: pre-fault normal 20.0, post-fault crashes
    # Suppose true underlying value spiked to 90, but due to pod crash, 60% of points are missing
    cart_pre = rng.normal(loc=20.0, scale=1.0, size=100)
    cart_post = rng.normal(loc=95.0, scale=2.0, size=100)

    # 2. checkoutservice (caller): pre-fault 10.0, post-fault severe spike to 80.0 (stays 100% observed)
    checkout_pre = rng.normal(loc=10.0, scale=1.0, size=100)
    checkout_post = rng.normal(loc=80.0, scale=2.0, size=100)
    checkout_latency = np.concatenate([checkout_pre, checkout_post])

    # 3. currencyservice: quiet normal service
    currency_pre = rng.normal(loc=5.0, scale=0.5, size=100)
    currency_post = rng.normal(loc=5.0, scale=0.5, size=100)
    currency_cpu = np.concatenate([currency_pre, currency_post])

    # Create mask: cartservice drops 60% of post-fault points
    mask = np.ones((T, 3), dtype=np.uint8)
    # Mask col 0 (cartservice)
    drop_indices = rng.choice(np.arange(100, 200), size=60, replace=False)
    mask[drop_indices, 0] = 0

    # Naive forward fill on cartservice post-fault creates flatline
    cart_full = np.concatenate([cart_pre, cart_post])
    cart_ffill = cart_full.copy()
    last_val = cart_pre[-1]
    for t in range(100, 200):
        if mask[t, 0] == 0:
            cart_ffill[t] = last_val
        else:
            last_val = cart_ffill[t]

    metrics = {
        "cartservice_cpu": cart_ffill.tolist(),
        "checkoutservice_latency": checkout_latency.tolist(),
        "currencyservice_cpu": currency_cpu.tolist(),
    }

    case = TelemetryCase(
        case_id="mnar_simulated_case",
        system="OnlineBoutique",
        metrics_data=metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_cpu",
        data_source_tag="SYNTHETIC_DEMO",
    )

    return case, mask


def test_trust_weighted_baro_recovers_mnar_blackout():
    """Verify TrustWeightedBARO correctly ranks cartservice at top under MNAR blackout."""
    case, mask = create_mnar_blackout_incident_case()

    # 1. Vanilla BARO on forward-filled corrupted data
    vanilla = VanillaBARO(pre_fault_buffer_sec=10, post_fault_window_sec=300)
    vanilla_res = vanilla.localize(case)

    # 2. TrustWeightedBARO with MNAR Blackout Prior
    baro_trust = TrustWeightedBARO(
        pre_fault_buffer_sec=10,
        post_fault_window_sec=300,
        lambda_mnar=3.5,
    )
    trust_res = baro_trust.localize(case, mask=mask)

    # TrustWeightedBARO must rank cartservice at rank 1 or 2
    assert "cartservice" in trust_res.ranked_services[:2]
    # And its rank with trust-weighting must be at least as good as or strictly better than vanilla
    vanilla_cart_rank = vanilla_res.ranked_services.index("cartservice") + 1
    trust_cart_rank = trust_res.ranked_services.index("cartservice") + 1
    assert trust_cart_rank <= vanilla_cart_rank
