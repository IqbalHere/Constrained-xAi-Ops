"""Time-Series Anomaly Detection (TSAD) Evaluation Suite.

Implements:
1. Volume Under the Surface PR (VUS-PR) and Range-AUC-PR over continuous buffer tolerance lengths.
2. Standard AUC-PR and False Alerts Per Hour (FAPH).
3. Detection Delay (seconds to first true anomaly alert).
4. Diagnostic comparison demonstrating Point-Adjusted F1 (PA-F1) inflation vs. VUS-PR.
"""

from typing import Dict, List, Sequence, Tuple
import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve, auc

# Safe trapezoid function
if hasattr(np, "trapezoid"):
    _trapz = np.trapezoid
elif hasattr(np, "trapz"):
    _trapz = np.trapz
else:
    import scipy.integrate
    _trapz = scipy.integrate.trapezoid


def expand_anomaly_regions(y_true: np.ndarray, buffer_len: int) -> np.ndarray:
    """Expands contiguous positive segments in binary y_true by buffer_len timestamps."""
    if buffer_len <= 0:
        return y_true.copy()
    n = len(y_true)
    expanded = np.zeros(n, dtype=int)
    for i in range(n):
        if y_true[i] == 1:
            start = max(0, i - buffer_len)
            end = min(n, i + buffer_len + 1)
            expanded[start:end] = 1
    return expanded


def compute_range_auc_pr(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    buffer_len: int = 5,
) -> float:
    """Computes Range-based AUC-PR with buffer tolerance window."""
    if len(y_true) == 0 or np.sum(y_true) == 0:
        return 0.0
    y_expanded = expand_anomaly_regions(y_true, buffer_len)
    if np.sum(y_expanded) == 0 or np.sum(y_expanded) == len(y_true):
        return float(np.mean(y_true))
    prec, rec, _ = precision_recall_curve(y_expanded, y_scores)
    # Sort for monotonic trapezoid
    sorted_indices = np.argsort(rec)
    area = float(_trapz(prec[sorted_indices], rec[sorted_indices]))
    return float(np.clip(area, 0.0, 1.0))


def compute_vus_pr(
    y_true: Sequence[int],
    y_scores: Sequence[float],
    buffer_lengths: Sequence[int] = (0, 5, 10, 15, 20),
) -> float:
    """Computes Volume Under the Surface PR (VUS-PR) across buffer lengths."""
    y_t = np.array(y_true, dtype=int)
    y_s = np.array(y_scores, dtype=float)
    if len(y_t) == 0 or np.sum(y_t) == 0:
        return 0.0

    auc_pr_curves = []
    for l_buf in buffer_lengths:
        r_auc = compute_range_auc_pr(y_t, y_s, buffer_len=l_buf)
        auc_pr_curves.append(r_auc)

    max_buf = max(buffer_lengths)
    if max_buf == 0:
        return auc_pr_curves[0]

    # Integrate across buffer tolerance axis
    norm_buffers = [b / float(max_buf) for b in buffer_lengths]
    vus = float(_trapz(auc_pr_curves, norm_buffers))
    return float(np.clip(vus, 0.0, 1.0))


def compute_faph(
    pre_fault_scores: Sequence[float],
    duration_sec: float,
    threshold: float = 0.35,
) -> float:
    """Computes False Alerts Per Hour (FAPH) on normal baseline windows."""
    if duration_sec <= 0:
        return 0.0
    scores = np.array(pre_fault_scores, dtype=float)
    false_alerts = int(np.sum(scores >= threshold))
    hours = duration_sec / 3600.0
    return float(false_alerts / hours)


def compute_detection_delay(
    post_fault_scores: Sequence[float],
    sampling_interval_sec: float = 1.0,
    threshold: float = 0.35,
) -> float:
    """Computes Detection Delay in seconds to first anomaly alert."""
    scores = np.array(post_fault_scores, dtype=float)
    alert_indices = np.where(scores >= threshold)[0]
    if len(alert_indices) > 0:
        return float(alert_indices[0] * sampling_interval_sec)
    return float(len(scores) * sampling_interval_sec)


def compute_point_adjusted_f1(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    threshold: float = 0.35,
) -> float:
    """Point-Adjusted F1 (PA-F1): flags whole anomaly segment if a single point triggers."""
    y_pred = (y_scores >= threshold).astype(int)
    y_adj = y_pred.copy()
    n = len(y_true)

    # Find contiguous anomaly segments
    in_segment = False
    seg_start = 0
    for i in range(n):
        if y_true[i] == 1 and not in_segment:
            in_segment = True
            seg_start = i
        elif y_true[i] == 0 and in_segment:
            in_segment = False
            if np.sum(y_pred[seg_start:i]) > 0:
                y_adj[seg_start:i] = 1
    if in_segment and np.sum(y_pred[seg_start:n]) > 0:
        y_adj[seg_start:n] = 1

    tp = np.sum((y_adj == 1) & (y_true == 1))
    fp = np.sum((y_adj == 1) & (y_true == 0))
    fn = np.sum((y_adj == 0) & (y_true == 1))

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2.0 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return float(f1)


def compare_vus_pr_vs_paf1(
    n_points: int = 500,
    anomaly_start: int = 300,
    anomaly_end: int = 400,
    noise_seed: int = 42,
) -> Dict[str, float]:
    """Diagnostic function demonstrating PA-F1 inflation on white noise vs. VUS-PR."""
    rng = np.random.default_rng(noise_seed)
    y_true = np.zeros(n_points, dtype=int)
    y_true[anomaly_start:anomaly_end] = 1

    # Simulated noisy detector: completely random uniform noise
    y_scores_random = rng.uniform(0.0, 0.40, size=n_points)
    # A single random spike hits the anomaly window
    y_scores_random[anomaly_start + 10] = 0.90

    pa_f1 = compute_point_adjusted_f1(y_true, y_scores_random, threshold=0.35)
    vus_pr = compute_vus_pr(y_true, y_scores_random)
    standard_auc_pr = float(average_precision_score(y_true, y_scores_random))

    return {
        "paf1_inflated_score": round(pa_f1, 4),
        "vus_pr_score": round(vus_pr, 4),
        "standard_auc_pr": round(standard_auc_pr, 4),
        "inflation_gap": round(pa_f1 - vus_pr, 4),
    }
