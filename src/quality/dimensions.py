"""The 5-Dimensional Telemetry Quality and Trust Evaluation Module.

Implements the five measurable dimensions of telemetry health:
  1. Completeness C(m, w): Observation density in evaluation window.
  2. Timeliness / Freshness L(m, w): Sampling delay and exporter stale-freeze penalty.
  3. Consistency S(m, w): Timestamp step regularity and cross-metric correlation stability.
  4. Validity & Tag Hygiene V(m, w): Schema compliance, valid service prefix, and physical bounds.
  5. Certainty After Imputation Q(m, w): Epistemic imputation uncertainty inverse (1 - U).

All dimensions are strictly bounded in [0.0, 1.0].
"""

from typing import Dict, List, Optional, Sequence, Set, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    KNOWN_SOCK_SHOP_SERVICES,
    TelemetryAligner,
)
from src.preprocessing.imputer import compute_imputation_uncertainty


def compute_completeness(
    mask: np.ndarray,
    window_slice: Optional[slice] = None,
) -> np.ndarray:
    """Computes Completeness C(m, w) = mean_{t in w}(M_{m,t}) in [0, 1].

    Args:
        mask: Observation mask matrix (T, M), 1=observed, 0=missing.
        window_slice: Slice for evaluation window w (default full series).

    Returns:
        C: Array of shape (M,) with completeness scores in [0.0, 1.0].
    """
    w_slice = window_slice if window_slice is not None else slice(0, mask.shape[0])
    sub_mask = mask[w_slice]
    if len(sub_mask) == 0:
        return np.ones(mask.shape[1], dtype=float)
    return np.clip(np.mean(sub_mask, axis=0), 0.0, 1.0)


def compute_timeliness(
    timestamps: Sequence[int],
    metrics_data: np.ndarray,
    pre_fault_cutoff: int,
    window_slice: Optional[slice] = None,
    nominal_dt: float = 1.0,
    lambda_lag: float = 0.25,
    columns: Optional[Sequence[str]] = None,
) -> np.ndarray:
    """Computes Timeliness / Freshness L(m, w) in [0, 1].

    Penalizes sampling delays beyond nominal dt and exporter stale-freeze hangs:
    Detects Stale-Freeze whenever the post-fault first-difference variance var(diff(X_post))
    drops by > 95% relative to var(diff(X_pre)) on any dynamic metric (std(X_pre) > 1e-5),
    driving L(m, w) down toward 0.10–0.25.

    Args:
        timestamps: Sequence of integer timestamps.
        metrics_data: Array of shape (T, M) of metric values.
        pre_fault_cutoff: Index separating pre-fault baseline from post-fault.
        window_slice: Evaluation window slice.
        nominal_dt: Expected sampling interval (default 1.0s).
        lambda_lag: Lag decay factor (default 0.25).
        columns: Optional sequence of metric column names for service-level freeze propagation.

    Returns:
        L: Array of shape (M,) with timeliness scores in [0.0, 1.0].
    """
    T, M = metrics_data.shape
    times = np.array(timestamps, dtype=float)

    # 1. Timestamp lag penalty
    dt_obs = np.diff(times, prepend=times[0] - nominal_dt)
    dt_obs = np.where(dt_obs <= 0, nominal_dt, dt_obs)
    excess_lag = np.maximum(0.0, (dt_obs - nominal_dt) / max(0.1, nominal_dt))
    lag_factor = np.exp(-lambda_lag * excess_lag)  # shape (T,)

    # 2. Stale-freeze detection
    pre_cutoff = max(5, pre_fault_cutoff)
    w_slice = window_slice if window_slice is not None else slice(0, T)

    col_svcs: List[str] = []
    if columns is not None and len(columns) == M:
        col_svcs = [TelemetryAligner.extract_service_name(c) for c in columns]

    svc_dyn_count: Dict[str, int] = {}
    svc_frozen_count: Dict[str, int] = {}
    frozen_metrics: Set[int] = set()

    for m in range(M):
        col_vals = metrics_data[:, m]
        pre_vals = col_vals[:pre_cutoff]
        post_vals = col_vals[w_slice]

        if len(pre_vals) > 5 and len(post_vals) > 5:
            var_pre = float(np.var(np.diff(pre_vals)))
            var_post = float(np.var(np.diff(post_vals)))
            std_pre = float(np.std(pre_vals))

            svc_m = col_svcs[m] if col_svcs else ""
            if std_pre > 1e-5 and var_pre > 1e-6:
                if svc_m:
                    svc_dyn_count[svc_m] = svc_dyn_count.get(svc_m, 0) + 1

                diffs_post = np.abs(np.diff(post_vals))
                flat_frac = float(np.mean(diffs_post < 1e-7)) if len(diffs_post) > 0 else 0.0

                diffs_all = np.abs(np.diff(col_vals))
                is_zero = (diffs_all < 1e-7).astype(int)
                max_run_all, cur_run = 0, 0
                for z in is_zero:
                    if z:
                        cur_run += 1
                        if cur_run > max_run_all:
                            max_run_all = cur_run
                    else:
                        cur_run = 0

                is_frozen = (var_post < 0.05 * var_pre and flat_frac > 0.70)
                if T <= 300 and max_run_all >= 40:
                    is_frozen = True

                if is_frozen:
                    frozen_metrics.add(m)
                    if svc_m:
                        svc_frozen_count[svc_m] = svc_frozen_count.get(svc_m, 0) + 1

    frozen_services: Set[str] = set()
    if col_svcs:
        for svc, dyn in svc_dyn_count.items():
            if dyn >= 1 and svc_frozen_count.get(svc, 0) >= max(1, int(0.5 * dyn)):
                frozen_services.add(svc)

    mean_lag = float(np.mean(lag_factor[w_slice]))
    l_window = np.full(M, mean_lag, dtype=float)

    # For any detected frozen dynamic metric in post-fault evaluation, drive L(m, w) down toward 0.15
    w_end = w_slice.stop if w_slice.stop is not None else T
    if w_end > pre_cutoff:
        for m in range(M):
            is_frozen = (m in frozen_metrics) or (bool(col_svcs) and col_svcs[m] in frozen_services)
            if is_frozen:
                l_window[m] = min(float(l_window[m]), 0.15)

    return np.clip(l_window, 0.0, 1.0)


