"""Regression test ensuring 100% paper evidence provenance and zero fabrication."""

import pytest
from scripts.verify_paper_provenance import verify_tables_and_figures


def test_paper_artifact_provenance():
    """Validates that all LaTeX tables and figures match statistical_summary.json."""
    is_valid = verify_tables_and_figures()
    assert is_valid is True, "Provenance verification failed: unverified numbers or missing artifacts found!"
