"""Explanation Fidelity, Stability, and Sparsity Evaluation Engine.

Evaluates objective explanation quality:
1. Indicator Fidelity@1 and Fidelity@3 against ground-truth root-cause indicators.
2. Explanation Stability (Jaccard@3) under telemetry corruption vs. 0% Oracle baseline.
3. Gini Sparsity Index for operator cognitive load.
"""

from typing import Dict, List, Sequence, Set
import numpy as np


def match_indicator(metric_name: str, gt_indicator: str) -> bool:
    """Checks whether a metric name matches the ground truth failure indicator."""
    m_lower = metric_name.lower()
    gt_lower = gt_indicator.lower()

    if gt_lower in m_lower:
        return True

    # Semantic synonym mappings
    synonyms = {
        "cpu": ["cpu", "load", "throttling"],
        "mem": ["mem", "memory", "working_set", "rss"],
        "memory": ["mem", "memory", "working_set", "rss"],
        "disk": ["disk", "fs", "storage", "io"],
        "latency": ["latency", "duration", "response_time", "rtt"],
        "net": ["net", "network", "rx", "tx", "bytes_received", "bytes_transmitted"],
    }

    for key, terms in synonyms.items():
        if key in gt_lower:
            if any(term in m_lower for term in terms):
                return True

    return False


def compute_fidelity_at_k(ranked_metrics: Sequence[str], gt_indicator: str, k: int = 1) -> float:
    """Returns 1.0 if ground-truth indicator is matched in the top-k ranked metrics, else 0.0."""
    top_k = ranked_metrics[:k]
    return 1.0 if any(match_indicator(m, gt_indicator) for m in top_k) else 0.0


def compute_jaccard_at_k(set_a: Sequence[str], set_b: Sequence[str], k: int = 3) -> float:
    """Computes Jaccard set similarity between top-k metric subsets in [0.0, 1.0]."""
    s_a = set(set_a[:k])
    s_b = set(set_b[:k])
    if not s_a and not s_b:
        return 1.0
    union = s_a | s_b
    if not union:
        return 1.0
    return float(len(s_a & s_b) / len(union))


def evaluate_explanation_fidelity(
    expl_corrupted: Dict[str, object],
    expl_oracle: Dict[str, object],
    gt_indicator: str,
) -> Dict[str, float]:
    """Computes comprehensive fidelity, stability, and sparsity metrics for an explanation."""
    ranked_corr = list(expl_corrupted.get("ranked_metrics", []))
    ranked_ora = list(expl_oracle.get("ranked_metrics", []))

    f1 = compute_fidelity_at_k(ranked_corr, gt_indicator, k=1)
    f3 = compute_fidelity_at_k(ranked_corr, gt_indicator, k=3)
    f1_ora = compute_fidelity_at_k(ranked_ora, gt_indicator, k=1)
    f3_ora = compute_fidelity_at_k(ranked_ora, gt_indicator, k=3)

    jaccard3 = compute_jaccard_at_k(ranked_corr, ranked_ora, k=3)

    return {
        "fidelity_at_1": float(f1),
        "fidelity_at_3": float(f3),
        "oracle_fidelity_at_1": float(f1_ora),
        "oracle_fidelity_at_3": float(f3_ora),
        "jaccard_at_3": float(jaccard3),
        "gini_sparsity": float(expl_corrupted.get("gini_sparsity", 0.0)),
        "reliability_score": float(expl_corrupted.get("reliability_score", 1.0)),
    }
