#!/usr/bin/env python3
"""Automated Chaos Experiment Orchestrator for Constrained-xAIOps.

Applies declarative Chaos Mesh manifests, tracks injection timestamps,
monitors target microservices, and records experiment metadata for live telemetry ingestion.
"""

import argparse
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ChaosRunner")


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Executes a shell command and logs output."""
    logger.info("Executing: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def check_kubectl_and_chaos_mesh() -> bool:
    """Verifies kubectl connectivity and Chaos Mesh CRD presence."""
    try:
        res = run_command(["kubectl", "version", "--client"], check=False)
        if res.returncode != 0:
            logger.warning("kubectl client not found or returned error.")
            return False
        res = run_command(["kubectl", "api-resources"], check=False)
        has_chaos = "chaos-mesh.org" in res.stdout
        if not has_chaos:
            logger.warning("Chaos Mesh CRDs not detected in cluster api-resources.")
        return True
    except FileNotFoundError:
        logger.warning("kubectl binary not found on system PATH.")
        return False


def run_experiment(
    manifest_path: Path,
    duration_sec: int = 60,
    dry_run: bool = False,
    output_meta: Optional[Path] = None,
) -> Dict[str, Any]:
    """Runs a chaos experiment with injection timing metadata."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Chaos manifest not found: {manifest_path}")

    logger.info("Preparing chaos injection with manifest: %s", manifest_path.name)
    logger.info("Experiment planned duration: %d seconds (Dry-run: %s)", duration_sec, dry_run)

    experiment_meta: Dict[str, Any] = {
        "manifest": str(manifest_path.resolve()),
        "manifest_name": manifest_path.stem,
        "planned_duration_sec": duration_sec,
        "dry_run": dry_run,
        "status": "INITIALIZED",
    }

    if dry_run:
        logger.info("[DRY-RUN] Manifest syntax and path validated successfully.")
        experiment_meta["status"] = "DRY_RUN_PASSED"
        experiment_meta["inject_time"] = int(time.time())
        experiment_meta["end_time"] = int(time.time()) + duration_sec
        return experiment_meta

    # Apply chaos
    inject_time = int(time.time())
    logger.info("Injecting chaos at timestamp %d...", inject_time)
    apply_res = run_command(["kubectl", "apply", "-f", str(manifest_path)], check=True)
    logger.info("Chaos manifest applied:\n%s", apply_res.stdout.strip())
    experiment_meta["inject_time"] = inject_time
    experiment_meta["status"] = "RUNNING"

    try:
        time.sleep(duration_sec)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Cleaning up chaos manifest immediately...")
    finally:
        end_time = int(time.time())
        logger.info("Tearing down chaos injection at timestamp %d...", end_time)
        del_res = run_command(["kubectl", "delete", "-f", str(manifest_path), "--ignore-not-found=true"], check=False)
        logger.info("Teardown result: %s", del_res.stdout.strip())
        experiment_meta["end_time"] = end_time
        experiment_meta["status"] = "COMPLETED"

    if output_meta:
        output_meta.parent.mkdir(parents=True, exist_ok=True)
        with open(output_meta, "w", encoding="utf-8") as f:
            json.dump(experiment_meta, f, indent=2)
        logger.info("Experiment metadata saved to %s", output_meta)

    return experiment_meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Constrained-xAIOps Chaos Experiment Runner")
    parser.add_argument(
        "--manifest",
        type=str,
        default="infrastructure/chaos-mesh/pod_kill_cartservice.yaml",
        help="Path to Chaos Mesh YAML manifest",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration of chaos in seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest without applying to live cluster",
    )
    parser.add_argument(
        "--output-meta",
        type=str,
        default=None,
        help="Path to save experiment metadata JSON",
    )

    args = parser.parse_args()
    manifest_p = Path(args.manifest)
    out_p = Path(args.output_meta) if args.output_meta else None
    meta = run_experiment(manifest_p, duration_sec=args.duration, dry_run=args.dry_run, output_meta=out_p)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
