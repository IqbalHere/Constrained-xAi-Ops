"""Weight Calibration and Dirichlet Sensitivity Analysis for Telemetry Trust Scores.

Provides:
  - Equal weighting: [0.2, 0.2, 0.2, 0.2, 0.2]
  - Calibrated logistic regression weighting: (d_1..d_5) -> hit_at_3
  - Dirichlet sensitivity engine: samples 100 weight vectors from Dirichlet(1,1,1,1,1)
"""

from typing import Dict, List, Literal, Optional, Sequence, Tuple
import numpy as np
from sklearn.linear_model import LogisticRegression

DIMENSION_NAMES = ["C", "L", "S", "V", "Q"]


def get_equal_weights() -> np.ndarray:
    """Returns uniform weights [0.2, 0.2, 0.2, 0.2, 0.2]."""
    return np.array([0.2, 0.2, 0.2, 0.2, 0.2], dtype=float)


def get_completeness_only_weights() -> np.ndarray:
    """Returns completeness-only weights [1.0, 0.0, 0.0, 0.0, 0.0] for ablation studies."""
    return np.array([1.0, 0.0, 0.0, 0.0, 0.0], dtype=float)


def calibrate_logistic_weights(
    dimension_matrix: np.ndarray,
    rca_hit_labels: Sequence[int],
    c_reg: float = 1.0,
) -> np.ndarray:
    """Fits L2-regularized LogisticRegression to calibrate dimension weights.

    Args:
        dimension_matrix: Array of shape (N_samples, 5) with [C, L, S, V, Q] values.
        rca_hit_labels: Binary labels indicating successful RCA hit (e.g. hit_at_3).
        c_reg: Inverse regularization parameter C.

    Returns:
        weights: Normalized positive weight vector of shape (5,) summing to 1.0.
    """
    labels = np.asarray(rca_hit_labels, dtype=int)
    if len(np.unique(labels)) < 2:
        # Single class: fallback to equal weights
        return get_equal_weights()

    clf = LogisticRegression(C=c_reg, penalty="l2", solver="lbfgs", max_iter=500)
    clf.fit(dimension_matrix, labels)

    coef = clf.coef_[0]
    pos_coef = np.clip(coef, 0.0, None)
    s = float(np.sum(pos_coef))
    if s < 1e-6:
        return get_equal_weights()

    return pos_coef / s


def run_dirichlet_sensitivity(
    dimensions_dict: Dict[str, float],
    n_draws: int = 100,
    alpha: Optional[Sequence[float]] = None,
    seed: int = 42,
) -> Dict[str, float]:
    """Evaluates Trust Score stability across random simplex weight vectors.

    Samples weight vectors from Dirichlet(alpha) to quantify sensitivity to weighting choices.

    Args:
        dimensions_dict: Dictionary with keys "C", "L", "S", "V", "Q".
        n_draws: Number of Dirichlet Monte Carlo draws (default 100).
        alpha: Dirichlet concentration parameter (default [1.0, 1.0, 1.0, 1.0, 1.0]).
        seed: Random seed.

    Returns:
        Dictionary with mean, std, median, iqr, min, and max composite scores.
    """
    rng = np.random.default_rng(seed)
    if alpha is None:
        alpha = [1.0, 1.0, 1.0, 1.0, 1.0]

    # Sample weight vectors from Dirichlet distribution: shape (n_draws, 5)
    weights = rng.dirichlet(alpha, size=n_draws)

    d_vector = np.array([
        dimensions_dict.get("C", 1.0),
        dimensions_dict.get("L", 1.0),
        dimensions_dict.get("S", 1.0),
        dimensions_dict.get("V", 1.0),
        dimensions_dict.get("Q", 1.0),
    ], dtype=float)

    # Multiplicative floor: if V == 0 or C == 0, score is 0
    v_val = dimensions_dict.get("V", 1.0)
    c_val = dimensions_dict.get("C", 1.0)
    floor = 1.0 if (v_val > 0.0 and c_val > 0.0) else 0.0

    scores = floor * np.dot(weights, d_vector)
    scores = np.clip(scores, 0.0, 1.0)

    q75, q25 = np.percentile(scores, [75, 25])

    return {
        "n_draws": float(n_draws),
        "mean_score": float(np.mean(scores)),
        "std_score": float(np.std(scores)),
        "median_score": float(np.median(scores)),
        "iqr_score": float(q75 - q25),
        "min_score": float(np.min(scores)),
        "max_score": float(np.max(scores)),
    }
