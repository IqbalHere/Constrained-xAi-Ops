"""Selective classification, conformal calibration, and abstention mechanisms."""

from src.abstention.conformal import (
    AdaptiveNonExchangeableConformalCalibrator,
    calibrate_conformal_threshold,
    compute_risk_coverage_curve,
)
from src.abstention.mnar_escalator import detect_mnar_blackout
from src.abstention.selective_gate import SelectiveGate, decide_service

__all__ = [
    "AdaptiveNonExchangeableConformalCalibrator",
    "calibrate_conformal_threshold",
    "compute_risk_coverage_curve",
    "detect_mnar_blackout",
    "decide_service",
    "SelectiveGate",
]
