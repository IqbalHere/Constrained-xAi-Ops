"""Deterministic Missingness and Telemetry Corruption Engine.

Implements realistic cloud telemetry degradation mechanisms:
  1. MCAR: Pointwise and contiguous block dropout (geometric lengths L_bar=15).
  2. MAR: Missingness conditioned on observed frontend load observer Z_obs(t).
  3. MNAR: Incident-driven post-fault blackout concentrated on root-cause service.
  4. Stale-Freeze: Simulates Prometheus exporter hangs (constant frozen telemetry).
  5. Tag Corruption: Simulates telemetry schema drifts and corrupted service prefixes.

All mechanisms are deterministic, seeded, and strictly avoid mutating inputs.
"""

from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd

from src.ingestion.aligner import KNOWN_ONLINE_BOUTIQUE_SERVICES, TelemetryAligner
from src.schemas import TelemetryCase


from scipy.ndimage import maximum_filter1d
from scipy.special import expit as _sigmoid


class MissingnessGenerator:
    """Deterministic, leakage-safe telemetry missingness generator."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def generate_mcar_mask(
        self,
        shape: Tuple[int, int],
        p_miss: float,
        block: bool = True,
        l_bar: int = 15,
        rng: Optional[np.random.Generator] = None,
    ) -> np.ndarray:
        """Generates a Missing Completely At Random (MCAR) binary observation mask.

        Args:
            shape: (T, M) tuple for time-steps and metrics.
            p_miss: Target missing fraction in [0.0, 1.0].
            block: If True, uses contiguous geometric blocks; otherwise pointwise Bernoulli.
            l_bar: Mean block length for geometric distribution.
            rng: Optional numpy Generator for reproducibility.

        Returns:
            mask: uint8 array of shape (T, M) where 1=observed, 0=missing.
        """
        if p_miss <= 0.0:
            return np.ones(shape, dtype=np.uint8)
        if p_miss >= 1.0:
            return np.zeros(shape, dtype=np.uint8)

        if rng is None:
            rng = np.random.default_rng(self.seed)

        T, M = shape
        total_elements = T * M
        target_zeros = int(round(total_elements * p_miss))

        mask = np.ones(shape, dtype=np.uint8)

        if not block:
            # Pointwise random selection of exact target count
            all_indices = rng.permutation(total_elements)
            zero_indices = all_indices[:target_zeros]
            t_idx, m_idx = np.unravel_index(zero_indices, shape)
            mask[t_idx, m_idx] = 0
            return mask

        # Contiguous block dropout
        current_zeros = 0
        max_attempts = total_elements * 3
        attempts = 0

        while current_zeros < target_zeros and attempts < max_attempts:
            attempts += 1
            m = rng.integers(0, M)
            t_start = rng.integers(0, T)
            block_len = rng.geometric(p=1.0 / max(1.0, float(l_bar)))
            t_end = min(T, t_start + block_len)

            # Check how many new zeros would be added
            segment = mask[t_start:t_end, m]
            new_zeros = np.sum(segment == 1)

            if current_zeros + new_zeros <= target_zeros + int(0.01 * total_elements):
                mask[t_start:t_end, m] = 0
                current_zeros += new_zeros
            else:
                # Add only what's needed to meet target
                needed = target_zeros - current_zeros
                if needed > 0:
                    ones_in_seg = np.where(segment == 1)[0]
                    if len(ones_in_seg) > 0:
                        chosen = ones_in_seg[:needed]
                        mask[t_start + chosen, m] = 0
                        current_zeros += len(chosen)
                break

        # Fine-tune to be within +-0.01 tolerance
        diff = target_zeros - np.sum(mask == 0)
        if diff > 0:
            ones_pos = np.argwhere(mask == 1)
            if len(ones_pos) > 0:
                pick = rng.choice(len(ones_pos), size=min(diff, len(ones_pos)), replace=False)
                mask[ones_pos[pick, 0], ones_pos[pick, 1]] = 0
        elif diff < 0:
            zeros_pos = np.argwhere(mask == 0)
            if len(zeros_pos) > 0:
                pick = rng.choice(len(zeros_pos), size=min(-diff, len(zeros_pos)), replace=False)
                mask[zeros_pos[pick, 0], zeros_pos[pick, 1]] = 1

        return mask

    def generate_mar_mask(
        self,
        metrics_df: pd.DataFrame,
        p_miss: float,
        block_len: int = 10,
        rng: Optional[np.random.Generator] = None,
    ) -> np.ndarray:
        """Generates a Missing At Random (MAR) mask conditioned on observed frontend load.

        The observer metric Z_obs(t) (frontend latency or load) remains 100% observed.
        Other metrics drop out with probability P(M_t,m = 0 | Z_obs) = sigmoid(beta_0 + 2.0 * Z_obs_std).
        beta_0 is solved via bisection so empirical missingness across masked metrics matches p_miss.
        """
        if p_miss <= 0.0:
            return np.ones(metrics_df.shape, dtype=np.uint8)
        if p_miss >= 1.0:
            return np.zeros(metrics_df.shape, dtype=np.uint8)

        if rng is None:
            rng = np.random.default_rng(self.seed)

        T, M = metrics_df.shape
        cols = list(metrics_df.columns)

        # 1. Identify conditioning observer column (frontend metric)
        obs_col_idx = 0
        for i, col in enumerate(cols):
            if "frontend" in col.lower() and ("latency" in col.lower() or "load" in col.lower() or "cpu" in col.lower()):
                obs_col_idx = i
                break

        z_obs = metrics_df.iloc[:, obs_col_idx].values.astype(float)
        mean_z = np.nanmean(z_obs)
        std_z = np.nanstd(z_obs) + 1e-4
        z_std = (z_obs - mean_z) / std_z

        # Masked metrics count: all except obs_col_idx
        masked_cols = [i for i in range(M) if i != obs_col_idx]
        total_masked_elements = T * len(masked_cols)
        target_zeros = int(round(total_masked_elements * p_miss))

        # Pre-generate uniform noise matrices for deterministic bisection
        u_matrix = rng.uniform(size=(T, len(masked_cols)))

        def evaluate_beta(beta: float) -> Tuple[int, np.ndarray]:
            probs = _sigmoid(beta + 2.0 * z_std)[:, None]  # shape (T, 1)
            starts = (u_matrix < probs).astype(np.uint8)
            dilated = maximum_filter1d(starts, size=block_len, axis=0, origin=-(block_len // 2))
            sub_mask = 1 - dilated
            return int(np.sum(sub_mask == 0)), sub_mask

        # Bisection on beta_0 in [-25.0, 25.0]
        low, high = -25.0, 25.0
        best_sub_mask = None

        for _ in range(25):
            mid = 0.5 * (low + high)
            zeros, sub_mask = evaluate_beta(mid)
            best_sub_mask = sub_mask

            if abs(zeros - target_zeros) <= max(1, int(0.01 * total_masked_elements)):
                break
            if zeros < target_zeros:
                low = mid
            else:
                high = mid

        # Assemble full mask (observer column stays completely observed = 1)
        full_mask = np.ones((T, M), dtype=np.uint8)
        for j_idx, col_idx in enumerate(masked_cols):
            full_mask[:, col_idx] = best_sub_mask[:, j_idx]
        full_mask[:, obs_col_idx] = 1

        # Fine-tune masked columns to match exact tolerance +-0.01
        current_zeros = int(np.sum(full_mask == 0))
        diff = target_zeros - current_zeros

        if diff > 0:
            t_idx, m_sub_idx = np.where(full_mask[:, masked_cols] == 1)
            if len(t_idx) > 0:
                pick = rng.choice(len(t_idx), size=min(diff, len(t_idx)), replace=False)
                for p in pick:
                    full_mask[t_idx[p], masked_cols[m_sub_idx[p]]] = 0
        elif diff < 0:
            t_idx, m_sub_idx = np.where(full_mask[:, masked_cols] == 0)
            if len(t_idx) > 0:
                pick = rng.choice(len(t_idx), size=min(-diff, len(t_idx)), replace=False)
                for p in pick:
                    full_mask[t_idx[p], masked_cols[m_sub_idx[p]]] = 1

        return full_mask

    def generate_mnar_mask(
        self,
        metrics_df: pd.DataFrame,
        inject_time_idx: int,
        root_cause_service: str,
        p_miss: float,
        rng: Optional[np.random.Generator] = None,
    ) -> np.ndarray:
        """Generates Incident-Driven Missing Not At Random (MNAR) telemetry blackout mask.

        Severe failures cause exporter hangs and packet loss, heavily concentrated
        in the post-fault window (t >= inject_time) on the ground-truth root-cause service.

        Probability follows:
          P(M_t,m = 0) = sigmoid(gamma_0 + 2.5 * z_true(t, m) + 3.0 * I(m in M_rc and t >= inject_time))
        where gamma_0 is calibrated via bisection.
        """
        if p_miss <= 0.0:
            return np.ones(metrics_df.shape, dtype=np.uint8)
        if p_miss >= 1.0:
            return np.zeros(metrics_df.shape, dtype=np.uint8)

        if rng is None:
            rng = np.random.default_rng(self.seed)

        T, M = metrics_df.shape
        total_elements = T * M
        target_zeros = int(round(total_elements * p_miss))

        # 1. Zero-leakage pre-fault baseline statistics
        pre_fault_cutoff = max(5, inject_time_idx - 10)
        pre_data = metrics_df.iloc[:pre_fault_cutoff].values.astype(float)
        full_data = metrics_df.values.astype(float)

        medians_pre = np.nanmedian(pre_data, axis=0)
        q75 = np.nanpercentile(pre_data, 75, axis=0)
        q25 = np.nanpercentile(pre_data, 25, axis=0)
        iqr_pre = q75 - q25 + 1e-4

        # True deviation z_true(t, m)
        z_true = np.abs(full_data - medians_pre[None, :]) / iqr_pre[None, :]

        # 2. Root cause service indicator
        cols = list(metrics_df.columns)
        rc_indicator = np.zeros((T, M), dtype=float)
        for m_idx, col in enumerate(cols):
            svc = TelemetryAligner.extract_service_name(col)
            if svc == root_cause_service:
                rc_indicator[inject_time_idx:, m_idx] = 1.0

        # Raw logit score: 2.5 * z_true + 3.0 * rc_indicator
        base_logits = 2.5 * z_true + 3.0 * rc_indicator

        # Uniform noise for deterministic bisection
        u_matrix = rng.uniform(size=(T, M))

        rc_cols = np.where(rc_indicator[-1, :] > 0)[0]
        non_rc_cols = np.where(rc_indicator[-1, :] == 0)[0]

        def evaluate_gamma(gamma: float) -> Tuple[int, np.ndarray]:
            probs = _sigmoid(gamma + base_logits)
            starts = (u_matrix < probs).astype(np.uint8)
            dilated = np.zeros((T, M), dtype=np.uint8)
            if len(non_rc_cols) > 0:
                dilated[:, non_rc_cols] = maximum_filter1d(starts[:, non_rc_cols], size=15, axis=0, origin=-7)
            if len(rc_cols) > 0:
                dilated[:, rc_cols] = maximum_filter1d(starts[:, rc_cols], size=25, axis=0, origin=-12)
            sub_mask = 1 - dilated
            return int(np.sum(sub_mask == 0)), sub_mask

        # Bisection on gamma_0 in [-30.0, 30.0]
        low, high = -30.0, 30.0
        best_mask = None

        for _ in range(25):
            mid = 0.5 * (low + high)
            zeros, m_res = evaluate_gamma(mid)
            best_mask = m_res

            if abs(zeros - target_zeros) <= max(1, int(0.01 * total_elements)):
                break
            if zeros < target_zeros:
                low = mid
            else:
                high = mid

        mask = best_mask.copy()

        # Fine-tune to match exact tolerance +-0.01
        diff = target_zeros - np.sum(mask == 0)
        if diff > 0:
            # Drop more in post-fault or highest logits
            candidates = np.argwhere(mask == 1)
            if len(candidates) > 0:
                weights = base_logits[candidates[:, 0], candidates[:, 1]]
                weights = weights - np.min(weights) + 1e-3
                weights = weights / np.sum(weights)
                pick = rng.choice(len(candidates), size=min(diff, len(candidates)), replace=False, p=weights)
                mask[candidates[pick, 0], candidates[pick, 1]] = 0
        elif diff < 0:
            # Restore lowest logits
            candidates = np.argwhere(mask == 0)
            if len(candidates) > 0:
                weights = 1.0 / (base_logits[candidates[:, 0], candidates[:, 1]] + 1e-2)
                weights = weights / np.sum(weights)
                pick = rng.choice(len(candidates), size=min(-diff, len(candidates)), replace=False, p=weights)
                mask[candidates[pick, 0], candidates[pick, 1]] = 1

        return mask

    def apply_corruption(
        self,
        case: TelemetryCase,
        mechanism: str = "MCAR",
        p_miss: float = 0.2,
        seed: Optional[int] = None,
    ) -> Tuple[Dict[str, List[float]], np.ndarray]:
        """Applies missingness to a TelemetryCase without mutating original case data.

        Returns:
            (corrupted_metrics_dict, mask_matrix)
        """
        run_seed = seed if seed is not None else self.seed
        rng = np.random.default_rng(run_seed)

        df = pd.DataFrame(case.metrics_data)
        T, M = df.shape

        if p_miss <= 0.0:
            mask = np.ones((T, M), dtype=np.uint8)
            return dict(case.metrics_data), mask

        # Find inject_time index
        timestamps = np.array(case.timestamps)
        inject_indices = np.where(timestamps >= case.inject_time)[0]
        inject_idx = int(inject_indices[0]) if len(inject_indices) > 0 else T // 2

        mech_upper = mechanism.upper()
        if mech_upper == "MCAR":
            mask = self.generate_mcar_mask((T, M), p_miss, block=True, l_bar=15, rng=rng)
        elif mech_upper == "MAR":
            mask = self.generate_mar_mask(df, p_miss, block_len=10, rng=rng)
        elif mech_upper == "MNAR":
            mask = self.generate_mnar_mask(
                df,
                inject_time_idx=inject_idx,
                root_cause_service=case.root_cause_service,
                p_miss=p_miss,
                rng=rng,
            )
        else:
            raise ValueError(f"Unknown missingness mechanism: {mechanism}")

        # Corrupt values with NaN where mask == 0
        corrupted_dict = {}
        for col_idx, col in enumerate(df.columns):
            vals = df[col].to_numpy(dtype=float, copy=True)
            vals[mask[:, col_idx] == 0] = np.nan
            corrupted_dict[col] = vals.tolist()

        return corrupted_dict, mask


def apply_stale_freeze(
    df: pd.DataFrame,
    service: str,
    start_idx: int,
    duration: int,
) -> Tuple[pd.DataFrame, np.ndarray]:
    """Simulates a hung Prometheus exporter by repeating constant values for `duration` steps.

    Args:
        df: Input metrics DataFrame (NOT mutated).
        service: Target microservice whose exporter hangs.
        start_idx: Time-step index where freeze begins.
        duration: Number of frozen time-steps.

    Returns:
        (corrupted_df, freeze_mask): Tuple of corrupted DataFrame and boolean freeze matrix.
    """
    corrupted_df = df.copy()
    T, M = df.shape
    freeze_mask = np.zeros((T, M), dtype=np.uint8)

    end_idx = min(T, start_idx + duration)
    if start_idx <= 0 or start_idx >= T or end_idx <= start_idx:
        return corrupted_df, freeze_mask

    for col_idx, col in enumerate(df.columns):
        svc = TelemetryAligner.extract_service_name(col)
        if svc == service:
            # Freeze value at start_idx - 1
            frozen_val = df.iloc[start_idx - 1, col_idx]
            corrupted_df.iloc[start_idx:end_idx, col_idx] = frozen_val
            freeze_mask[start_idx:end_idx, col_idx] = 1

    return corrupted_df, freeze_mask


def apply_tag_corruption(
    columns: Sequence[str],
    p_tag: float,
    seed: int = 42,
) -> List[str]:
    """Corrupts/strips service prefixes on a fraction p_tag of metric names.

    Args:
        columns: Original metric column names.
        p_tag: Fraction of columns to corrupt in [0.0, 1.0].
        seed: Random seed.

    Returns:
        New list of column names with corrupted tags.
    """
    rng = np.random.default_rng(seed)
    cols = list(columns)
    n_corrupt = int(round(len(cols) * p_tag))

    if n_corrupt <= 0:
        return cols

    indices = rng.choice(len(cols), size=min(n_corrupt, len(cols)), replace=False)
    for idx in indices:
        orig = cols[idx]
        if "_" in orig:
            # Strip prefix or mangle it
            parts = orig.split("_", 1)
            cols[idx] = f"corrupted_{parts[1]}"
        else:
            cols[idx] = f"unknown_{orig}"

    return cols


def apply_adversarial_spoofing(
    case: TelemetryCase,
    service: Optional[str] = None,
    seed: int = 42,
    inject_schema_violation: bool = True,
) -> Tuple[TelemetryCase, np.ndarray]:
    """Simulates Adversarial Telemetry Spoofing ('AI Oops').

    An attacker or faulty agent overwrites the failing service's post-fault spike
    with synthetic Gaussian noise matching pre-fault mean/std (to fool naive z-score/BARO),
    while breaking cross-metric correlation (causing Consistency S to drop)
    and injecting physical bound violations (causing Validity V to drop).

    Args:
        case: Input TelemetryCase (not mutated).
        service: Target service to spoof (defaults to case.root_cause_service).
        seed: Random seed for noise generation.
        inject_schema_violation: If True, injects negative domain violations to drop Validity V.

    Returns:
        (spoofed_case, spoof_mask): Corrupted TelemetryCase and binary spoofing indicator mask.
    """
    rng = np.random.default_rng(seed)
    target_service = service or case.root_cause_service
    timestamps = np.array(case.timestamps)
    inject_idx = next(
        (i for i, t in enumerate(timestamps) if t >= case.inject_time),
        len(timestamps) // 2,
    )
    pre_fault_cutoff = max(5, inject_idx - 10)

    spoofed_metrics: Dict[str, List[float]] = {}
    T = len(timestamps)
    columns = list(case.metrics_data.keys())
    M = len(columns)
    spoof_mask = np.zeros((T, M), dtype=np.uint8)

    for col_idx, col in enumerate(columns):
        svc = TelemetryAligner.extract_service_name(col)
        arr = np.array(case.metrics_data[col], dtype=float)

        if svc == target_service:
            pre_vals = arr[:pre_fault_cutoff]
            mu = float(np.mean(pre_vals))
            sigma = float(np.std(pre_vals))
            sigma = max(1e-3, sigma)

            post_len = T - inject_idx
            noise = rng.normal(loc=mu, scale=sigma, size=post_len)

            if inject_schema_violation:
                violation_indices = rng.choice(post_len, size=max(1, int(post_len * 0.8)), replace=False)
                noise[violation_indices] = -np.abs(noise[violation_indices]) - 0.5

            spoofed_arr = arr.copy()
            spoofed_arr[inject_idx:] = noise
            spoofed_metrics[col] = spoofed_arr.tolist()
            spoof_mask[inject_idx:, col_idx] = 1
        else:
            spoofed_metrics[col] = list(arr)

    spoofed_case = TelemetryCase(
        case_id=f"{case.case_id}-spoofed",
        system=case.system,
        metrics_data=spoofed_metrics,
        timestamps=case.timestamps,
        inject_time=case.inject_time,
        root_cause_service=case.root_cause_service,
        root_cause_indicator=case.root_cause_indicator,
        data_source_tag=case.data_source_tag,
    )
    return spoofed_case, spoof_mask