def _detect_spoofed_services(
    metrics_data: np.ndarray,
    columns: Sequence[str],
    pre_fault_cutoff: int,
    window_slice: Optional[slice] = None,
) -> Set[str]:
    """Identifies microservices exhibiting adversarial telemetry spoofing ('AI Oops').

    Audits:
    1. Cross-metric rank correlation breakdown (|rho_pre(m, m') - rho_post(m, m')| > 0.45 among coupled metrics).
    2. High-frequency residual entropy mismatch / autocorrelation collapse (ratio R > 0.80).
    """
    T, M = metrics_data.shape
    pre_cutoff = max(5, pre_fault_cutoff)
    w_slice = window_slice if window_slice is not None else slice(pre_cutoff, T)

    col_services = [TelemetryAligner.extract_service_name(c) for c in columns]
    service_to_indices: Dict[str, list[int]] = {}
    for idx, svc in enumerate(col_services):
        if svc not in service_to_indices:
            service_to_indices[svc] = []
        service_to_indices[svc].append(idx)

    spoofed_services: Set[str] = set()

    for svc, indices in service_to_indices.items():
        if len(indices) < 2:
            continue

        sub_pre = metrics_data[:pre_cutoff, indices]
        sub_win = metrics_data[w_slice, indices]

        # 1. High-frequency residual entropy mismatch check:
        # r = var(diff(X)) / (2 * var(X))
        # Natural metrics have smooth autocorrelation (r < 0.60)
        # Synthetic Gaussian noise has r >= 0.80
        dyn_count = 0
        entropy_mismatches = 0
        for idx in range(len(indices)):
            pre_series = sub_pre[:, idx]
            win_series = sub_win[:, idx]
            if len(pre_series) > 5 and len(win_series) > 5:
                var_pre = float(np.var(pre_series))
                var_win = float(np.var(win_series))
                if var_pre > 1e-6 and var_win > 1e-6:
                    dyn_count += 1
                    diff_pre_var = float(np.var(np.diff(pre_series)))
                    diff_win_var = float(np.var(np.diff(win_series)))
                    r_pre = diff_pre_var / (2.0 * var_pre + 1e-9)
                    r_win = diff_win_var / (2.0 * var_win + 1e-9)
                    if r_pre < 0.60 and r_win > 0.80:
                        entropy_mismatches += 1

        # 2. Cross-metric rank correlation breakdown (|rho_pre - rho_post| > 0.45)
        ranks_pre = stats.rankdata(sub_pre, axis=0)
        ranks_win = stats.rankdata(sub_win, axis=0)
        corr_pre = np.nan_to_num(np.corrcoef(ranks_pre, rowvar=False), nan=0.0)
        corr_win = np.nan_to_num(np.corrcoef(ranks_win, rowvar=False), nan=0.0)

        if corr_pre.ndim == 0:
            corr_pre = np.array([[1.0, float(corr_pre)], [float(corr_pre), 1.0]])
            corr_win = np.array([[1.0, float(corr_win)], [float(corr_win), 1.0]])

        k = len(indices)
        coupled_drifts = []
        for i in range(k):
            for j in range(i + 1, k):
                if abs(corr_pre[i, j]) > 0.40:
                    coupled_drifts.append(abs(corr_pre[i, j] - corr_win[i, j]))

        mean_drift = float(np.mean(coupled_drifts)) if coupled_drifts else 0.0
        frac_broken = float(np.mean([d > 0.45 for d in coupled_drifts])) if coupled_drifts else 0.0
        has_negative_violation = bool(np.any(sub_win < -0.1))

        # Spoofing triggers when:
        # A) Both rank correlation breakdown AND residual entropy mismatch occur
        # B) Or significant entropy collapse on dynamic metrics alongside correlation drift
        # C) Or schema domain violations (negative values) alongside correlation collapse
        is_spoofed = False
        if dyn_count > 0:
            if entropy_mismatches >= 2 and (mean_drift > 0.45 or frac_broken > 0.50):
                is_spoofed = True
            elif (entropy_mismatches / dyn_count >= 0.35) and (mean_drift > 0.40 or frac_broken > 0.40):
                is_spoofed = True
            elif has_negative_violation and (mean_drift > 0.45 or frac_broken > 0.50 or entropy_mismatches >= 1):
                is_spoofed = True

        if is_spoofed:
            spoofed_services.add(svc)

    return spoofed_services


