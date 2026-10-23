"""Constrained-xAIOps: Master Reproducibility & Publication Runner.

Executes end-to-end verification of all scientific claims, provenance,
citations, test suites, and operational dashboards.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def run_step(name: str, cmd: list) -> bool:
    print("\n" + "=" * 70)
    print(f"STEP: {name}")
    print(f"COMMAND: {' '.join(cmd)}")
    print("=" * 70)
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - t0
    if res.returncode == 0:
        print(f"[PASS] {name} completed successfully in {elapsed:.2f}s.")
        return True
    else:
        print(f"[FAIL] {name} failed with exit code {res.returncode} in {elapsed:.2f}s.")
        return False


def main():
    print("""
========================================================================
Constrained-xAIOps: Master IEEE Manuscript & Benchmark Reproducibility
Target: RCAEval Online Boutique (RE1-OB, 125 Cases, 5 Seeds, 16 Cores)
========================================================================
""")
    workspace_root = Path(__file__).resolve().parent.parent
    os.chdir(workspace_root)

    steps = [
        ("Secret & Credential Safety Audit", [sys.executable, "scripts/check_no_secrets.py"]),
        ("Paper Provenance & Numerical Integrity Audit", [sys.executable, "scripts/verify_paper_provenance.py"]),
        ("IEEE Citation & Manuscript Integrity Audit", [sys.executable, "scripts/audit_citations_and_claims.py"]),
        ("Complete Unit, Regression & Operational Test Suite", [sys.executable, "-m", "pytest", "tests/", "-v"]),
        ("Self-Contained IEEE Submission Bundle Generation", [sys.executable, "scripts/build_submission_bundle.py"]),
    ]

    all_passed = True
    for step_name, cmd in steps:
        success = run_step(step_name, cmd)
        if not success:
            all_passed = False
            break

    print("\n" + "=" * 70)
    if all_passed:
        print("MASTER REPRODUCIBILITY SUMMARY: ALL AUDITS & TESTS PASSED (100%)")
        print("=" * 70)
        print("""
Generated Camera-Ready Assets:
- Manuscript: paper/main.tex
- BibTeX Database: paper/references.bib
- Publication Tables: artifacts/tables/table1_main_missingness_grid.tex
                      artifacts/tables/table2_rca_retrieval_rerank_and_selective.tex
                      artifacts/tables/table3_ablations_and_xai.tex
                      artifacts/tables/table4_statistical_tests_and_efficiency.tex
                      artifacts/tables/table5_multisystem_zeroshot_and_security.tex
- Publication Figures: artifacts/figures/fig1_degradation_curves.pdf (.png)
                       artifacts/figures/fig2_risk_coverage_aurc.pdf (.png)
                       artifacts/figures/fig3_shap_fidelity_and_ablations.pdf (.png)
                       artifacts/figures/fig4_label_scarcity_and_imputers.pdf (.png)
                       artifacts/figures/fig5_multisystem_and_security.pdf (.png)
- Verified Metrics: artifacts/metrics/statistical_summary.json (1,962 metrics)
                    artifacts/metrics/phase6_multisystem_and_security.json (1,046 metrics)
- Submission Bundle: artifacts/Constrained_xAIOps_IEEE_Submission.zip (1-Click Overleaf Ready)

Interactive Operational Dashboard Launch:
- Streamlit UI: streamlit run src/dashboard/app.py
- FastAPI Backend: uvicorn src.dashboard.api:app --host 127.0.0.1 --port 8000
""")
        sys.exit(0)
    else:
        print("MASTER REPRODUCIBILITY SUMMARY: FAILED")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
