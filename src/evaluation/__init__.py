"""Evaluation, metrics, statistical testing, and paper export suite."""

from src.evaluation.ablations import run_ablation_suite
from src.evaluation.exporter import PaperEvidenceExporter
from src.evaluation.metrics_rca import compute_rca_metrics
from src.evaluation.metrics_selective import (
    compute_expected_calibration_error,
    compute_selective_metrics,
)
from src.evaluation.metrics_tsad import (
    compare_vus_pr_vs_paf1,
    compute_detection_delay,
    compute_faph,
    compute_point_adjusted_f1,
    compute_range_auc_pr,
    compute_vus_pr,
)
from src.evaluation.statistics import (
    compute_bootstrap_ci,
    compute_cliffs_delta,
    holm_bonferroni_correction,
    run_friedman_test,
    run_paired_wilcoxon_test,
)

__all__ = [
    "compute_vus_pr",
    "compute_range_auc_pr",
    "compute_faph",
    "compute_detection_delay",
    "compute_point_adjusted_f1",
    "compare_vus_pr_vs_paf1",
    "compute_rca_metrics",
    "compute_selective_metrics",
    "compute_expected_calibration_error",
    "compute_cliffs_delta",
    "compute_bootstrap_ci",
    "run_paired_wilcoxon_test",
    "run_friedman_test",
    "holm_bonferroni_correction",
    "run_ablation_suite",
    "PaperEvidenceExporter",
]
