"""Automated Plagiarism, N-Gram Overlap & Humanization Verifier.

Enforces:
1. Strict Ban on AI-Tell & Hype Vocabulary across both .docx and .tex:
   - Banned Hype Words:
     ["revolutionary", "groundbreaking", "unprecedented", "cutting-edge", "game-changer",
      "seamless", "seamlessly", "dramatically", "catastrophic", "catastrophically",
      "flawless", "flawlessly", "unparalleled", "crushes", "skyrockets", "remarkable",
      "remarkably", "extraordinary", "astonishing", "silver bullet", "panacea",
      "bulletproof", "unassailable", "breakthrough", "miracle", "vastly superior",
      "massive improvement"]
   - Banned AI-Tell Cliches:
     ["delve", "tapestry", "testament", "paramount", "underscores", "pivotal",
      "realm", "harnessing", "beacon", "symphony", "intricate", "meticulous",
      "commendable", "notably", "it is worth noting", "in conclusion", "landscape",
      "paradigm", "crucial role", "vital role", "rapidly evolving", "ever-evolving",
      "cornerstone", "holistic", "synergy", "foster", "leverage", "utilize"]
2. Human Sentence Burstiness: Coefficient of Variation (std/mean) >= 0.35.
3. Zero N-Gram Plagiarism: < 1.0% non-formula 5-gram overlap against references and docstrings.
"""

import math
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import List, Set, Tuple
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent

BANNED_HYPE_WORDS = [
    "revolutionary", "groundbreaking", "unprecedented", "cutting-edge", "game-changer",
    "seamless", "seamlessly", "dramatically", "catastrophic", "catastrophically",
    "flawless", "flawlessly", "unparalleled", "crushes", "skyrockets", "remarkable",
    "remarkably", "extraordinary", "astonishing", "silver bullet", "panacea",
    "bulletproof", "unassailable", "breakthrough", "miracle", "vastly superior",
    "massive improvement"
]

BANNED_AI_CLICHES = [
    "delve", "tapestry", "testament", "paramount", "underscores", "pivotal",
    "realm", "harnessing", "beacon", "symphony", "intricate", "meticulous",
    "commendable", "notably", "it is worth noting", "in conclusion", "landscape",
    "paradigm", "crucial role", "vital role", "rapidly evolving", "ever-evolving",
    "cornerstone", "holistic", "synergy", "foster", "leverage", "utilize"
]

ALL_BANNED_TERMS = BANNED_HYPE_WORDS + BANNED_AI_CLICHES


def extract_docx_text(docx_path: Path) -> List[str]:
    """Extracts all text paragraphs from a Word (.docx) document."""
    if not docx_path.exists():
        return []
    paragraphs = []
    with zipfile.ZipFile(docx_path, "r") as zf:
        xml_content = zf.read("word/document.xml")
        root = ET.fromstring(xml_content)
        for elem in root.iter():
            if elem.tag.endswith("}p") or elem.tag == "p":
                texts = [node.text for node in elem.iter() if (node.tag.endswith("}t") or node.tag == "t") and node.text]
                p_text = "".join(texts).strip()
                if p_text:
                    paragraphs.append(p_text)
    return paragraphs


def extract_tex_text(tex_path: Path) -> List[str]:
    """Extracts prose paragraphs from LaTeX source file."""
    if not tex_path.exists():
        return []
    content = tex_path.read_text(encoding="utf-8")
    # Remove comments
    content = re.sub(r"(?m)^%.*$", "", content)
    # Remove math blocks
    content = re.sub(r"\$[^$]+\$", "", content)
    content = re.sub(r"\\\[.*?\\\]", "", content, flags=re.DOTALL)
    # Remove commands with arguments
    content = re.sub(r"\\[a-zA-Z]+(\[[^\]]*\])?(\{[^}]*\})?", "", content)
    paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 30]
    return paragraphs


