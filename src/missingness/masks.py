"""Binary Mask Persistence and SHA-256 Integrity Verification.

Provides lossless storage and loading of binary observation masks:
  M in {0, 1}^{T x M} (1 = observed, 0 = missing)
with cryptographically verified SHA-256 checksums.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional, Tuple
import numpy as np


def compute_sha256(file_path: Path | str) -> str:
    """Computes SHA-256 checksum for a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def save_mask(
    mask: np.ndarray,
    file_path: Path | str,
    metadata: Optional[dict] = None,
) -> str:
    """Saves a binary observation mask matrix as a compressed .npz file.

    Args:
        mask: 2D array of shape (T, M), dtype bool or int (1=observed, 0=missing).
        file_path: Target path (e.g. data/masks/case_01_mcar_0.2.npz).
        metadata: Optional metadata dictionary (e.g. mechanism, p_miss, seed).

    Returns:
        sha256: Hex digest of the saved file.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    mask_bool = np.asarray(mask, dtype=np.uint8)
    meta_json = json.dumps(metadata or {})

    # Save compressed npz
    np.savez_compressed(path, mask=mask_bool, metadata=meta_json)
    return compute_sha256(path)


def load_mask(
    file_path: Path | str,
    expected_sha256: Optional[str] = None,
) -> Tuple[np.ndarray, dict]:
    """Loads a binary observation mask matrix and verifies its integrity.

    Args:
        file_path: Path to .npz mask file.
        expected_sha256: Optional SHA-256 hex string to verify against.

    Returns:
        (mask, metadata): Tuple of binary mask array (uint8) and metadata dictionary.

    Raises:
        ValueError: If SHA-256 checksum does not match expected_sha256.
        FileNotFoundError: If file_path does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Mask file not found: {path}")

    actual_sha = compute_sha256(path)
    if expected_sha256 is not None and actual_sha != expected_sha256:
        raise ValueError(
            f"SHA-256 verification failed for {path}!\n"
            f"Expected: {expected_sha256}\n"
            f"Actual:   {actual_sha}"
        )

    with np.load(path, allow_pickle=False) as data:
        mask = data["mask"]
        meta_str = str(data["metadata"])
        metadata = json.loads(meta_str) if meta_str else {}

    return mask, metadata
