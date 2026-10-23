"""Unit tests for Deterministic Missingness & Corruption Engine and Causal Imputation."""

import numpy as np
import pandas as pd
import pytest

from src.missingness.generator import (
    MissingnessGenerator,
    apply_stale_freeze,
    apply_tag_corruption,
)
from src.missingness.masks import save_mask, load_mask
from src.preprocessing.imputer import CausalImputer
from src.schemas import TelemetryCase


def create_synthetic_test_case() -> TelemetryCase:
    """Creates a deterministic 300-step test case with 4 Online Boutique services."""
    rng = np.random.default_rng(12345)
    T = 300
    timestamps = list(range(1000, 1000 + T))
    inject_time = 1150  # Step 150

    # Frontend load observer
    frontend_latency = rng.normal(loc=0.05, scale=0.01, size=T).tolist()
    # Cartservice (root cause)
    cartservice_cpu_pre = rng.normal(loc=15.0, scale=1.0, size=150)
    cartservice_cpu_post = rng.normal(loc=90.0, scale=3.0, size=150)
    cartservice_cpu = np.concatenate([cartservice_cpu_pre, cartservice_cpu_post]).tolist()
    # Currencyservice
    currency_cpu = rng.normal(loc=20.0, scale=2.0, size=T).tolist()
    # Paymentservice
    payment_mem = rng.normal(loc=50.0, scale=1.0, size=T).tolist()

    metrics = {
        "frontend_latency": frontend_latency,
        "cartservice_cpu": cartservice_cpu,
        "currencyservice_cpu": currency_cpu,
        "paymentservice_mem": payment_mem,
    }

    return TelemetryCase(
        case_id="synth_test_01",
        system="OnlineBoutique",
        metrics_data=metrics,
        timestamps=timestamps,
        inject_time=inject_time,
        root_cause_service="cartservice",
        root_cause_indicator="cartservice_cpu",
        data_source_tag="SYNTHETIC_DEMO",
    )


def test_target_missingness_rates():
    """Verify MCAR, MAR, and MNAR generate empirical missingness within +-0.02 of target."""
    gen = MissingnessGenerator(seed=42)
    case = create_synthetic_test_case()
    df = pd.DataFrame(case.metrics_data)
    T, M = df.shape

    for p_miss in [0.2, 0.4, 0.6]:
        # MCAR (pointwise and block)
        mcar_mask_pt = gen.generate_mcar_mask((T, M), p_miss=p_miss, block=False)
        emp_mcar_pt = float(np.mean(mcar_mask_pt == 0))
        assert abs(emp_mcar_pt - p_miss) <= 0.02, f"MCAR pointwise failed for {p_miss}: got {emp_mcar_pt}"

        mcar_mask_blk = gen.generate_mcar_mask((T, M), p_miss=p_miss, block=True, l_bar=15)
        emp_mcar_blk = float(np.mean(mcar_mask_blk == 0))
        assert abs(emp_mcar_blk - p_miss) <= 0.02, f"MCAR block failed for {p_miss}: got {emp_mcar_blk}"

        # MAR (conditioned on frontend observer)
        mar_mask = gen.generate_mar_mask(df, p_miss=p_miss)
        # Observer column is unmasked (column 0), masked columns are 1..3
        masked_cols_data = mar_mask[:, 1:]
        emp_mar = float(np.mean(masked_cols_data == 0))
        assert abs(emp_mar - p_miss) <= 0.02, f"MAR failed for {p_miss}: got {emp_mar}"

        # MNAR
        mnar_mask = gen.generate_mnar_mask(
            df,
            inject_time_idx=150,
            root_cause_service="cartservice",
            p_miss=p_miss,
        )
        emp_mnar = float(np.mean(mnar_mask == 0))
        assert abs(emp_mnar - p_miss) <= 0.02, f"MNAR failed for {p_miss}: got {emp_mnar}"


def test_immutability():
    """Verify applying corruption does NOT mutate the original TelemetryCase data."""
    gen = MissingnessGenerator(seed=42)
    case = create_synthetic_test_case()
    orig_cartservice = list(case.metrics_data["cartservice_cpu"])

    corrupted_dict, mask = gen.apply_corruption(case, mechanism="MNAR", p_miss=0.4)

    # Corrupted dict has NaNs
    assert any(np.isnan(corrupted_dict["cartservice_cpu"]))
    # Original case data is untouched and has NO NaNs
    assert not any(np.isnan(case.metrics_data["cartservice_cpu"]))
    assert case.metrics_data["cartservice_cpu"] == orig_cartservice


def test_mnar_concentration_on_root_cause_service():
    """Under incident-driven MNAR, the post-fault root-cause service should have higher missingness."""
    gen = MissingnessGenerator(seed=42)
    case = create_synthetic_test_case()
    df = pd.DataFrame(case.metrics_data)

    mnar_mask = gen.generate_mnar_mask(
        df,
        inject_time_idx=150,
        root_cause_service="cartservice",
        p_miss=0.3,
    )

    cartservice_idx = list(df.columns).index("cartservice_cpu")
    currency_idx = list(df.columns).index("currencyservice_cpu")

    post_cart_missing = np.mean(mnar_mask[150:, cartservice_idx] == 0)
    pre_currency_missing = np.mean(mnar_mask[:150, currency_idx] == 0)

    assert post_cart_missing > pre_currency_missing
    assert post_cart_missing > 0.35, "Root cause post-fault missingness should be concentrated"


def test_causal_imputation_no_future_leakage():
    """Modifying future values at t=250 must NOT alter imputed values at t=100."""
    imputer = CausalImputer(method="forward_fill")

    T = 200
    df = pd.DataFrame({
        "m1": [float(i) for i in range(T)],
    })
    mask = np.ones((T, 1), dtype=np.uint8)
    mask[90:110, 0] = 0  # Missing gap around t=100

    # Imputation run 1
    imputed_1 = imputer.impute(df, mask, inject_time_idx=150)
    val_at_100_first = imputed_1.iloc[100, 0]

    # Modify future post-fault values drastically at t >= 180
    df_tampered = df.copy()
    df_tampered.iloc[180:, 0] = 99999.0

    imputed_2 = imputer.impute(df_tampered, mask, inject_time_idx=150)
    val_at_100_second = imputed_2.iloc[100, 0]

    assert val_at_100_first == val_at_100_second, "Future values leaked backward into t=100!"


def test_mask_persistence_and_sha256(tmp_path):
    """Test mask saving and loading with SHA-256 integrity verification."""
    mask = np.array([[1, 0, 1], [0, 1, 0]], dtype=np.uint8)
    save_path = tmp_path / "test_mask.npz"

    sha = save_mask(mask, save_path, metadata={"p_miss": 0.5})
    assert isinstance(sha, str)
    assert len(sha) == 64

    loaded_mask, meta = load_mask(save_path, expected_sha256=sha)
    assert np.array_equal(mask, loaded_mask)
    assert meta["p_miss"] == 0.5

    # Wrong checksum raises ValueError
    with pytest.raises(ValueError):
        load_mask(save_path, expected_sha256="wrong_hash_0000000000000000000000000000000000000000000000000000000000")