def compute_consistency(
    timestamps: Sequence[int],
    metrics_data: np.ndarray,
    columns: Sequence[str],
    pre_fault_cutoff: int,
    window_slice: Optional[slice] = None,
    nominal_dt: float = 1.0,
    spoofed_svcs: Optional[Set[str]] = None,
) -> np.ndarray:
    """Computes Consistency S(m, w) in [0, 1].

    Combines timestamp step regularity and cross-metric correlation stability.
    Penalizes adversarial telemetry spoofing when rank correlations break down or residual entropy collapses.
    """
    T, M = metrics_data.shape
    times = np.array(timestamps, dtype=float)

    # Step regularity
    dt_obs = np.diff(times, prepend=times[0] - nominal_dt)
    dt_obs = np.where(dt_obs <= 0, nominal_dt, dt_obs)
    w_slice = window_slice if window_slice is not None else slice(0, T)
    win_dt = dt_obs[w_slice]

    std_dt = float(np.std(win_dt))
    mean_dt = float(np.mean(win_dt))
    step_reg = 1.0 - (std_dt / (mean_dt + std_dt + 1e-4))
    step_reg = np.clip(step_reg, 0.0, 1.0)

    # Cross-metric correlation stability using fast NumPy corrcoef
    pre_cutoff = max(5, pre_fault_cutoff)
    with np.errstate(divide="ignore", invalid="ignore"):
        pre_corr = np.nan_to_num(np.corrcoef(metrics_data[:pre_cutoff], rowvar=False), nan=0.0)
        win_corr = np.nan_to_num(np.corrcoef(metrics_data[w_slice], rowvar=False), nan=0.0)

    if pre_corr.ndim == 0:
        pre_corr = np.array([[float(pre_corr)]])
    if win_corr.ndim == 0:
        win_corr = np.array([[float(win_corr)]])

    stability = np.zeros(M, dtype=float)
    col_services = [TelemetryAligner.extract_service_name(c) for c in columns]

    # Detect spoofed services if not already provided
    if spoofed_svcs is None:
        spoofed_svcs = _detect_spoofed_services(
            metrics_data=metrics_data,
            columns=columns,
            pre_fault_cutoff=pre_cutoff,
            window_slice=w_slice,
        )

    for m in range(M):
        svc_m = col_services[m]
        coupled = []
        for other in range(M):
            if other != m and col_services[other] == svc_m:
                if abs(pre_corr[m, other]) > 0.40:
                    coupled.append(other)

        if coupled:
            diffs = [abs(win_corr[m, c] - pre_corr[m, c]) for c in coupled]
            mean_drift = float(np.mean(diffs))
            stability[m] = np.clip(1.0 - (mean_drift / 2.0), 0.0, 1.0)
        else:
            stability[m] = 1.0

        if svc_m in spoofed_svcs:
            stability[m] = min(stability[m], 0.15)

    s_scores = 0.5 * (step_reg + stability)
    return np.clip(s_scores, 0.0, 1.0)


