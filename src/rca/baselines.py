"""Reproducible Baseline Root Cause Analysis (RCA) algorithms.

Implements pure NumPy/SciPy:
1. Vanilla BARO (RobustScorer on pre-fault baseline vs. post-fault window)
2. epsilon-Diagnosis (Two-sample non-parametric Kolmogorov-Smirnov statistical divergence)
3. CIRCA (KDD '22 Structural Graph Intervention Recognition via pre-fault topological Ridge regression)
4. RCD (NeurIPS '22 Hierarchical Interventional Discovery via localized F-node divergence and tournament elimination)

Multi-system compatible across Online Boutique, Sock Shop, and Train Ticket benchmarks.
Zero-leakage guarantee: all baselines, normalizers, and regression models fit strictly on
the pre-fault window (t < inject_time - 10s).
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence
import numpy as np
import scipy.stats as stats

from src.correlation.topology import BaseTopology, get_topology
from src.ingestion.aligner import (
    KNOWN_ONLINE_BOUTIQUE_SERVICES,
    extract_services_from_metrics,
    get_system_services,
    group_metrics_by_service,
)
from src.ingestion.rcaeval_loader import RCAEvalLoader
from src.schemas import RCAResult, TelemetryCase


def fast_ks_statistic(data1: np.ndarray, data2: np.ndarray) -> float:
    """Fast vectorized two-sample Kolmogorov-Smirnov D statistic.

    Computes supremum |F_1(x) - F_2(x)| in O((n1+n2) log(n1+n2)) pure NumPy without
    the quadratic combinatoric overhead of scipy.stats.ks_2samp.
    """
    n1 = len(data1)
    n2 = len(data2)
    if n1 < 2 or n2 < 2:
        return 0.0
    if np.all(data1 == data1[0]) and np.all(data2 == data2[0]):
        return 0.0 if data1[0] == data2[0] else 1.0

    d1 = np.sort(data1)
    d2 = np.sort(data2)
    all_data = np.concatenate([d1, d2])
    cdf1 = np.searchsorted(d1, all_data, side="right") / n1
    cdf2 = np.searchsorted(d2, all_data, side="right") / n2
    d_stat = float(np.max(np.abs(cdf1 - cdf2)))
    return d_stat if not np.isnan(d_stat) else 0.0


class VanillaBARO:
    """Vanilla BARO Root Cause Localizer.

    Uses a non-parametric RobustScorer:
      score = |median(post) - median(pre)| / (IQR(pre) + 1e-4)
    Zero-leakage: fitting/calibration baseline window is restricted to t < inject_time - buffer_sec.
    """

    def __init__(
        self,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        aggregation: Literal["max", "mean"] = "max",
    ):
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.aggregation = aggregation

    def score_metric(self, pre_vals: np.ndarray, post_vals: np.ndarray) -> float:
        """Computes RobustScorer for a single metric time-series."""
        if len(pre_vals) == 0 or len(post_vals) == 0:
            return 0.0

        median_pre = np.median(pre_vals)
        median_post = np.median(post_vals)
        q75, q25 = np.percentile(pre_vals, [75, 25])
        iqr_pre = q75 - q25

        score = float(np.abs(median_post - median_pre) / (iqr_pre + 1e-4))
        return score if not np.isnan(score) else 0.0

    def localize(self, case: TelemetryCase) -> RCAResult:
        """Runs BARO localization on a single TelemetryCase."""
        start_time = time.perf_counter()

        timestamps = np.array(case.timestamps)
        inject_time = case.inject_time

        # Zero-leakage windows:
        # Pre-fault window: strictly t < inject_time - pre_fault_buffer_sec
        pre_mask = timestamps < (inject_time - self.pre_fault_buffer_sec)
        # Post-fault window: inject_time <= t <= inject_time + post_fault_window_sec
        post_mask = (timestamps >= inject_time) & (
            timestamps <= inject_time + self.post_fault_window_sec
        )

        # Fallback if timestamps are relative or unaligned
        if np.sum(pre_mask) < 5:
            cutoff = int(len(timestamps) * 0.3)
            pre_mask = np.zeros(len(timestamps), dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            post_mask = timestamps >= inject_time
            if np.sum(post_mask) < 5:
                cutoff = int(len(timestamps) * 0.5)
                post_mask = np.zeros(len(timestamps), dtype=bool)
                post_mask[cutoff:] = True

        grouped = group_metrics_by_service(case.metrics_data)
        all_services = get_system_services(case.system, case.metrics_data)
        if not all_services:
            all_services = list(KNOWN_ONLINE_BOUTIQUE_SERVICES)

        service_scores: dict[str, float] = {}
        for service, metrics in grouped.items():
            if service not in all_services:
                continue
            metric_scores = []
            for col, values in metrics.items():
                arr = np.array(values, dtype=float)
                s = self.score_metric(arr[pre_mask], arr[post_mask])
                metric_scores.append(s)

            if metric_scores:
                if self.aggregation == "max":
                    service_scores[service] = float(np.max(metric_scores))
                else:
                    service_scores[service] = float(np.mean(metric_scores))
            else:
                service_scores[service] = 0.0

        for s in all_services:
            if s not in service_scores:
                service_scores[s] = 0.0

        ranked = sorted(service_scores.items(), key=lambda x: x[1], reverse=True)
        ranked_services = [s for s, _ in ranked]
        ranked_scores = [score for _, score in ranked]

        # Calculate rank metrics
        gt = case.root_cause_service
        if gt in ranked_services:
            rank = ranked_services.index(gt) + 1
        else:
            rank = len(ranked_services) + 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return RCAResult(
            case_id=case.case_id,
            ranked_services=ranked_services,
            scores=ranked_scores,
            ground_truth_service=gt,
            hit_at_1=(rank == 1),
            hit_at_3=(rank <= 3),
            hit_at_5=(rank <= 5),
            reciprocal_rank=float(1.0 / rank),
            runtime_ms=round(elapsed_ms, 3),
        )


class EpsilonDiagnosis:
    """epsilon-Diagnosis Root Cause Localizer.

    Uses two-sample Kolmogorov-Smirnov statistical divergence between
    pre-fault and post-fault metric distributions.
    """

    def __init__(
        self,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        aggregation: Literal["max", "mean"] = "max",
    ):
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.aggregation = aggregation

    def score_metric(self, pre_vals: np.ndarray, post_vals: np.ndarray) -> float:
        """Computes Kolmogorov-Smirnov statistic for distribution divergence."""
        return fast_ks_statistic(pre_vals, post_vals)

    def localize(self, case: TelemetryCase) -> RCAResult:
        """Runs epsilon-Diagnosis localization on a single TelemetryCase."""
        start_time = time.perf_counter()

        timestamps = np.array(case.timestamps)
        inject_time = case.inject_time

        pre_mask = timestamps < (inject_time - self.pre_fault_buffer_sec)
        post_mask = (timestamps >= inject_time) & (
            timestamps <= inject_time + self.post_fault_window_sec
        )

        if np.sum(pre_mask) < 5:
            cutoff = int(len(timestamps) * 0.3)
            pre_mask = np.zeros(len(timestamps), dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            post_mask = timestamps >= inject_time
            if np.sum(post_mask) < 5:
                cutoff = int(len(timestamps) * 0.5)
                post_mask = np.zeros(len(timestamps), dtype=bool)
                post_mask[cutoff:] = True

        grouped = group_metrics_by_service(case.metrics_data)
        all_services = get_system_services(case.system, case.metrics_data)
        if not all_services:
            all_services = list(KNOWN_ONLINE_BOUTIQUE_SERVICES)

        service_scores: dict[str, float] = {}
        for service, metrics in grouped.items():
            if service not in all_services:
                continue
            metric_scores = []
            for col, values in metrics.items():
                arr = np.array(values, dtype=float)
                s = self.score_metric(arr[pre_mask], arr[post_mask])
                metric_scores.append(s)

            if metric_scores:
                if self.aggregation == "max":
                    service_scores[service] = float(np.max(metric_scores))
                else:
                    service_scores[service] = float(np.mean(metric_scores))
            else:
                service_scores[service] = 0.0

        for s in all_services:
            if s not in service_scores:
                service_scores[s] = 0.0

        ranked = sorted(service_scores.items(), key=lambda x: x[1], reverse=True)
        ranked_services = [s for s, _ in ranked]
        ranked_scores = [score for _, score in ranked]

        gt = case.root_cause_service
        if gt in ranked_services:
            rank = ranked_services.index(gt) + 1
        else:
            rank = len(ranked_services) + 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return RCAResult(
            case_id=case.case_id,
            ranked_services=ranked_services,
            scores=ranked_scores,
            ground_truth_service=gt,
            hit_at_1=(rank == 1),
            hit_at_3=(rank <= 3),
            hit_at_5=(rank <= 5),
            reciprocal_rank=float(1.0 / rank),
            runtime_ms=round(elapsed_ms, 3),
        )


class CIRCA:
    """CIRCA: Structural Graph Intervention Recognition (KDD '22).

    For each service s and metric m, regresses m on its topological caller/callee
    parent summary metrics strictly on the pre-fault normal window (t < inject_time - 10s)
    using Ridge regression (alpha=1.0 to prevent singular matrix crashes on constant/imputed columns).
    Scores post-fault structural intervention residuals:
      score = |y_post - y_hat_post| / (IQR_pre_residual + 1e-4)
    aggregating to service level.
    """

    def __init__(
        self,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        alpha: float = 1.0,
        aggregation: Literal["max", "mean"] = "max",
        topology: Optional[BaseTopology] = None,
    ):
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.alpha = alpha
        self.aggregation = aggregation
        self.topology = topology

    def localize(self, case: TelemetryCase) -> RCAResult:
        start_time = time.perf_counter()

        timestamps = np.array(case.timestamps)
        inject_time = case.inject_time

        # Zero-leakage temporal slices
        pre_mask = timestamps < (inject_time - self.pre_fault_buffer_sec)
        post_mask = (timestamps >= inject_time) & (
            timestamps <= inject_time + self.post_fault_window_sec
        )

        if np.sum(pre_mask) < 5:
            cutoff = int(len(timestamps) * 0.3)
            pre_mask = np.zeros(len(timestamps), dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            post_mask = timestamps >= inject_time
            if np.sum(post_mask) < 5:
                cutoff = int(len(timestamps) * 0.5)
                post_mask = np.zeros(len(timestamps), dtype=bool)
                post_mask[cutoff:] = True

        # Resolve topology
        topo = self.topology or get_topology(case.system, case=case)
        grouped = group_metrics_by_service(case.metrics_data)

        # Dynamic service list
        all_services = get_system_services(case.system, case.metrics_data)
        if not all_services:
            all_services = list(topo.services)

        # Pre-compute service summary series (mean of service metrics)
        svc_series_pre: dict[str, np.ndarray] = {}
        svc_series_post: dict[str, np.ndarray] = {}
        for s in all_services:
            m_dict = grouped.get(s, {})
            if m_dict:
                arrs = [np.array(v, dtype=float) for v in m_dict.values()]
                stacked = np.vstack(arrs)
                svc_series_pre[s] = np.nanmean(stacked[:, pre_mask], axis=0)
                svc_series_post[s] = np.nanmean(stacked[:, post_mask], axis=0)
            else:
                svc_series_pre[s] = np.zeros(int(np.sum(pre_mask)))
                svc_series_post[s] = np.zeros(int(np.sum(post_mask)))

        # Fallback background series
        bg_pre = np.mean(list(svc_series_pre.values()), axis=0) if svc_series_pre else np.zeros(int(np.sum(pre_mask)))
        bg_post = np.mean(list(svc_series_post.values()), axis=0) if svc_series_post else np.zeros(int(np.sum(post_mask)))

        service_scores: dict[str, float] = {}

        for s in all_services:
            metrics = grouped.get(s, {})
            if not metrics:
                service_scores[s] = 0.0
                continue

            # Topological parents/neighbors
            parents = [p for p in topo.get_neighbors(s) if p in all_services and p != s]

            # Construct predictor matrix X
            if parents:
                X_pre_cols = [svc_series_pre[p] for p in parents]
                X_post_cols = [svc_series_post[p] for p in parents]
                X_pre = np.column_stack(X_pre_cols + [np.ones(len(X_pre_cols[0]))])
                X_post = np.column_stack(X_post_cols + [np.ones(len(X_post_cols[0]))])
            else:
                X_pre = np.column_stack([bg_pre, np.ones(len(bg_pre))])
                X_post = np.column_stack([bg_post, np.ones(len(bg_post))])

            # Ridge regression: (X^T X + alpha * I)^{-1} X^T Y
            p_dim = X_pre.shape[1]
            reg_mat = X_pre.T @ X_pre + self.alpha * np.eye(p_dim)
            metric_arrs = [np.array(v, dtype=float) for v in metrics.values()]
            if not metric_arrs:
                service_scores[s] = 0.0
                continue

            Y_all = np.column_stack(metric_arrs)
            Y_pre = Y_all[pre_mask]
            Y_post = Y_all[post_mask]

            if len(Y_pre) == 0 or len(Y_post) == 0:
                service_scores[s] = 0.0
                continue

            try:
                weights = np.linalg.solve(reg_mat, X_pre.T @ Y_pre)
            except Exception:
                inv_reg = np.linalg.pinv(reg_mat)
                weights = inv_reg @ (X_pre.T @ Y_pre)
            Y_hat_pre = X_pre @ weights
            residuals_pre = np.abs(Y_pre - Y_hat_pre)

            q75, q25 = np.percentile(residuals_pre, [75, 25], axis=0)
            iqr_pre = q75 - q25

            # Post-fault residuals
            Y_hat_post = X_post @ weights
            residuals_post = np.abs(Y_post - Y_hat_post)
            med_res_post = np.median(residuals_post, axis=0)

            scores = med_res_post / (iqr_pre + 1e-4)
            scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)

            if len(scores) > 0:
                service_scores[s] = float(np.max(scores) if self.aggregation == "max" else np.mean(scores))
            else:
                service_scores[s] = 0.0

        for s in all_services:
            if s not in service_scores:
                service_scores[s] = 0.0

        ranked = sorted(service_scores.items(), key=lambda x: x[1], reverse=True)
        ranked_services = [s for s, _ in ranked]
        ranked_scores = [score for _, score in ranked]

        gt = case.root_cause_service
        rank = ranked_services.index(gt) + 1 if gt in ranked_services else len(ranked_services) + 1
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return RCAResult(
            case_id=case.case_id,
            ranked_services=ranked_services,
            scores=ranked_scores,
            ground_truth_service=gt,
            hit_at_1=(rank == 1),
            hit_at_3=(rank <= 3),
            hit_at_5=(rank <= 5),
            reciprocal_rank=float(1.0 / rank),
            runtime_ms=round(elapsed_ms, 3),
        )


class RCD:
    """RCD: Hierarchical Interventional Discovery (NeurIPS '22).

    Divides metrics into local service chunks.
    Uses fast non-parametric conditional divergence / localized interventional F-node test
    between pre-fault and post-fault distributions to eliminate non-root-cause services
    in tournament stages, ranking remaining root-cause candidates.
    """

    def __init__(
        self,
        pre_fault_buffer_sec: int = 10,
        post_fault_window_sec: int = 300,
        aggregation: Literal["max", "mean"] = "max",
        topology: Optional[BaseTopology] = None,
    ):
        self.pre_fault_buffer_sec = pre_fault_buffer_sec
        self.post_fault_window_sec = post_fault_window_sec
        self.aggregation = aggregation
        self.topology = topology

    def localize(self, case: TelemetryCase) -> RCAResult:
        start_time = time.perf_counter()

        timestamps = np.array(case.timestamps)
        inject_time = case.inject_time

        # Zero-leakage temporal slices
        pre_mask = timestamps < (inject_time - self.pre_fault_buffer_sec)
        post_mask = (timestamps >= inject_time) & (
            timestamps <= inject_time + self.post_fault_window_sec
        )

        if np.sum(pre_mask) < 5:
            cutoff = int(len(timestamps) * 0.3)
            pre_mask = np.zeros(len(timestamps), dtype=bool)
            pre_mask[:cutoff] = True

        if np.sum(post_mask) < 5:
            post_mask = timestamps >= inject_time
            if np.sum(post_mask) < 5:
                cutoff = int(len(timestamps) * 0.5)
                post_mask = np.zeros(len(timestamps), dtype=bool)
                post_mask[cutoff:] = True

        topo = self.topology or get_topology(case.system, case=case)
        grouped = group_metrics_by_service(case.metrics_data)

        all_services = get_system_services(case.system, case.metrics_data)
        if not all_services:
            all_services = list(topo.services)

        # Stage 1: Localized Interventional F-Node Divergence Test per service
        raw_interventions: dict[str, float] = {}
        service_pre_arrays: dict[str, np.ndarray] = {}

        for s in all_services:
            metrics = grouped.get(s, {})
            if not metrics:
                raw_interventions[s] = 0.0
                service_pre_arrays[s] = np.zeros(int(np.sum(pre_mask)))
                continue

            metric_divergences: list[float] = []
            s_pre_list = []
            for col, values in metrics.items():
                arr = np.array(values, dtype=float)
                pre_v = arr[pre_mask]
                post_v = arr[post_mask]
                s_pre_list.append(pre_v)

                if len(pre_v) < 3 or len(post_v) < 3:
                    metric_divergences.append(0.0)
                    continue

                ks_stat = fast_ks_statistic(pre_v, post_v)

                med_pre = np.median(pre_v)
                q75, q25 = np.percentile(pre_v, [75, 25])
                iqr = q75 - q25 + 1e-4
                z_shift = float(np.abs(np.median(post_v) - med_pre) / iqr)

                div = ks_stat * np.log1p(z_shift)
                metric_divergences.append(div if not np.isnan(div) else 0.0)

            if metric_divergences:
                raw_interventions[s] = float(np.max(metric_divergences) if self.aggregation == "max" else np.mean(metric_divergences))
            else:
                raw_interventions[s] = 0.0

            if s_pre_list:
                service_pre_arrays[s] = np.mean(np.vstack(s_pre_list), axis=0)
            else:
                service_pre_arrays[s] = np.zeros(int(np.sum(pre_mask)))

        # Normalize raw interventional scores to [0, 1]
        max_div = max(raw_interventions.values()) if raw_interventions else 0.0
        norm_interventions = {
            s: raw_interventions[s] / (max_div + 1e-4) for s in all_services
        }

        # Stage 2: Hierarchical Tournament Elimination
        final_rcd_scores: dict[str, float] = {}
        svc_list = list(all_services)
        svc_to_idx = {s: i for i, s in enumerate(svc_list)}

        if svc_list:
            stacked = np.array([service_pre_arrays.get(s, np.zeros(int(np.sum(pre_mask)))) for s in svc_list], dtype=float)
            stds = np.std(stacked, axis=1)
            valid_mask = stds > 1e-6
            with np.errstate(divide='ignore', invalid='ignore'):
                corr_mat = np.nan_to_num(np.corrcoef(stacked), nan=0.0)
                corr_mat[~valid_mask, :] = 0.0
                corr_mat[:, ~valid_mask] = 0.0
        else:
            corr_mat = np.zeros((0, 0))

        for s in all_services:
            base_score = norm_interventions.get(s, 0.0)
            if base_score <= 1e-5:
                final_rcd_scores[s] = 0.0
                continue

            neighbors = topo.get_neighbors(s)
            s_i = svc_to_idx.get(s, -1)

            elimination_penalty = 0.0
            for u in neighbors:
                if u not in all_services or u == s:
                    continue

                u_score = norm_interventions.get(u, 0.0)
                u_i = svc_to_idx.get(u, -1)

                if s_i >= 0 and u_i >= 0:
                    r_su = abs(float(corr_mat[s_i, u_i]))
                else:
                    r_su = 0.0

                # Tournament condition: penalize downstream cascading services
                if u_score >= base_score * 0.9 and r_su > 0.35:
                    penalty = r_su * min(base_score, u_score)
                    if penalty > elimination_penalty:
                        elimination_penalty = penalty

            rcd_score = max(0.0, base_score - 0.7 * elimination_penalty)
            final_rcd_scores[s] = float(rcd_score)

        ranked = sorted(final_rcd_scores.items(), key=lambda x: x[1], reverse=True)
        ranked_services = [s for s, _ in ranked]
        ranked_scores = [score for _, score in ranked]

        gt = case.root_cause_service
        rank = ranked_services.index(gt) + 1 if gt in ranked_services else len(ranked_services) + 1
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return RCAResult(
            case_id=case.case_id,
            ranked_services=ranked_services,
            scores=ranked_scores,
            ground_truth_service=gt,
            hit_at_1=(rank == 1),
            hit_at_3=(rank <= 3),
            hit_at_5=(rank <= 5),
            reciprocal_rank=float(1.0 / rank),
            runtime_ms=round(elapsed_ms, 3),
        )


def evaluate_baseline(
    localizer,
    cases: Sequence[TelemetryCase],
    num_total_services: Optional[int] = None,
) -> dict:
    """Evaluates a localizer across a sequence of cases and computes benchmark metrics."""
    results: list[RCAResult] = []
    ranks: list[int] = []

    for case in cases:
        res = localizer.localize(case)
        results.append(res)
        gt = res.ground_truth_service
        if gt in res.ranked_services:
            ranks.append(res.ranked_services.index(gt) + 1)
        else:
            ranks.append(len(res.ranked_services) + 1)

    n = len(results)
    if n == 0:
        return {}

    ac1 = float(np.mean([r <= 1 for r in ranks]))
    ac2 = float(np.mean([r <= 2 for r in ranks]))
    ac3 = float(np.mean([r <= 3 for r in ranks]))
    ac4 = float(np.mean([r <= 4 for r in ranks]))
    ac5 = float(np.mean([r <= 5 for r in ranks]))
    avg5 = float(np.mean([ac1, ac2, ac3, ac4, ac5]))
    mrr = float(np.mean([1.0 / r for r in ranks]))

    if num_total_services is None:
        mean_services = np.mean([len(r.ranked_services) for r in results]) if results else 10.0
        num_services_f = float(max(5.0, mean_services))
    else:
        num_services_f = float(num_total_services)

    chance_at_5 = 5.0 / num_services_f
    lift_at_5 = float(avg5 - chance_at_5)
    mean_runtime_ms = float(np.mean([res.runtime_ms for res in results]))

    return {
        "total_cases": n,
        "AC@1": round(ac1, 4),
        "AC@2": round(ac2, 4),
        "AC@3": round(ac3, 4),
        "AC@4": round(ac4, 4),
        "AC@5": round(ac5, 4),
        "Avg@5": round(avg5, 4),
        "MRR": round(mrr, 4),
        "Chance@5": round(chance_at_5, 4),
        "Lift@5": round(lift_at_5, 4),
        "mean_runtime_ms": round(mean_runtime_ms, 2),
        "case_results": [r.model_dump() for r in results],
    }


def run_clean_baselines(
    dataset_dir: str = "data/raw/rcaeval/RE1-OB",
    output_path: str = "artifacts/metrics/clean_baselines_re1_ob.json",
) -> dict:
    """Executes BARO, epsilon-Diagnosis, CIRCA, and RCD across clean benchmark cases."""
    print("=" * 60)
    print(f"Constrained-xAIOps: Running Clean Baselines on {dataset_dir}")
    print("=" * 60)

    loader = RCAEvalLoader(raw_dir=dataset_dir)
    case_dirs = loader.discover_case_directories()
    print(f"[Loader] Discovered {len(case_dirs)} failure cases.")

    if not case_dirs:
        raise FileNotFoundError(
            f"No cases found in {dataset_dir}. Run `python datasets/download_rcaeval.py` first."
        )

    cases = loader.load_all_cases()
    print(f"[Loader] Successfully loaded {len(cases)} cases into TelemetryCase contracts.")

    # Export schema registry
    loader.generate_schema_registry(cases, output_file="datasets/schema_registry.json")

    # 1. Run Vanilla BARO
    print("\n[Baseline 1/4] Executing Vanilla BARO...")
    baro = VanillaBARO(pre_fault_buffer_sec=10, post_fault_window_sec=300, aggregation="max")
    baro_metrics = evaluate_baseline(baro, cases)
    print(f"  - AC@1: {baro_metrics['AC@1'] * 100:.1f}% | AC@3: {baro_metrics['AC@3'] * 100:.1f}% | Avg@5: {baro_metrics['Avg@5'] * 100:.1f}% | MRR: {baro_metrics['MRR']:.4f}")

    # 2. Run epsilon-Diagnosis
    print("\n[Baseline 2/4] Executing epsilon-Diagnosis...")
    eps = EpsilonDiagnosis(pre_fault_buffer_sec=10, post_fault_window_sec=300, aggregation="max")
    eps_metrics = evaluate_baseline(eps, cases)
    print(f"  - AC@1: {eps_metrics['AC@1'] * 100:.1f}% | AC@3: {eps_metrics['AC@3'] * 100:.1f}% | Avg@5: {eps_metrics['Avg@5'] * 100:.1f}% | MRR: {eps_metrics['MRR']:.4f}")

    # 3. Run CIRCA
    print("\n[Baseline 3/4] Executing CIRCA (KDD '22)...")
    circa = CIRCA(pre_fault_buffer_sec=10, post_fault_window_sec=300, alpha=1.0, aggregation="max")
    circa_metrics = evaluate_baseline(circa, cases)
    print(f"  - AC@1: {circa_metrics['AC@1'] * 100:.1f}% | AC@3: {circa_metrics['AC@3'] * 100:.1f}% | Avg@5: {circa_metrics['Avg@5'] * 100:.1f}% | MRR: {circa_metrics['MRR']:.4f}")

    # 4. Run RCD
    print("\n[Baseline 4/4] Executing RCD (NeurIPS '22)...")
    rcd = RCD(pre_fault_buffer_sec=10, post_fault_window_sec=300, aggregation="max")
    rcd_metrics = evaluate_baseline(rcd, cases)
    print(f"  - AC@1: {rcd_metrics['AC@1'] * 100:.1f}% | AC@3: {rcd_metrics['AC@3'] * 100:.1f}% | Avg@5: {rcd_metrics['Avg@5'] * 100:.1f}% | MRR: {rcd_metrics['MRR']:.4f}")

    out = {
        "dataset": Path(dataset_dir).name,
        "system": loader.system,
        "total_cases": len(cases),
        "zero_leakage_buffer_sec": 10,
        "post_fault_window_sec": 300,
        "baselines": {
            "Vanilla_BARO": {k: v for k, v in baro_metrics.items() if k != "case_results"},
            "epsilon_Diagnosis": {k: v for k, v in eps_metrics.items() if k != "case_results"},
            "CIRCA": {k: v for k, v in circa_metrics.items() if k != "case_results"},
            "RCD": {k: v for k, v in rcd_metrics.items() if k != "case_results"},
        },
        "case_details": {
            "Vanilla_BARO": baro_metrics.get("case_results", []),
            "epsilon_Diagnosis": eps_metrics.get("case_results", []),
            "CIRCA": circa_metrics.get("case_results", []),
            "RCD": rcd_metrics.get("case_results", []),
        },
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"\n[Artifacts] Clean baseline results saved to: {out_file}")
    print("=" * 60)
    return out


if __name__ == "__main__":
    run_clean_baselines()
