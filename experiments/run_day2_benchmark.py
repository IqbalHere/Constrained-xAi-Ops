"""Day 2 Verification Benchmark: Telemetry Trust Score & Missingness Degradation.

Evaluates how the 5-Dimensional Telemetry Trust Score (C, L, S, V, Q) and Vanilla BARO
behave across MCAR, MAR, and Incident-Driven MNAR at rates [0.0, 0.1, 0.2, 0.4, 0.6, 0.8]
across all 125 failure cases of RCAEval RE1-OB (Online Boutique).

Enforces:
  1. NO FABRICATED NUMBERS: All outputs computed strictly from real cases.
  2. ZERO DATA LEAKAGE: Pre-fault baselines restricted to t < inject_time - 10s.
  3. NO RAW MUTATION: TelemetryCase instances are preserved without in-place mutation.
"""

import json
import os
import sys
import time
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.ingestion.rcaeval_loader import RCAEvalLoader
from src.missingness.generator import MissingnessGenerator
from src.preprocessing.imputer import CausalImputer
from src.quality.trust_score import TelemetryTrustEvaluator
from src.rca.baselines import VanillaBARO, evaluate_baseline
from src.schemas import TelemetryCase


def run_benchmark(
    dataset_dir: str = "data/raw/rcaeval/RE1-OB",
    output_path: str = "artifacts/metrics/day2_trust_and_missingness_re1_ob.json",
    seed: int = 42,
) -> dict:
    max_workers = min(16, max(4, os.cpu_count() or 8))
    print("=" * 70)
    print("Constrained-xAIOps: Day 2 Benchmark (Trust Score & Missingness Engine)")
    print(f"Hardware Concurrency: Utilizing {max_workers} parallel threads across CPU cores.")
    print("=" * 70)

    # 1. Load all 125 cases
    loader = RCAEvalLoader(raw_dir=dataset_dir)
    cases = loader.load_all_cases()
    n_cases = len(cases)
    print(f"[Loader] Preloaded {n_cases} clean failure cases into memory.")

    if n_cases == 0:
        raise FileNotFoundError(f"No cases found in {dataset_dir}!")

    # 2. Setup engines
    gen = MissingnessGenerator(seed=seed)
    evaluator = TelemetryTrustEvaluator()
    imputer_ffill = CausalImputer(method="forward_fill")
    imputer_zfill = CausalImputer(method="zero_fill")
    baro = VanillaBARO(pre_fault_buffer_sec=10, post_fault_window_sec=300, aggregation="max")

    mechanisms = ["MCAR", "MAR", "MNAR"]
    rates = [0.0, 0.1, 0.2, 0.4, 0.6, 0.8]

    benchmark_results: Dict[str, Dict[str, dict]] = {m: {} for m in mechanisms}
    comparison_imputer_results: Dict[str, dict] = {}

    total_start = time.perf_counter()

    for mechanism in mechanisms:
        print(f"\nEvaluating Mechanism: {mechanism}")
        print("-" * 50)

        for p_miss in rates:
            step_start = time.perf_counter()

            # Containers for this (mechanism, p_miss) configuration
            t_sys_list = []
            c_list = []
            l_list = []
            s_list = []
            v_list = []
            q_list = []
            t_rc_list = []
            imputed_cases = []

            def _process_case(args):
                case_idx, case = args
                case_seed = seed + case_idx * 17
                corrupted_dict, mask = gen.apply_corruption(
                    case=case,
                    mechanism=mechanism,
                    p_miss=p_miss,
                    seed=case_seed,
                )
                trust_eval = evaluator.evaluate_case(case, mask=mask)
                corrupted_df = pd.DataFrame(corrupted_dict)
                inject_idx = next(
                    (i for i, t in enumerate(case.timestamps) if t >= case.inject_time),
                    len(case.timestamps) // 2,
                )
                imputed_df = imputer_ffill.impute(
                    corrupted_df, mask, inject_time_idx=inject_idx
                )
                imputed_case = TelemetryCase(
                    case_id=case.case_id,
                    system=case.system,
                    metrics_data={col: imputed_df[col].tolist() for col in imputed_df.columns},
                    timestamps=case.timestamps,
                    inject_time=case.inject_time,
                    root_cause_service=case.root_cause_service,
                    root_cause_indicator=case.root_cause_indicator,
                    data_source_tag=case.data_source_tag,
                )
                return trust_eval, imputed_case

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                processed_results = list(executor.map(_process_case, enumerate(cases)))

            for trust_eval, imputed_case in processed_results:
                t_sys_list.append(trust_eval.dimensions["T_sys"])
                c_list.append(trust_eval.dimensions["C"])
                l_list.append(trust_eval.dimensions["L"])
                s_list.append(trust_eval.dimensions["S"])
                v_list.append(trust_eval.dimensions["V"])
                q_list.append(trust_eval.dimensions["Q"])

                rc_svc = imputed_case.root_cause_service
                t_rc = trust_eval.service_scores.get(rc_svc, 1.0)
                t_rc_list.append(t_rc)
                imputed_cases.append(imputed_case)

            # Evaluate BARO across all 125 imputed cases
            baro_eval = evaluate_baseline(baro, imputed_cases, num_total_services=10)

            # Spearman correlation between root cause trust score and reciprocal rank
            rc_ranks = [res["reciprocal_rank"] for res in baro_eval["case_results"]]
            if np.std(t_rc_list) > 1e-6 and np.std(rc_ranks) > 1e-6:
                spearman_stat, spearman_p = spearmanr(t_rc_list, rc_ranks)
                spearman_stat = float(spearman_stat)
                spearman_p = float(spearman_p)
            else:
                spearman_stat = 0.0
                spearman_p = 1.0

            elapsed_step = time.perf_counter() - step_start

            result_entry = {
                "mechanism": mechanism,
                "p_miss": p_miss,
                "n_cases": n_cases,
                "trust_metrics": {
                    "mean_T_sys": round(float(np.mean(t_sys_list)), 4),
                    "mean_T_root_cause": round(float(np.mean(t_rc_list)), 4),
                    "mean_C": round(float(np.mean(c_list)), 4),
                    "mean_L": round(float(np.mean(l_list)), 4),
                    "mean_S": round(float(np.mean(s_list)), 4),
                    "mean_V": round(float(np.mean(v_list)), 4),
                    "mean_Q": round(float(np.mean(q_list)), 4),
                },
                "baro_metrics": {
                    "AC@1": baro_eval["AC@1"],
                    "AC@3": baro_eval["AC@3"],
                    "AC@5": baro_eval["AC@5"],
                    "Avg@5": baro_eval["Avg@5"],
                    "MRR": baro_eval["MRR"],
                    "Lift@5": baro_eval["Lift@5"],
                    "mean_runtime_ms": baro_eval["mean_runtime_ms"],
                },
                "correlation": {
                    "spearman_trust_vs_mrr": round(spearman_stat, 4),
                    "p_value": round(spearman_p, 4),
                },
                "step_runtime_sec": round(elapsed_step, 2),
            }

            benchmark_results[mechanism][str(p_miss)] = result_entry

            print(
                f"  Rate: {int(p_miss * 100):2d}% | "
                f"T_sys: {result_entry['trust_metrics']['mean_T_sys']:.4f} | "
                f"T_rc: {result_entry['trust_metrics']['mean_T_root_cause']:.4f} | "
                f"BARO AC@1: {result_entry['baro_metrics']['AC@1'] * 100:5.1f}% | "
                f"Avg@5: {result_entry['baro_metrics']['Avg@5'] * 100:5.1f}% | "
                f"MRR: {result_entry['baro_metrics']['MRR']:.4f} | "
                f"Spearman r: {result_entry['correlation']['spearman_trust_vs_mrr']:+.3f}",
                flush=True,
            )

    # 3. Imputer comparison on MNAR 40% (forward_fill vs zero_fill)
    print("\nEvaluating Imputer Comparison on MNAR 40% (forward_fill vs zero_fill)...", flush=True)
    def _process_zfill(args):
        case_idx, case = args
        case_seed = seed + case_idx * 17
        corrupted_dict, mask = gen.apply_corruption(case, mechanism="MNAR", p_miss=0.4, seed=case_seed)
        corrupted_df = pd.DataFrame(corrupted_dict)
        zfill_df = imputer_zfill.impute(corrupted_df, mask)
        return TelemetryCase(
            case_id=case.case_id,
            system=case.system,
            metrics_data={col: zfill_df[col].tolist() for col in zfill_df.columns},
            timestamps=case.timestamps,
            inject_time=case.inject_time,
            root_cause_service=case.root_cause_service,
            root_cause_indicator=case.root_cause_indicator,
            data_source_tag=case.data_source_tag,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        zfill_cases = list(executor.map(_process_zfill, enumerate(cases)))

    zfill_eval = evaluate_baseline(baro, zfill_cases, num_total_services=10)
    comparison_imputer_results = {
        "MNAR_40_forward_fill": benchmark_results["MNAR"]["0.4"]["baro_metrics"],
        "MNAR_40_zero_fill": {
            "AC@1": zfill_eval["AC@1"],
            "AC@3": zfill_eval["AC@3"],
            "AC@5": zfill_eval["AC@5"],
            "Avg@5": zfill_eval["Avg@5"],
            "MRR": zfill_eval["MRR"],
            "Lift@5": zfill_eval["Lift@5"],
        },
    }
    print(f"  forward_fill AC@1: {comparison_imputer_results['MNAR_40_forward_fill']['AC@1']*100:.1f}%, MRR: {comparison_imputer_results['MNAR_40_forward_fill']['MRR']:.4f}")
    print(f"  zero_fill    AC@1: {comparison_imputer_results['MNAR_40_zero_fill']['AC@1']*100:.1f}%, MRR: {comparison_imputer_results['MNAR_40_zero_fill']['MRR']:.4f}")

    total_runtime = time.perf_counter() - total_start

    output_manifest = {
        "dataset": "RE1-OB",
        "system": "OnlineBoutique",
        "total_cases": n_cases,
        "seed": seed,
        "total_benchmark_runtime_sec": round(total_runtime, 2),
        "results_by_mechanism": benchmark_results,
        "imputer_comparison": comparison_imputer_results,
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_manifest, f, indent=2)

    print(f"\n[Artifacts] Day 2 benchmark results saved to: {out_file}")
    print(f"[Done] Total execution completed in {total_runtime:.1f}s.")
    print("=" * 70)
    return output_manifest


if __name__ == "__main__":
    run_benchmark()