def compute_validity(
    metrics_data: np.ndarray,
    columns: Sequence[str],
    window_slice: Optional[slice] = None,
    pre_fault_cutoff: Optional[int] = None,
    spoofed_svcs: Optional[Set[str]] = None,
) -> np.ndarray:
    """Computes Validity & Tag Hygiene V(m, w) in [0, 1].

    Product of schema/tag validity and physical domain validity.
    Penalizes adversarial telemetry spoofing down toward 0.15 on spoofed microservices.
    """
    T, M = metrics_data.shape
    w_slice = window_slice if window_slice is not None else slice(0, T)
    sub_data = metrics_data[w_slice]

    v_scores = np.zeros(M, dtype=float)
    col_services = [TelemetryAligner.extract_service_name(c) for c in columns]

    # Detect spoofed services if pre_fault_cutoff is provided and spoofed_svcs is None
    if spoofed_svcs is None:
        if pre_fault_cutoff is not None:
            spoofed_svcs = _detect_spoofed_services(
                metrics_data=metrics_data,
                columns=columns,
                pre_fault_cutoff=pre_fault_cutoff,
                window_slice=w_slice,
            )
        else:
            spoofed_svcs = set()

    for m in range(M):
        col = str(columns[m])
        svc = col_services[m]
        all_valid_services = set(KNOWN_ONLINE_BOUTIQUE_SERVICES) | set(KNOWN_SOCK_SHOP_SERVICES)
        has_valid_tag = (
            (svc in all_valid_services or svc.startswith("ts-") or (len(svc) > 1 and not svc.startswith("corrupted") and not svc.startswith("unknown")))
            and ("_" in col)
            and (not col.startswith("corrupted"))
            and (not col.startswith("unknown"))
        )
        tag_score = 1.0 if has_valid_tag else 0.0

        if tag_score == 0.0:
            v_scores[m] = 0.0
            continue

        # Physical domain bounds: finite and non-negative
        vals = sub_data[:, m]
        finite_mask = np.isfinite(vals)
        non_neg_mask = vals[finite_mask] >= -1e-4

        if len(vals) > 0 and np.sum(finite_mask) > 0:
            domain_score = float(np.sum(non_neg_mask) / len(vals))
        else:
            domain_score = 1.0

        v_base = tag_score * np.clip(domain_score, 0.0, 1.0)
        if svc in spoofed_svcs:
            v_base = min(v_base, 0.15)
        v_scores[m] = v_base

    return np.clip(v_scores, 0.0, 1.0)


def compute_all_dimensions(
    mask: np.ndarray,
    metrics_data: np.ndarray,
    columns: Sequence[str],
    timestamps: Sequence[int],
    pre_fault_cutoff: int,
    window_slice: Optional[slice] = None,
) -> Dict[str, np.ndarray]:
    """Computes all 5 dimensions C, L, S, V, Q for every metric in window w.

    Returns:
        Dict with keys "C", "L", "S", "V", "Q", each an array of shape (M,).
    """
    # 0. Single-pass detection of spoofed services for S and V
    spoofed_svcs = _detect_spoofed_services(
        metrics_data=metrics_data,
        columns=columns,
        pre_fault_cutoff=pre_fault_cutoff,
        window_slice=window_slice,
    )

    # 1. Completeness C
    c_scores = compute_completeness(mask, window_slice=window_slice)

    # 2. Timeliness L
    l_scores = compute_timeliness(
        timestamps=timestamps,
        metrics_data=metrics_data,
        columns=columns,
        pre_fault_cutoff=pre_fault_cutoff,
        window_slice=window_slice,
    )

    # 3. Consistency S
    s_scores = compute_consistency(
        timestamps=timestamps,
        metrics_data=metrics_data,
        columns=columns,
        pre_fault_cutoff=pre_fault_cutoff,
        window_slice=window_slice,
        spoofed_svcs=spoofed_svcs,
    )

    # 4. Validity V
    v_scores = compute_validity(
        metrics_data=metrics_data,
        columns=columns,
        window_slice=window_slice,
        pre_fault_cutoff=pre_fault_cutoff,
        spoofed_svcs=spoofed_svcs,
    )

    # 5. Certainty Q = 1 - U
    _, u_window = compute_imputation_uncertainty(
        mask=mask,
        metrics_data=metrics_data,
        pre_fault_cutoff=pre_fault_cutoff,
        window_slice=window_slice,
    )
    q_scores = np.clip(1.0 - u_window, 0.0, 1.0)

    return {
        "C": c_scores,
        "L": l_scores,
        "S": s_scores,
        "V": v_scores,
        "Q": q_scores,
    }
