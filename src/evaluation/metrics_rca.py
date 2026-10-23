"""Root Cause Analysis (RCA) Evaluation Metrics Suite.

Implements:
1. Top-k Accuracy (AC@1, AC@3, AC@5, Avg@5), MRR, Chance@5, and Lift@5.
2. NeurIPS 2026 RCAEval Retrieval-Reranking Decomposition:
   - Retrieval@5: P(RootCause in Top5) = AC@5
   - Rerank@1: P(Rank == 1 | Rank <= 5) = AC@1 / (AC@5 + 1e-12)
"""

from typing import Dict, List, Sequence
import numpy as np

from src.schemas import RCAResult


def compute_rca_metrics(
    results: Sequence[RCAResult],
    num_total_services: int = 10,
) -> Dict[str, float]:
    """Computes comprehensive RCA ranking and retrieval-reranking metrics."""
    n = len(results)
    if n == 0:
        return {
            "AC@1": 0.0,
            "AC@3": 0.0,
            "AC@5": 0.0,
            "Avg@5": 0.0,
            "MRR": 0.0,
            "Chance@5": 5.0 / float(num_total_services),
            "Lift@5": 0.0,
            "Retrieval@5": 0.0,
            "Rerank@1": 0.0,
            "mean_runtime_ms": 0.0,
        }

    ac1 = float(np.mean([1.0 if r.hit_at_1 else 0.0 for r in results]))
    ac3 = float(np.mean([1.0 if r.hit_at_3 else 0.0 for r in results]))
    ac5 = float(np.mean([1.0 if r.hit_at_5 else 0.0 for r in results]))
    avg5 = (ac1 + ac3 + ac5) / 3.0
    mrr = float(np.mean([r.reciprocal_rank for r in results]))

    chance5 = 5.0 / float(num_total_services)
    lift5 = ac5 - chance5

    # Retrieval-Reranking Decomposition
    retrieval5 = ac5
    rerank1 = ac1 / (ac5 + 1e-12) if ac5 > 0 else 0.0
    rerank1 = float(np.clip(rerank1, 0.0, 1.0))

    runtime = float(np.mean([r.runtime_ms for r in results]))

    return {
        "AC@1": round(ac1, 4),
        "AC@3": round(ac3, 4),
        "AC@5": round(ac5, 4),
        "Avg@5": round(avg5, 4),
        "MRR": round(mrr, 4),
        "Chance@5": round(chance5, 4),
        "Lift@5": round(lift5, 4),
        "Retrieval@5": round(retrieval5, 4),
        "Rerank@1": round(rerank1, 4),
        "mean_runtime_ms": round(runtime, 3),
    }
