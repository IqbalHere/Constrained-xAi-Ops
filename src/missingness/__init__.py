"""Missingness and telemetry corruption mechanisms."""

from src.missingness.generator import (
    MissingnessGenerator,
    apply_stale_freeze,
    apply_tag_corruption,
)
from src.missingness.masks import (
    save_mask,
    load_mask,
    compute_sha256,
)

__all__ = [
    "MissingnessGenerator",
    "apply_stale_freeze",
    "apply_tag_corruption",
    "save_mask",
    "load_mask",
    "compute_sha256",
]
