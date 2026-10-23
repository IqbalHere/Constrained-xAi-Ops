"""Loader and schema registry exporter for RCAEval RE1 benchmark datasets.

Discovers and structures failure cases across all three benchmark suites:
1. RE1-OB (Online Boutique, 125 cases)
2. RE1-SS (Sock Shop, 125 cases)
3. RE1-TT (Train Ticket, 125 cases)
Total: 375 real cloud failure cases.

Parses timestamps, metrics, inject times, and ground-truth annotations,
converting them into validated Pydantic v2 TelemetryCase contracts.
Exports schema registry to datasets/schema_registry.json.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence
import pandas as pd

from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    KNOWN_SOCK_SHOP_SERVICES,
    TelemetryAligner,
    extract_services_from_metrics,
    group_metrics_by_service,
)
from src.schemas import TelemetryCase


class RCAEvalLoader:
    """Discovers, parses, and structures RCAEval benchmark cases."""

    def __init__(
        self,
        raw_dir: str = "data/raw/rcaeval/RE1-OB",
        system: Optional[str] = None,
    ):
        self.raw_dir = Path(raw_dir)
        self.aligner = TelemetryAligner()

        if system is not None:
            self.system = system
        elif "SS" in self.raw_dir.name or "sock" in str(self.raw_dir).lower():
            self.system = "SockShop"
        elif "TT" in self.raw_dir.name or "train" in str(self.raw_dir).lower():
            self.system = "TrainTicket"
        else:
            self.system = "OnlineBoutique"

    def discover_case_directories(self) -> list[Path]:
        """Discovers and sorts all case directories in the raw dataset."""
        if not self.raw_dir.exists():
            return []

        # Check nested structure: RE1-XX/<fault_dir>/<case_num>
        nested_cases = [
            d for d in self.raw_dir.glob("*/*")
            if d.is_dir() and not d.name.startswith((".", "_")) and (
                (d / "inject_time.txt").exists()
                or (d / "data.csv").exists()
                or (d / "metrics.csv").exists()
            )
        ]
        if len(nested_cases) > 0:
            return sorted(nested_cases, key=lambda p: (p.parent.name, p.name))

        # Check flat structure: RE1-XX/<case_dir>
        flat_cases = [
            d for d in self.raw_dir.iterdir()
            if d.is_dir() and not d.name.startswith((".", "_")) and (
                (d / "inject_time.txt").exists()
                or (d / "data.csv").exists()
                or (d / "metrics.csv").exists()
            )
        ]
        return sorted(flat_cases, key=lambda p: p.name)

    def _read_metrics_file(self, case_dir: Path) -> pd.DataFrame:
        """Reads metrics from data.csv, metrics.csv, or metrics.json format."""
        data_csv_path = case_dir / "data.csv"
        metrics_csv_path = case_dir / "metrics.csv"
        json_path = case_dir / "metrics.json"

        if data_csv_path.exists():
            return pd.read_csv(data_csv_path)
        elif metrics_csv_path.exists():
            return pd.read_csv(metrics_csv_path)
        elif json_path.exists():
            try:
                return pd.read_json(json_path)
            except Exception:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return pd.DataFrame(data)
        else:
            raise FileNotFoundError(f"No data.csv, metrics.csv or metrics.json found in {case_dir}")

    def _read_inject_time(self, case_dir: Path, df: Optional[pd.DataFrame] = None) -> int:
        """Reads inject_time from file or infers from annotations."""
        for candidate in ["inject_time.txt", "injection_time.txt", "inject.txt"]:
            file_path = case_dir / candidate
            if file_path.exists():
                val = file_path.read_text().strip()
                try:
                    return int(float(val))
                except ValueError:
                    pass

        # Check JSON metadata files in case dir
        for candidate_json in ["injection_info.json", "metadata.json", "anomaly.json"]:
            json_file = case_dir / candidate_json
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    for key in ["inject_time", "injection_time", "timestamp"]:
                        if key in meta:
                            return int(float(meta[key]))
                except Exception:
                    pass

        # Fallback: midpoint of timestamps if dataframe available
        if df is not None:
            time_cols = [c for c in df.columns if c.lower() in ("time", "timestamp")]
            if time_cols:
                times = pd.to_numeric(df[time_cols[0]], errors="coerce").dropna().values
                if len(times) > 0:
                    return int(times[len(times) // 2])
        return 0

    def _read_ground_truth(self, case_dir: Path) -> tuple[str, str]:
        """Extracts ground truth (root_cause_service, root_cause_indicator)."""
        parent_name = case_dir.parent.name
        # 1. Standard RCAEval fault dir naming: e.g. 'adservice_cpu', 'carts_delay', 'ts-order-service_loss'
        if "_" in parent_name:
            svc_candidate, ind_candidate = parent_name.rsplit("_", 1)
            known_faults = {"cpu", "mem", "delay", "disk", "loss", "synthetic_injection"}
            known_all = set(KNOWN_ONLINE_BOUTIQUE_SERVICES) | set(KNOWN_SOCK_SHOP_SERVICES)
            if ind_candidate in known_faults:
                return svc_candidate, ind_candidate
            if svc_candidate in known_all or svc_candidate.startswith("ts-"):
                return svc_candidate, ind_candidate

        # 2. Check direct text files
        for candidate in [
            "groundtruth.txt", "root_cause.txt", "root_cause_service.txt",
            "injection_info.txt", "fault_service.txt"
        ]:
            file_path = case_dir / candidate
            if file_path.exists():
                text = file_path.read_text().strip()
                tokens = text.split()
                if len(tokens) >= 2:
                    return tokens[0], tokens[1]
                elif len(tokens) == 1:
                    return tokens[0], "unknown"

        # 3. Check JSON metadata in case directory
        for candidate_json in ["injection_info.json", "metadata.json", "root_cause.json", "anomaly.json"]:
            json_file = case_dir / candidate_json
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    service = meta.get("service") or meta.get("root_cause_service") or meta.get("cmdb_id")
                    indicator = meta.get("indicator") or meta.get("metric") or meta.get("type", "unknown")
                    if service:
                        return str(service), str(indicator)
                except Exception:
                    pass

        # 4. Infer service from case folder name
        name_lower = case_dir.name.lower()
        for s in KNOWN_ONLINE_BOUTIQUE_SERVICES + KNOWN_SOCK_SHOP_SERVICES:
            if s.lower() in name_lower:
                return s, "synthetic_injection"

        return "unknown", "unknown"

    def load_case(self, case_dir: Path) -> TelemetryCase:
        """Loads and structures a single RCAEval failure case."""
        raw_df = self._read_metrics_file(case_dir)
        inject_time = self._read_inject_time(case_dir, raw_df)
        rc_service, rc_indicator = self._read_ground_truth(case_dir)

        # Consistent human-readable case ID
        if case_dir.parent.name != self.raw_dir.name:
            if self.raw_dir.name == "RE1-OB":
                case_id = f"{case_dir.parent.name}-{case_dir.name}"
            else:
                case_id = f"{self.raw_dir.name}-{case_dir.parent.name}-{case_dir.name}"
        else:
            case_id = case_dir.name

        return self.aligner.align_and_structure(
            raw_df=raw_df,
            case_id=case_id,
            system=self.system,
            inject_time=inject_time,
            root_cause_service=rc_service,
            root_cause_indicator=rc_indicator,
            data_source_tag="PUBLIC_BENCHMARK",
        )

    def load_all_cases(self) -> list[TelemetryCase]:
        """Loads all discovered cases in the benchmark directory."""
        case_dirs = self.discover_case_directories()
        cases = []
        for d in case_dirs:
            cases.append(self.load_case(d))
        return cases

    @classmethod
    def load_all_suites(
        cls,
        root_raw_dir: str = "data/raw/rcaeval",
    ) -> Dict[str, list[TelemetryCase]]:
        """Loads all 3 benchmark suites (RE1-OB, RE1-SS, RE1-TT)."""
        root_path = Path(root_raw_dir)
        suite_map = {
            "OnlineBoutique": root_path / "RE1-OB",
            "SockShop": root_path / "RE1-SS",
            "TrainTicket": root_path / "RE1-TT",
        }
        loaded: Dict[str, list[TelemetryCase]] = {}
        for sys_name, s_dir in suite_map.items():
            if s_dir.exists():
                loader = cls(raw_dir=str(s_dir), system=sys_name)
                loaded[sys_name] = loader.load_all_cases()
            else:
                loaded[sys_name] = []
        return loaded

    @classmethod
    def load_all_375_cases(
        cls,
        root_raw_dir: str = "data/raw/rcaeval",
    ) -> list[TelemetryCase]:
        """Loads all 375 cases across all 3 benchmark suites."""
        suites = cls.load_all_suites(root_raw_dir=root_raw_dir)
        all_cases = []
        for sys_name, cases in suites.items():
            all_cases.extend(cases)
        return all_cases

    def generate_schema_registry(
        self,
        cases: list[TelemetryCase],
        output_file: str = "datasets/schema_registry.json",
    ) -> dict:
        """Computes schema registry across provided cases and exports documentation."""
        fault_distribution: dict[str, int] = {}
        all_services: set[str] = set()
        metric_counts_per_service: dict[str, set[str]] = {}
        systems_seen: set[str] = set()
        system_details: dict[str, dict] = {}

        for case in cases:
            systems_seen.add(case.system)
            fault_type = case.root_cause_indicator
            fault_distribution[fault_type] = fault_distribution.get(fault_type, 0) + 1

            services = extract_services_from_metrics(case.metrics_data)
            all_services.update(services)

            grouped = group_metrics_by_service(case.metrics_data)
            for s, s_metrics in grouped.items():
                if s not in metric_counts_per_service:
                    metric_counts_per_service[s] = set()
                metric_counts_per_service[s].update(s_metrics.keys())

        # Build per-system breakdown
        for sys_name in sorted(systems_seen):
            sys_cases = [c for c in cases if c.system == sys_name]
            sys_faults: dict[str, int] = {}
            sys_services: set[str] = set()
            sys_metrics: dict[str, set[str]] = {}
            for c in sys_cases:
                sys_faults[c.root_cause_indicator] = sys_faults.get(c.root_cause_indicator, 0) + 1
                s_list = extract_services_from_metrics(c.metrics_data)
                sys_services.update(s_list)
                grp = group_metrics_by_service(c.metrics_data)
                for s, sm in grp.items():
                    if s not in sys_metrics:
                        sys_metrics[s] = set()
                    sys_metrics[s].update(sm.keys())

            system_details[sys_name] = {
                "total_cases": len(sys_cases),
                "num_services": len(sys_services),
                "services": sorted(list(sys_services)),
                "fault_distribution": sys_faults,
                "metric_counts_per_service": {s: len(sys_metrics.get(s, set())) for s in sorted(sys_services)},
            }

        registry = {
            "dataset_name": "RCAEval RE1 (Multi-System Benchmark)",
            "systems_included": sorted(list(systems_seen)),
            "total_cases": len(cases),
            "total_services": len(all_services),
            "fault_distribution": fault_distribution,
            "services": sorted(list(all_services)),
            "metric_counts_per_service": {
                s: len(metric_counts_per_service.get(s, set())) for s in sorted(all_services)
            },
            "sample_metrics": {
                s: sorted(list(metric_counts_per_service.get(s, set())))[:5]
                for s in sorted(all_services)
            },
            "systems": system_details,
        }

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)

        print(f"[Schema Registry] Exported multi-system registry ({len(cases)} cases) to: {out_path}")
        return registry
