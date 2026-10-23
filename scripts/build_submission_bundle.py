#!/usr/bin/env python3
"""Build Self-Contained Overleaf / IEEE Camera-Ready Submission Bundle.

Packages:
1. main.tex (with paths adjusted to local tables/ and figures/ for 1-click Overleaf compilation)
2. references.bib (complete BibTeX library)
3. tables/table1_*.tex through table5_*.tex
4. figures/fig1_*.pdf through fig5_*.pdf and .png
into artifacts/Constrained_xAIOps_IEEE_Submission.zip.
"""

import os
import re
import sys
import zipfile
from pathlib import Path


def build_submission_bundle(
    workspace_root: Path,
    output_zip: Path,
) -> bool:
    print("=" * 70)
    print("Building Self-Contained IEEE / Overleaf Submission Bundle")
    print("=" * 70)

    paper_dir = workspace_root / "paper"
    tables_dir = workspace_root / "artifacts" / "tables"
    figures_dir = workspace_root / "artifacts" / "figures"

    main_tex_path = paper_dir / "main.tex"
    references_bib_path = paper_dir / "references.bib"

    if not main_tex_path.exists():
        print(f"[FAIL] Missing {main_tex_path}")
        return False
    if not references_bib_path.exists():
        print(f"[FAIL] Missing {references_bib_path}")
        return False

    output_zip.parent.mkdir(parents=True, exist_ok=True)

    # 1. Read main.tex and adjust paths for self-contained Overleaf directory layout
    raw_tex = main_tex_path.read_text(encoding="utf-8")
    adjusted_tex = re.sub(r"\.\./artifacts/tables/", "tables/", raw_tex)
    adjusted_tex = re.sub(r"\.\./artifacts/figures/", "figures/", adjusted_tex)

    # Verify all expected tables and figures
    tables = [
        "table1_main_missingness_grid.tex",
        "table2_rca_retrieval_rerank_and_selective.tex",
        "table3_ablations_and_xai.tex",
        "table4_statistical_tests_and_efficiency.tex",
        "table5_multisystem_zeroshot_and_security.tex",
    ]

    figures = [
        "fig1_degradation_curves.pdf",
        "fig1_degradation_curves.png",
        "fig2_risk_coverage_aurc.pdf",
        "fig2_risk_coverage_aurc.png",
        "fig3_shap_fidelity_and_ablations.pdf",
        "fig3_shap_fidelity_and_ablations.png",
        "fig4_label_scarcity_and_imputers.pdf",
        "fig4_label_scarcity_and_imputers.png",
        "fig5_multisystem_and_security.pdf",
        "fig5_multisystem_and_security.png",
    ]

    for t in tables:
        t_path = tables_dir / t
        if not t_path.exists():
            print(f"[FAIL] Missing table file: {t_path}")
            return False

    for f in figures:
        f_path = figures_dir / f
        if not f_path.exists():
            print(f"[FAIL] Missing figure file: {f_path}")
            return False

    # 2. Assemble zip archive
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write adjusted main.tex
        zf.writestr("main.tex", adjusted_tex)
        print("  + Added: main.tex (Overleaf relative paths adjusted)")

        # Write references.bib
        zf.write(references_bib_path, arcname="references.bib")
        print("  + Added: references.bib")

        # Write tables/
        for t in tables:
            t_path = tables_dir / t
            zf.write(t_path, arcname=f"tables/{t}")
            print(f"  + Added: tables/{t}")

        # Write figures/
        for f in figures:
            f_path = figures_dir / f
            zf.write(f_path, arcname=f"figures/{f}")
            print(f"  + Added: figures/{f}")

    print("\n" + "=" * 70)
    total_bytes = output_zip.stat().st_size
    print(f"[SUCCESS] Submission bundle created: {output_zip}")
    print(f"  Size: {total_bytes:,} bytes ({total_bytes / (1024*1024):.2f} MB)")
    print("  Ready for 1-click upload to Overleaf and IEEE Manuscript Central!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    import shutil
    root = Path(__file__).resolve().parent.parent
    out_zip = root / "artifacts" / "Constrained_xAIOps_IEEE_Submission.zip"
    ok = build_submission_bundle(root, out_zip)
    if ok:
        pkg_zip = root / "FINAL_SUBMISSION_PACKAGE" / "02_Constrained_xAIOps_Overleaf_Source.zip"
        pkg_zip.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_zip, pkg_zip)
        print(f"  + Synced to: {pkg_zip}")

        # Sync IEEE PDF if present
        pdf_src = root / "paper" / "Constrained_xAIOps_IEEE.pdf"
        if not pdf_src.exists():
            pdf_src = root / "paper" / "main.pdf"
        if pdf_src.exists():
            pdf_dst = root / "FINAL_SUBMISSION_PACKAGE" / "01_Constrained_xAIOps_IEEE_Manuscript.pdf"
            shutil.copy2(pdf_src, pdf_dst)
            print(f"  + Synced manuscript PDF to: {pdf_dst}")

    sys.exit(0 if ok else 1)
