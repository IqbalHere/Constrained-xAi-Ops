"""Explainability, TreeSHAP attribution, and fidelity modules."""

from src.explainability.fidelity import (
    compute_fidelity_at_k,
    compute_jaccard_at_k,
    evaluate_explanation_fidelity,
    match_indicator,
)
from src.explainability.shap_explainer import (
    MissingnessAwareSHAPExplainer,
    compute_gini_index,
)

__all__ = [
    "MissingnessAwareSHAPExplainer",
    "compute_gini_index",
    "match_indicator",
    "compute_fidelity_at_k",
    "compute_jaccard_at_k",
    "evaluate_explanation_fidelity",
]
