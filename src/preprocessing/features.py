"""Feature extraction pipeline for telemetry anomaly detection.

Extracts rolling statistical moments, robust z-scores, velocity,
and observation mask metadata so downstream models are aware of imputed values.
"""

from typing import Optional
import numpy as np
import pandas as pd


def extract_features(
    df_imputed: pd.DataFrame,
    mask: np.ndarray,
    window_size: int = 60,
    pre_fault_cutoff: Optional[int] = None,
) -> pd.DataFrame:
    """Extracts leakage-safe statistical features and quality indicators for every metric.

    Args:
        df_imputed: Imputed telemetry DataFrame (T, M).
        mask: Observation mask matrix (T, M) where 1=observed, 0=missing.
        window_size: Rolling window size for causal rolling statistics.
        pre_fault_cutoff: Pre-fault baseline index for baseline normalization.

    Returns:
        features_df: Multi-feature DataFrame containing raw, rolling moments,
                     velocity, observation mask, and rolling completeness.
    """
    T, M = df_imputed.shape
    feature_dict: dict[str, np.ndarray] = {}

    pre_cutoff = pre_fault_cutoff if pre_fault_cutoff is not None else T // 3
    pre_data = df_imputed.iloc[:pre_cutoff].values.astype(float)
    pre_median = np.median(pre_data, axis=0)
    pre_q75 = np.percentile(pre_data, 75, axis=0)
    pre_q25 = np.percentile(pre_data, 25, axis=0)
    pre_iqr = pre_q75 - pre_q25 + 1e-4

    for m_idx, col in enumerate(df_imputed.columns):
        series = df_imputed[col]
        col_mask = pd.Series(mask[:, m_idx], index=series.index)

        # 1. Rolling median and rolling IQR
        roll_med = series.rolling(window=window_size, min_periods=1).median().values
        roll_q75 = series.rolling(window=window_size, min_periods=1).quantile(0.75).values
        roll_q25 = series.rolling(window=window_size, min_periods=1).quantile(0.25).values
        roll_iqr = roll_q75 - roll_q25 + 1e-4

        # 2. Robust z-score against pre-fault baseline (zero leakage)
        z_pre = (series.values - pre_median[m_idx]) / pre_iqr[m_idx]

        # 3. First-difference velocity
        velocity = series.diff(1).fillna(0.0).values

        # 4. Observation mask & rolling completeness
        roll_comp = col_mask.rolling(window=window_size, min_periods=1).mean().values

        feature_dict[f"{col}__raw"] = series.values
        feature_dict[f"{col}__roll_median"] = roll_med
        feature_dict[f"{col}__roll_iqr"] = roll_iqr
        feature_dict[f"{col}__z_score"] = z_pre
        feature_dict[f"{col}__velocity"] = velocity
        feature_dict[f"{col}__mask"] = mask[:, m_idx]
        feature_dict[f"{col}__completeness"] = roll_comp

    return pd.DataFrame(feature_dict, index=df_imputed.index)
