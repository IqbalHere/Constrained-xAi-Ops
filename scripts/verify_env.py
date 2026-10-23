"""Environment and Hardware Verification Script for Constrained-xAIOps.

Audits Python version, hardware resources (RAM, CPU), and installed package versions.
Saves manifest to artifacts/logs/env_report.json.
"""

import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


CRITICAL_PACKAGES = [
    "numpy",
    "pandas",
    "pyarrow",
    "scipy",
    "sklearn",  # scikit-learn
    "shap",
    "pydantic",
    "yaml",  # pyyaml
    "fastapi",
    "uvicorn",
    "streamlit",
    "matplotlib",
    "seaborn",
    "psutil",
    "pytest",
    "requests",
]

PACKAGE_DIST_MAPPING = {
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}


def audit_environment() -> dict:
    """Collects system, hardware, and environment details."""
    # RAM and CPU
    if psutil:
        mem = psutil.virtual_memory()
        total_ram_gb = round(mem.total / (1024**3), 2)
        available_ram_gb = round(mem.available / (1024**3), 2)
        cpu_cores_logical = psutil.cpu_count(logical=True)
        cpu_cores_physical = psutil.cpu_count(logical=False)
    else:
        total_ram_gb = None
        available_ram_gb = None
        cpu_cores_logical = os.cpu_count()
        cpu_cores_physical = None

    # Packages
    installed_packages = {}
    for pkg in CRITICAL_PACKAGES:
        dist_name = PACKAGE_DIST_MAPPING.get(pkg, pkg)
        try:
            installed_packages[pkg] = importlib.metadata.version(dist_name)
        except importlib.metadata.PackageNotFoundError:
            try:
                mod = __import__(pkg)
                installed_packages[pkg] = getattr(mod, "__version__", "unknown")
            except ImportError:
                installed_packages[pkg] = "NOT_INSTALLED"

    report = {
        "status": "PASS",
        "python_version": sys.version,
        "python_version_tuple": list(sys.version_info[:3]),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "hardware": {
            "total_ram_gb": total_ram_gb,
            "available_ram_gb": available_ram_gb,
            "cpu_cores_logical": cpu_cores_logical,
            "cpu_cores_physical": cpu_cores_physical,
        },
        "packages": installed_packages,
    }
    return report


def main() -> None:
    print("=" * 60)
    print("Constrained-xAIOps: Auditing Environment & Hardware...")
    print("=" * 60)

    report = audit_environment()

    output_dir = Path("artifacts/logs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "env_report.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Python: {report['python_version'].split()[0]}")
    print(f"Platform: {report['platform']}")
    print(f"RAM: {report['hardware']['total_ram_gb']} GB total, {report['hardware']['available_ram_gb']} GB available")
    print(f"CPU Cores: {report['hardware']['cpu_cores_logical']} logical")
    print("\nPackage Versions:")
    for pkg, ver in report["packages"].items():
        print(f"  - {pkg}: {ver}")

    print(f"\nManifest successfully written to: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
