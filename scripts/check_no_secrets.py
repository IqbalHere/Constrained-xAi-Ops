"""Secret scanner script to prevent accidental leakage of keys, tokens, and .env files.
"""

import os
import re
import sys
from pathlib import Path

# Patterns indicating potential secrets
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"""(?i)aws_secret_access_key\s*=\s*['"][A-Za-z0-9/\+=]{40}['"]"""), "AWS Secret Access Key"),
    (re.compile(r"ghp_[0-9a-zA-Z]{36}"), "GitHub Personal Access Token"),
    (re.compile(r"glpat-[0-9a-zA-Z\-_]{20}"), "GitLab Personal Access Token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "Private Key"),
]

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "data",
}


def scan_workspace(root_dir: str = ".") -> list[dict]:
    findings = []
    root_path = Path(root_dir).resolve()

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter directories in-place
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]

        for fname in filenames:
            file_path = Path(dirpath) / fname
            rel_path = file_path.relative_to(root_path)

            # Check for .env files
            if fname == ".env" or fname.startswith(".env."):
                findings.append({
                    "file": str(rel_path),
                    "line": 0,
                    "description": "Committed or staged .env file detected",
                })
                continue

            # Skip binary and very large files
            if fname.endswith((".zip", ".tar", ".gz", ".parquet", ".png", ".jpg", ".pyc")):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_idx, line in enumerate(content.splitlines(), start=1):
                    for pattern, desc in SECRET_PATTERNS:
                        if pattern.search(line):
                            findings.append({
                                "file": str(rel_path),
                                "line": line_idx,
                                "description": f"Potential secret matched: {desc}",
                            })
            except Exception as e:
                # Unable to read file, skip
                continue

    return findings


def main() -> None:
    print("Scanning workspace for exposed secrets and .env files...")
    findings = scan_workspace(".")
    if findings:
        print(f"\n[SECURITY VIOLATION] Found {len(findings)} potential security issues:")
        for item in findings:
            print(f"  - {item['file']}:{item['line']} -> {item['description']}")
        sys.exit(1)
    else:
        print("[PASS] No secrets, private tokens, or .env files found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
