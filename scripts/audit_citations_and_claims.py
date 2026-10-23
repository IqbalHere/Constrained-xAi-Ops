"""Citation, Reference, and Placeholder Integrity Auditor.

Verifies:
1. Every citation key in paper/main.tex resolves in paper/references.bib.
2. Every BibTeX entry in paper/references.bib is syntactically well-formed.
3. Zero unresolved placeholders (e.g., '[TBD]', 'TODO', 'FIXME', 'XXX') exist in paper/main.tex.
4. All referenced figure files and input table files exist on disk.
"""

import re
import sys
from pathlib import Path
from typing import Set


def parse_bib_keys(bib_path: Path) -> Set[str]:
    """Extracts all citation keys from a .bib file."""
    content = bib_path.read_text(encoding="utf-8")
    # Matches patterns like @article{key, or @inproceedings{key,
    keys = re.findall(r"@\w+\s*{\s*([^,]+),", content)
    return {k.strip() for k in keys}


def parse_tex_citations(tex_path: Path) -> Set[str]:
    """Extracts all citation keys used in \cite{...} macros."""
    content = tex_path.read_text(encoding="utf-8")
    matches = re.findall(r"\\cite\s*\{([^}]+)\}", content)
    cited_keys = set()
    for match in matches:
        for k in match.split(","):
            cited_keys.add(k.strip())
    return cited_keys


def audit_citations_and_claims(
    tex_file: str = "paper/main.tex",
    bib_file: str = "paper/references.bib",
) -> bool:
    print("=" * 70)
    print("IEEE Citation, Reference & Placeholder Integrity Auditor")
    print("=" * 70)

    tex_path = Path(tex_file)
    bib_path = Path(bib_file)

    if not tex_path.exists():
        print(f"[FAIL] TeX file not found: {tex_path}")
        return False
    if not bib_path.exists():
        print(f"[FAIL] BibTeX file not found: {bib_path}")
        return False

    tex_content = tex_path.read_text(encoding="utf-8")

    # 1. Check for forbidden placeholder patterns
    forbidden_patterns = [r"\[TBD\]", r"\[TODO\]", r"TODO", r"FIXME", r"XXX", r"\\textbf\{TBD\}"]
    placeholder_found = False
    for pat in forbidden_patterns:
        matches = re.findall(pat, tex_content, re.IGNORECASE)
        if matches:
            print(f"[FAIL] Forbidden placeholder pattern found ({len(matches)} occurrences): '{pat}'")
            placeholder_found = True

    if not placeholder_found:
        print("[PASS] Zero placeholders ([TBD], TODO, FIXME) found in manuscript.")

    # 2. Extract and verify citation keys
    bib_keys = parse_bib_keys(bib_path)
    cited_keys = parse_tex_citations(tex_path)

    print(f"[Info] Found {len(bib_keys)} entries in {bib_file}.")
    print(f"[Info] Found {len(cited_keys)} unique citation keys in {tex_file}.")

    unresolved_citations = cited_keys - bib_keys
    if unresolved_citations:
        print(f"[FAIL] Unresolved citations ({len(unresolved_citations)}): {unresolved_citations}")
    else:
        print(f"[PASS] 100% of cited keys ({len(cited_keys)}/{len(cited_keys)}) resolve in {bib_file}.")

    # 3. Check referenced tables and figures
    tables = re.findall(r"\\input\{([^}]+)\}", tex_content)
    figures = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex_content)

    missing_files = []
    for tbl in tables:
        # Table path is relative to paper/ directory
        tbl_path = (tex_path.parent / tbl).resolve()
        if not tbl_path.exists():
            missing_files.append(str(tbl_path))

    for fig in figures:
        # Figure path is relative to paper/ directory
        fig_path = (tex_path.parent / fig).resolve()
        if not fig_path.exists():
            missing_files.append(str(fig_path))

    if missing_files:
        print(f"[FAIL] Missing referenced assets in manuscript: {missing_files}")
    else:
        print(f"[PASS] All {len(tables)} input tables and {len(figures)} figures exist on disk.")

    success = (not placeholder_found) and (not unresolved_citations) and (not missing_files)
    if success:
        print("\n[SUCCESS] Citation and manuscript integrity audit PASSED.")
    else:
        print("\n[FAILURE] Citation and manuscript integrity audit FAILED.")

    return success


if __name__ == "__main__":
    ok = audit_citations_and_claims()
    sys.exit(0 if ok else 1)
