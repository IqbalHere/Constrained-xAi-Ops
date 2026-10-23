"""Download and verify the RCAEval RE1 benchmark datasets from Zenodo.

Suites:
1. RE1-OB (Online Boutique, 125 failure cases)
   URL: https://zenodo.org/records/14590730/files/RE1-OB.zip?download=1
   MD5: 47cce26ed24140e8974e68f9db2a5e9c
2. RE1-SS (Sock Shop, 125 failure cases)
   URL: https://zenodo.org/records/14590730/files/RE1-SS.zip?download=1
   MD5: d2b15cbd3bb3cf6ec5f3cc65f7fac225
3. RE1-TT (Train Ticket, 125 failure cases)
   URL: https://zenodo.org/records/14590730/files/RE1-TT.zip?download=1
   MD5: 48a26925ce47fd4bcfbedbae4f31475b

Target extraction: data/raw/rcaeval/{RE1-OB, RE1-SS, RE1-TT}/ (375 total cases)
"""

import argparse
import hashlib
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
import requests

SUITES: Dict[str, Dict[str, object]] = {
    "OB": {
        "name": "RE1-OB",
        "system": "OnlineBoutique",
        "url": "https://zenodo.org/records/14590730/files/RE1-OB.zip?download=1",
        "hf_url": "https://huggingface.co/datasets/phamquiluan/RCAEval/resolve/main/RE1-OB.zip",
        "expected_md5": "47cce26ed24140e8974e68f9db2a5e9c",
        "zip_path": Path("data/raw/RE1-OB.zip"),
        "extract_dir": Path("data/raw/rcaeval/RE1-OB"),
        "expected_cases": 125,
    },
    "SS": {
        "name": "RE1-SS",
        "system": "SockShop",
        "url": "https://zenodo.org/records/14590730/files/RE1-SS.zip?download=1",
        "hf_url": "https://huggingface.co/datasets/phamquiluan/RCAEval/resolve/main/RE1-SS.zip",
        "expected_md5": "d2b15cbd3bb3cf6ec5f3cc65f7fac225",
        "zip_path": Path("data/raw/RE1-SS.zip"),
        "extract_dir": Path("data/raw/rcaeval/RE1-SS"),
        "expected_cases": 125,
    },
    "TT": {
        "name": "RE1-TT",
        "system": "TrainTicket",
        "url": "https://zenodo.org/records/14590730/files/RE1-TT.zip?download=1",
        "hf_url": "https://huggingface.co/datasets/phamquiluan/RCAEval/resolve/main/RE1-TT.zip",
        "expected_md5": "48a26925ce47fd4bcfbedbae4f31475b",
        "zip_path": Path("data/raw/RE1-TT.zip"),
        "extract_dir": Path("data/raw/rcaeval/RE1-TT"),
        "expected_cases": 125,
    },
}

# Backward compatibility defaults
DEFAULT_ZIP_PATH = Path("data/raw/RE1-OB.zip")
DEFAULT_EXTRACT_DIR = Path("data/raw/rcaeval/RE1-OB")
EXPECTED_MD5 = "47cce26ed24140e8974e68f9db2a5e9c"
EXPECTED_CASES = 125
ZENODO_URL = "https://zenodo.org/records/14590730/files/RE1-OB.zip?download=1"


