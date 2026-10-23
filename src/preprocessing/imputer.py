"""Leakage-Safe Causal Telemetry Imputation and Epistemic Uncertainty Estimation.

Zero-Leakage Guarantee:
  - All imputations use strictly past or pre-fault data (t' <= t).
  - Post-fault future values NEVER leak backward into pre-fault windows.
  - KNNImputer is fitted strictly on pre-fault baseline data (t < inject_time - 10s).
"""

from typing import Dict, Literal, Optional, Tuple, Union
import numpy as np
import pandas as pd
from sklearn.impute import KNNImputer


class CausalImputer:
    """Causal, leakage-safe imputer for multi-metric telemetry time-series."""

    def __init__(
        self,
        method: Literal["zero_fill", "forward_fill", "linear_interp", "knn_imputer"] = "forward_fill",
        window_size: int = 60,
    ):
        self.method = method
        self.window_size = window_size

    def impute(
        self,
        metrics_df: pd.DataFrame,
        mask: np.ndarray,
        inject_time_idx: Optional[int] = None,
    ) -> pd.DataFrame:
        """Causally imputes missing values in metrics_df guided by binary mask.

        Args:
            metrics_df: DataFrame of telemetry values (T, M), potentially containing NaNs.
            mask: Binary mask (T, M) where 1=observed, 0=missing.
            inject_time_idx: Time-step index of fault injection (for zero-leakage pre-fault baselines).

        Returns:
            imputed_df: Completely filled DataFrame without NaNs or future leakage.
        """
        T, M = metrics_df.shape
        df_copy = metrics_df.copy()
        raw_vals = df_copy.values.astype(float)

        # Enforce that positions where mask == 0 are treated as missing
        raw_vals[mask == 0] = np.nan

        pre_cutoff = max(5, (inject_time_idx - 10) if inject_time_idx is not None else T // 3)
        pre_fault_data = raw_vals[:pre_cutoff]
        pre_medians = np.nanmedian(pre_fault_data, axis=0)
        # Fallback if pre-fault column is entirely NaN
        pre_medians = np.where(np.isnan(pre_medians), 0.0, pre_medians)

        if self.method == "zero_fill":
            out_vals = np.where(np.isnan(raw_vals), 0.0, raw_vals)

        elif self.method == "forward_fill":
            out_vals = raw_vals.copy()
            for m in range(M):
                last_valid = pre_medians[m]
                for t in range(T):
                    if np.isnan(out_vals[t, m]):
                        out_vals[t, m] = last_valid
                    else:
                        last_valid = out_vals[t, m]

        elif self.method == "linear_interp":
            out_vals = raw_vals.copy()
            for m in range(M):
                # Strictly causal linear interpolation/extrapolation:
                # never look ahead into t' > t
                last_seen_val = pre_medians[m]
                second_last_val = pre_medians[m]
                last_seen_t = -1
                second_last_t = -2

                for t in range(T):
                    if not np.isnan(out_vals[t, m]):
                        second_last_val = last_seen_val
                        second_last_t = last_seen_t
                        last_seen_val = out_vals[t, m]
                        last_seen_t = t
                    else:
                        # Causal linear projection from last two observations
                        if last_seen_t >= 0 and second_last_t >= 0 and (last_seen_t > second_last_t):
                            slope = (last_seen_val - second_last_val) / (last_seen_t - second_last_t)
                            extrapolated = last_seen_val + slope * (t - last_seen_t)
                            # Bound extrapolation to prevent runaway divergence
                            out_vals[t, m] = np.clip(
                                extrapolated,
                                pre_medians[m] - 5 * abs(pre_medians[m] + 1.0),
                                pre_medians[m] + 5 * abs(pre_medians[m] + 1.0),
                            )
                        else:
                            out_vals[t, m] = last_seen_val

        elif self.method == "knn_imputer":
            # ZERO LEAKAGE: Fit KNN strictly on pre-fault window
            pre_clean = pre_fault_data.copy()
            # If pre-fault window has missing values, forward-fill pre_clean first
            for m in range(M):
                last_v = pre_medians[m]
                for t in range(len(pre_clean)):
                    if np.isnan(pre_clean[t, m]):
                        pre_clean[t, m] = last_v
                    else:
                        last_v = pre_clean[t, m]

            imputer = KNNImputer(n_neighbors=min(5, max(1, pre_cutoff - 1)))
            imputer.fit(pre_clean)

            # Transform row-by-row or full array
            try:
                out_vals = imputer.transform(raw_vals)
                # Fallback any remaining NaNs
                out_vals = np.where(np.isnan(out_vals), pre_medians[None, :], out_vals)
            except Exception:
                # Fallback to forward-fill if singular
                out_vals = np.where(np.isnan(raw_vals), pre_medians[None, :], raw_vals)

        else:
            raise ValueError(f"Unknown imputation method: {self.method}")

        return pd.DataFrame(out_vals, columns=metrics_df.columns, index=metrics_df.index)

    def impute_dict(
        self,
        metrics_dict: Dict[str, list[float]],
        mask: np.ndarray,
        inject_time_idx: Optional[int] = None,
    ) -> Dict[str, list[float]]:
        """Fast dict-based causal imputation avoiding pandas DataFrame round-trip overhead."""
        columns = list(metrics_dict.keys())
        raw_vals = np.column_stack([np.array(metrics_dict[c], dtype=float) for c in columns])
        T, M = raw_vals.shape
        raw_vals[mask == 0] = np.nan

        pre_cutoff = max(5, (inject_time_idx - 10) if inject_time_idx is not None else T // 3)
        pre_fault_data = raw_vals[:pre_cutoff]
        pre_medians = np.nanmedian(pre_fault_data, axis=0)
        pre_medians = np.where(np.isnan(pre_medians), 0.0, pre_medians)

        out_vals = raw_vals.copy()
        for m in range(M):
            last_valid = pre_medians[m]
            for t in range(T):
                if np.isnan(out_vals[t, m]):
                    out_vals[t, m] = last_valid
                else:
                    last_valid = out_vals[t, m]

        return {c: out_vals[:, i].tolist() for i, c in enumerate(columns)}


def compute_imputation_uncertainty(
    mask: np.ndarray,
    metrics_data: np.ndarray,
    pre_fault_cutoff: int,
    window_slice: Optional[slice] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Computes point-wise uncertainty U(m, t) and window uncertainty U(m, w).

    Args:
        mask: Binary mask matrix (T, M), where 1=observed, 0=missing.
        metrics_data: Telemetry array (T, M).
        pre_fault_cutoff: Index separating pre-fault baseline from post-fault window.
        window_slice: Optional slice for evaluation window w (default full series).

    Returns:
        (U_point, U_window): Point uncertainty matrix (T, M) and window uncertainty array (M,).
    """
    T, M = mask.shape
    pre_cutoff = max(5, pre_fault_cutoff)
    pre_data = metrics_data[:pre_cutoff]

    # Pre-fault IQR per metric
    q75_pre = np.nanpercentile(pre_data, 75, axis=0)
    q25_pre = np.nanpercentile(pre_data, 25, axis=0)
    iqr_pre = q75_pre - q25_pre + 1e-4

    w_slice = window_slice if window_slice is not None else slice(0, T)
    w_data = metrics_data[w_slice]
    N_w = float(len(range(*w_slice.indices(T))))

    # 1. Contiguous gap length g(m, t) up to time t
    gap_matrix = np.zeros((T, M), dtype=float)
    for m in range(M):
        is_zero = (mask[:, m] == 0)
        if not np.any(is_zero):
            continue
        c = 0.0
        for t in range(T):
            if is_zero[t]:
                c += 1.0
                gap_matrix[t, m] = c
            else:
                c = 0.0

    # 2. Local volatility ratio over evaluation window
    local_q75 = np.nanpercentile(w_data, 75, axis=0)
    local_q25 = np.nanpercentile(w_data, 25, axis=0)
    local_iqr = local_q75 - local_q25 + 1e-4
    vol_ratio = (local_iqr / iqr_pre)[None, :]

    # 3. Point uncertainty: U(m, t) = (1 - M_{m,t}) * tanh(1.5 * (g(m, t) / N_w) * vol_ratio)
    u_point = (1.0 - mask) * np.tanh(1.5 * (gap_matrix / max(1.0, N_w)) * vol_ratio)
    u_point = np.clip(u_point, 0.0, 1.0)

    # 4. Window uncertainty U(m, w) = mean_{t in w} U(m, t)
    u_window = np.mean(u_point[w_slice], axis=0)
    u_window = np.clip(u_window, 0.0, 1.0)

    return u_point, u_window


def compute_certainty_after_imputation(
    mask: np.ndarray,
    metrics_data: np.ndarray,
    pre_fault_cutoff: int,
    window_slice: Optional[slice] = None,
) -> np.ndarray:
    """Computes Certainty After Imputation Q(m, w) = 1.0 - U(m, w) bounded in [0.0, 1.0]."""
    _, u_window = compute_imputation_uncertainty(
        mask=mask,
        metrics_data=metrics_data,
        pre_fault_cutoff=pre_fault_cutoff,
        window_slice=window_slice,
    )
    return np.clip(1.0 - u_window, 0.0, 1.0)