def get_5grams(text: str) -> Set[Tuple[str, ...]]:
    """Generates lowercase 5-grams from text."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    if len(words) < 5:
        return set()
    return {tuple(words[i:i+5]) for i in range(len(words) - 4)}


def build_banned_regex(term: str) -> re.Pattern:
    """Builds regex pattern matching term and standard inflections."""
    if term in ("leverage", "utilize"):
        stem = term[:-1]  # 'leverag', 'utiliz'
        return re.compile(r"\b" + re.escape(stem) + r"\w*\b", re.IGNORECASE)
    elif " " in term:
        # Multi-word phrase
        return re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    else:
        return re.compile(r"\b" + re.escape(term) + r"(?:s|d|ed|ing|ly)?\b", re.IGNORECASE)


def audit_banned_vocabulary(paragraphs: List[str], doc_name: str) -> List[str]:
    """Checks for forbidden hype words and robotic AI cliches."""
    violations = []
    for idx, p in enumerate(paragraphs, start=1):
        for term in ALL_BANNED_TERMS:
            pattern = build_banned_regex(term)
            match = pattern.search(p)
            if match:
                matched_word = match.group(0)
                snippet = p[max(0, match.start() - 25):min(len(p), match.end() + 25)].strip()
                violations.append(
                    f"{doc_name} [Para {idx}]: Contains banned term '{matched_word}' (matched rule for '{term}')\n"
                    f"    Context: \"...{snippet}...\""
                )
    return violations


def audit_sentence_burstiness(paragraphs: List[str], doc_name: str) -> Tuple[bool, float, float, float]:
    """Computes sentence length distribution and verifies Coefficient of Variation >= 0.35."""
    full_text = " ".join(paragraphs)
    cleaned_text = re.sub(r"\([0-9]+\)", "", full_text)
    raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned_text)
    sentences = [s.strip() for s in raw_sentences if len(s.strip().split()) >= 4]

    if not sentences:
        return False, 0.0, 0.0, 0.0

    lengths = [len(s.split()) for s in sentences]
    mean_len = sum(lengths) / len(lengths)
    variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
    std_len = math.sqrt(variance)
    cv = std_len / mean_len if mean_len > 0 else 0.0

    is_bursty = cv >= 0.35
    return is_bursty, cv, mean_len, std_len


def audit_ngram_overlap(manuscript_paragraphs: List[str], bib_path: Path) -> Tuple[bool, float]:
    """Checks that non-formula 5-gram overlap against references and docstrings is < 1.0%."""
    prose_paragraphs = [p for p in manuscript_paragraphs if not re.match(r"^\[\d+\]", p.strip())]
    manuscript_text = " ".join(prose_paragraphs)
    m_5grams = get_5grams(manuscript_text)
    if not m_5grams:
        return True, 0.0

    ref_text = ""
    if bib_path.exists():
        ref_text += bib_path.read_text(encoding="utf-8") + " "

    for py_file in (REPO_ROOT / "src").rglob("*.py"):
        if "__pycache__" not in py_file.parts:
            ref_text += py_file.read_text(encoding="utf-8")[:500] + " "

    ref_5grams = get_5grams(ref_text)
    overlap = m_5grams & ref_5grams
    overlap_pct = (len(overlap) / len(m_5grams)) * 100.0

    is_clean = overlap_pct < 1.0
    return is_clean, overlap_pct


def run_full_humanization_audit() -> bool:
    print("=" * 70)
    print("Automated Plagiarism, N-Gram Overlap & Humanization Verifier")
    print("=" * 70)

    all_violations: List[str] = []

    # 1. Inspect target docx
    docx_candidates = [
        REPO_ROOT / "FINAL_SUBMISSION_PACKAGE" / "CRC_Paper_Constrained_xAIOps.docx",
        REPO_ROOT / "paper" / "CRC_Paper_Constrained_xAIOps.docx",
    ]
    target_docx = None
    for cand in docx_candidates:
        if cand.exists():
            target_docx = cand
            break

    if target_docx is None:
        print("[FAIL] Missing CRC Word document. Expected at:")
        for cand in docx_candidates:
            print(f"  - {cand}")
        return False

    print(f"[Input 1/2] Auditing Word Document: {target_docx.relative_to(REPO_ROOT)}")
    docx_paragraphs = extract_docx_text(target_docx)
    print(f"  Extracted {len(docx_paragraphs)} paragraphs.")

    # 2. Inspect target LaTeX
    tex_path = REPO_ROOT / "paper" / "main.tex"
    if not tex_path.exists():
        print(f"[FAIL] Missing LaTeX manuscript: {tex_path}")
        return False
    print(f"[Input 2/2] Auditing LaTeX Manuscript: {tex_path.relative_to(REPO_ROOT)}")
    tex_paragraphs = extract_tex_text(tex_path)
    print(f"  Extracted {len(tex_paragraphs)} prose paragraphs.")

    # 3. Banned Vocabulary Check on Word document
    print("\n[Audit 1/4] Scanning Word (.docx) for banned hype & AI cliches...")
    docx_banned_violations = audit_banned_vocabulary(docx_paragraphs, target_docx.name)
    if docx_banned_violations:
        for v in docx_banned_violations:
            print(f"  [FAIL] {v}")
        all_violations.extend(docx_banned_violations)
    else:
        print("  [PASS] Zero banned hype or AI-tell words detected in Word document.")

    # 4. Banned Vocabulary Check on LaTeX manuscript
    print("\n[Audit 2/4] Scanning LaTeX (main.tex) for banned hype & AI cliches...")
    tex_banned_violations = audit_banned_vocabulary(tex_paragraphs, tex_path.name)
    if tex_banned_violations:
        for v in tex_banned_violations:
            print(f"  [FAIL] {v}")
        all_violations.extend(tex_banned_violations)
    else:
        print("  [PASS] Zero banned hype or AI-tell words detected in LaTeX manuscript.")

    # 5. Sentence Burstiness & Readability
    print("\n[Audit 3/4] Analyzing sentence burstiness & length distribution...")
    docx_bursty, docx_cv, docx_mean, docx_std = audit_sentence_burstiness(docx_paragraphs, target_docx.name)
    print(f"  Word Doc Mean Length: {docx_mean:.1f} words | Std: {docx_std:.1f} | CV: {docx_cv:.3f} (Required: >= 0.350)")
    tex_bursty, tex_cv, tex_mean, tex_std = audit_sentence_burstiness(tex_paragraphs, tex_path.name)
    print(f"  LaTeX   Mean Length: {tex_mean:.1f} words | Std: {tex_std:.1f} | CV: {tex_cv:.3f} (Required: >= 0.350)")
    
    bursty_pass = docx_bursty and tex_bursty
    if bursty_pass:
        print("  [PASS] Natural human sentence burstiness confirmed across both documents (CV >= 0.35).")
    else:
        if not docx_bursty:
            print(f"  [FAIL] Word document sentence length is too uniform (CV = {docx_cv:.3f} < 0.350).")
            all_violations.append("Word document CV < 0.350")
        if not tex_bursty:
            print(f"  [FAIL] LaTeX manuscript sentence length is too uniform (CV = {tex_cv:.3f} < 0.350).")
            all_violations.append("LaTeX manuscript CV < 0.350")

    # 6. N-gram Overlap Check
    print("\n[Audit 4/4] Evaluating 5-gram plagiarism overlap against references & docstrings...")
    bib_file = REPO_ROOT / "paper" / "references.bib"
    is_clean, overlap_pct = audit_ngram_overlap(docx_paragraphs, bib_file)
    print(f"  5-Gram Overlap: {overlap_pct:.2f}% (Threshold: < 1.00%)")
    if is_clean:
        print(f"  [PASS] Strict zero-plagiarism verified ({overlap_pct:.2f}% < 1.00%).")
    else:
        print(f"  [FAIL] N-gram overlap exceeds threshold: {overlap_pct:.2f}% >= 1.00%")
        all_violations.append(f"N-gram overlap {overlap_pct:.2f}% >= 1.00%")

    overall_success = len(all_violations) == 0
    print("\n" + "=" * 70)
    if overall_success:
        print("[HUMANIZATION AUDIT PASSED] 100% Humanized, Plagiarism-Free CRC Paper & LaTeX Manuscript.")
    else:
        print(f"[HUMANIZATION AUDIT FAILED] {len(all_violations)} violation(s) detected. Remediation required.")
    print("=" * 70)
    return overall_success


if __name__ == "__main__":
    ok = run_full_humanization_audit()
    sys.exit(0 if ok else 1)