def compute_md5(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Computes the MD5 hex digest of a file in chunks."""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            md5.update(chunk)
    return md5.hexdigest()


def download_file(
    url: str,
    dest_path: Path,
    fallback_url: Optional[str] = None,
    max_retries: int = 5,
    timeout: int = 120,
) -> None:
    """Downloads a file in streaming chunks with retries and fallback mirror support."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")

    urls_to_try = [url]
    if fallback_url:
        urls_to_try.append(fallback_url)

    for current_url in urls_to_try:
        source_name = "Zenodo" if "zenodo" in current_url else "Hugging Face"
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[Download] Connecting to {source_name} ({current_url}) (Attempt {attempt}/{max_retries})...")
                headers = {"User-Agent": "Constrained-xAIOps-DataFetcher/1.0"}
                with requests.get(current_url, stream=True, timeout=timeout, headers=headers) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    chunk_size = 1024 * 512  # 512 KB

                    with open(temp_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    pct = (downloaded / total_size) * 100
                                    mb = downloaded / (1024 * 1024)
                                    total_mb = total_size / (1024 * 1024)
                                    sys.stdout.write(f"\r[Download] {mb:.1f}/{total_mb:.1f} MB ({pct:.1f}%)")
                                    sys.stdout.flush()
                                else:
                                    mb = downloaded / (1024 * 1024)
                                    sys.stdout.write(f"\r[Download] {mb:.1f} MB downloaded")
                                    sys.stdout.flush()
                    print()

                # Atomically move temp to dest
                if temp_path.exists():
                    if dest_path.exists():
                        dest_path.unlink()
                    temp_path.rename(dest_path)
                print(f"[Download] Download finished: {dest_path}")
                return
            except (requests.RequestException, OSError) as e:
                print(f"\n[Warning] Download failed on attempt {attempt}: {e}")
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
                if attempt < max_retries:
                    time.sleep(3 * attempt)
                else:
                    print(f"[Warning] Exhausted attempts on {source_name}.")

    raise RuntimeError(f"Failed to download from primary and fallback URLs for {dest_path.name}")


def extract_dataset(zip_path: Path, target_dir: Path, suite_name: str, expected_cases: int = 125) -> List[Path]:
    """Extracts zip archive and guarantees all case directories exist in target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Extract] Inspecting archive {zip_path}...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        prefix = f"{suite_name}/"
        has_prefix = any(m.startswith(prefix) for m in members)

        print(f"[Extract] Found {len(members)} entries. Extracting into {target_dir}...")
        if has_prefix:
            # Extract to parent so 'RE1-XX/...' populates target_dir
            parent_dir = target_dir.parent
            zf.extractall(parent_dir)
        else:
            zf.extractall(target_dir)

    # Discover case subdirectories (either nested fault_dir/case_num or flat)
    leaf_cases = [
        d for d in target_dir.glob("*/*")
        if d.is_dir() and not d.name.startswith((".", "_")) and (
            (d / "inject_time.txt").exists() or (d / "data.csv").exists() or (d / "metrics.csv").exists()
        )
    ]
    if len(leaf_cases) == expected_cases:
        case_dirs = leaf_cases
    else:
        flat_cases = [
            d for d in target_dir.iterdir()
            if d.is_dir() and not d.name.startswith((".", "_")) and (
                (d / "inject_time.txt").exists() or (d / "data.csv").exists() or (d / "metrics.csv").exists()
            )
        ]
        case_dirs = flat_cases if len(flat_cases) == expected_cases else (leaf_cases or flat_cases)

    print(f"[Extract] Verified {len(case_dirs)} case directories in {target_dir}")
    return case_dirs


def ensure_suite(suite_key: str, force_download: bool = False) -> Path:
    """Ensures a specific RCAEval suite (OB, SS, TT) is downloaded and extracted."""
    cfg = SUITES[suite_key]
    suite_name = str(cfg["name"])
    zip_path = Path(str(cfg["zip_path"]))
    target_dir = Path(str(cfg["extract_dir"]))
    expected_md5 = str(cfg["expected_md5"])
    expected_cases = int(cfg["expected_cases"])
    url = str(cfg["url"])
    hf_url = str(cfg["hf_url"])

    print("\n" + "=" * 60)
    print(f"Constrained-xAIOps: RCAEval {suite_name} Dataset Verification")
    print("=" * 60)

    # 1. Check if extraction already done and complete
    if target_dir.exists() and not force_download:
        existing_cases = [
            d for d in target_dir.glob("*/*")
            if d.is_dir() and ((d / "inject_time.txt").exists() or (d / "data.csv").exists() or (d / "metrics.csv").exists())
        ]
        if not existing_cases:
            existing_cases = [
                d for d in target_dir.iterdir()
                if d.is_dir() and ((d / "inject_time.txt").exists() or (d / "data.csv").exists() or (d / "metrics.csv").exists())
            ]
        if len(existing_cases) == expected_cases:
            print(f"[Verification] Found existing extracted dataset with all {expected_cases} cases in {target_dir}")
            return target_dir

    # 2. Check local zip file
    if zip_path.exists() and not force_download:
        print(f"[Checksum] Verifying MD5 of local zip: {zip_path}")
        local_md5 = compute_md5(zip_path)
        if local_md5 == expected_md5:
            print(f"[Checksum] MD5 matched: {local_md5}")
        else:
            print(f"[Checksum] MD5 mismatch! Expected {expected_md5}, got {local_md5}. Re-downloading...")
            download_file(url, zip_path, fallback_url=hf_url)
            new_md5 = compute_md5(zip_path)
            if new_md5 != expected_md5:
                raise ValueError(f"Downloaded file MD5 {new_md5} does not match {expected_md5}")
    else:
        print(f"[Download] Downloading {zip_path.name} from Zenodo / Hugging Face...")
        download_file(url, zip_path, fallback_url=hf_url)
        downloaded_md5 = compute_md5(zip_path)
        print(f"[Checksum] Verifying MD5: {downloaded_md5}")
        if downloaded_md5 != expected_md5:
            raise ValueError(f"Downloaded file MD5 {downloaded_md5} does not match expected {expected_md5}")

    # 3. Extract
    case_dirs = extract_dataset(zip_path, target_dir, suite_name=suite_name, expected_cases=expected_cases)
    if len(case_dirs) != expected_cases:
        print(f"[Warning] Found {len(case_dirs)} cases, expected {expected_cases}.")
    else:
        print(f"[Success] All {expected_cases} cases of {suite_name} extracted and ready.")

    return target_dir


def ensure_rcaeval_dataset(
    zip_path: Path = DEFAULT_ZIP_PATH,
    target_dir: Path = DEFAULT_EXTRACT_DIR,
    force_download: bool = False,
) -> Path:
    """Backward compatibility wrapper for RE1-OB."""
    return ensure_suite("OB", force_download=force_download)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and verify RCAEval benchmark datasets.")
    parser.add_argument(
        "--suite",
        type=str,
        default="ALL",
        choices=["ALL", "all", "OB", "ob", "SS", "ss", "TT", "tt"],
        help="Benchmark suite to download: OB, SS, TT, or ALL (default: ALL).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if files already exist.",
    )
    args = parser.parse_args()

    suite_arg = args.suite.upper()
    if suite_arg == "ALL":
        for k in ["OB", "SS", "TT"]:
            ensure_suite(k, force_download=args.force)
    else:
        ensure_suite(suite_arg, force_download=args.force)


if __name__ == "__main__":
    main()
