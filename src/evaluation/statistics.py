"""Non-Parametric Statistical Testing & Effect Size Suite.

Implements:
1. Paired Wilcoxon Signed-Rank Test (scipy.stats.wilcoxon).
2. Multi-method Friedman Test (scipy.stats.friedmanchisquare).
3. Holm-Bonferroni Step-Down Multiple-Comparison Correction.
4. Cliff's Delta non-parametric effect size with Romano magnitude classification.
5. Non-parametric 95% Bootstrap Confidence Intervals (n_boot = 1000).
"""

from typing import Dict, List, Sequence, Tuple
import numpy as np
import scipy.stats as stats


def compute_cliffs_delta(x: Sequence[float], y: Sequence[float]) -> Tuple[float, str]:
    """Computes Cliff's Delta non-parametric effect size and magnitude category.

    Formula: d = (sum_{i,j} sign(x_i - y_j)) / (n_x * n_y)
    Categories (Romano et al., 2006):
    - |d| < 0.147: 'negligible'
    - 0.147 <= |d| < 0.33: 'small'
    - 0.33 <= |d| < 0.474: 'medium'
    - |d| >= 0.474: 'large'
    """
    x_arr = np.array(x, dtype=float)
    y_arr = np.array(y, dtype=float)
    n_x, n_y = len(x_arr), len(y_arr)

    if n_x == 0 or n_y == 0:
        return 0.0, "negligible"

    # Vectorized computation
    diff_matrix = x_arr[:, np.newaxis] - y_arr[np.newaxis, :]
    delta = float(np.mean(np.sign(diff_matrix)))

    abs_d = abs(delta)
    if abs_d < 0.147:
        magnitude = "negligible"
    elif abs_d < 0.33:
        magnitude = "small"
    elif abs_d < 0.474:
        magnitude = "medium"
    else:
        magnitude = "large"

    return round(delta, 4), magnitude


def compute_bootstrap_ci(
    data: Sequence[float],
    n_boot: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Computes mean and non-parametric bootstrap confidence interval [ci_lower, ci_upper]."""
    arr = np.array(data, dtype=float)
    n = len(arr)
    if n == 0:
        return 0.0, 0.0, 0.0

    mean_val = float(np.mean(arr))
    if n == 1 or np.std(arr) < 1e-12:
        return round(mean_val, 4), round(mean_val, 4), round(mean_val, 4)

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        boot_means[i] = np.mean(sample)

    alpha = 1.0 - confidence_level
    lower_pct = (alpha / 2.0) * 100.0
    upper_pct = (1.0 - alpha / 2.0) * 100.0

    ci_lower = float(np.percentile(boot_means, lower_pct))
    ci_upper = float(np.percentile(boot_means, upper_pct))

    return round(mean_val, 4), round(ci_lower, 4), round(ci_upper, 4)


def run_paired_wilcoxon_test(
    scores_a: Sequence[float],
    scores_b: Sequence[float],
) -> Dict[str, float]:
    """Runs a two-sided paired Wilcoxon signed-rank test between two paired arrays."""
    a = np.array(scores_a, dtype=float)
    b = np.array(scores_b, dtype=float)

    diffs = a - b
    # Filter out exact zero differences
    non_zero = diffs[diffs != 0]

    if len(non_zero) < 5:
        # Fallback if too few non-zero differences
        return {"statistic": 0.0, "p_value": 1.0}

    try:
        res = stats.wilcoxon(a, b, alternative="two-sided")
        stat = float(res.statistic)
        p_val = float(res.pvalue)
    except Exception:
        stat, p_val = 0.0, 1.0

    return {"statistic": round(stat, 4), "p_value": round(p_val, 6)}


def run_friedman_test(
    *methods_scores: Sequence[float],
) -> Dict[str, float]:
    """Runs Friedman chi-square test across 3 or more paired methods."""
    if len(methods_scores) < 3:
        return {"statistic": 0.0, "p_value": 1.0}

    try:
        res = stats.friedmanchisquare(*methods_scores)
        stat = float(res.statistic)
        p_val = float(res.pvalue)
    except Exception:
        stat, p_val = 0.0, 1.0

    return {"statistic": round(stat, 4), "p_value": round(p_val, 6)}


def holm_bonferroni_correction(
    p_values: Dict[str, float],
    alpha: float = 0.05,
) -> Dict[str, Dict[str, object]]:
    """Performs Holm-Bonferroni step-down multiple-comparison correction."""
    m = len(p_values)
    if m == 0:
        return {}

    # Sort comparisons by ascending raw p-value
    sorted_items = sorted(p_values.items(), key=lambda x: x[1])
    adjusted_results: Dict[str, Dict[str, object]] = {}

    cum_max = 0.0
    for rank_idx, (name, raw_p) in enumerate(sorted_items, start=1):
        adjusted_p = min(1.0, (m - rank_idx + 1) * raw_p)
        # Enforce monotonicity
        cum_max = max(cum_max, adjusted_p)
        cum_max = min(1.0, cum_max)

        is_significant = bool(cum_max < alpha)
        adjusted_results[name] = {
            "raw_p": round(raw_p, 6),
            "adjusted_p": round(cum_max, 6),
            "significant_at_05": is_significant,
            "rank": rank_idx,
        }

    return adjusted_results
