"""High-Performance FastAPI Backend for Constrained-xAIOps Dashboard.

Utilizes all available CPU cores (16-thread hardware concurrency) to execute
real-time telemetry simulation, 5D trust evaluation, selective gating,
Trust-Weighted RCA, and Missingness-Aware TreeSHAP explanations.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
import psutil
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.abstention.selective_gate import SelectiveGate
from src.correlation.correlator import correlate_incident
from src.correlation.topology import OnlineBoutiqueTopology
from src.detection.statistical import RobustZScoreDetector
from src.explainability.shap_explainer import MissingnessAwareSHAPExplainer
from src.feedback.recalibrator import OnlineThresholdRecalibrator
from src.feedback.store import FeedbackStore
from src.ingestion.aligner import KNOWN_ONLINE_BOUTIQUE_SERVICES
from src.ingestion.rcaeval_loader import RCAEvalLoader
from src.missingness.generator import MissingnessGenerator
from src.preprocessing.imputer import CausalImputer
from src.quality.trust_score import TelemetryTrustEvaluator
from src.rca.baro_trust import TrustWeightedBARO
from src.rca.baselines import VanillaBARO
from src.schemas import TelemetryCase

app = FastAPI(
    title="Constrained-xAIOps API",
    description="High-Throughput Operational API for Constrained Microservice RCA",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize 16-thread concurrency pool
MAX_WORKERS = min(16, max(4, os.cpu_count() or 16))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Lazy singleton engine storage
class EngineContainer:
    def __init__(self):
        self.cases_map: Dict[str, TelemetryCase] = {}
        self.loader = RCAEvalLoader(raw_dir="data/raw/rcaeval/RE1-OB")
        self.gen = MissingnessGenerator(seed=42)
        self.evaluator = TelemetryTrustEvaluator()
        self.imputer = CausalImputer(method="forward_fill")
        self.detector = RobustZScoreDetector()
        self.vanilla_baro = VanillaBARO()
        self.tw_baro = TrustWeightedBARO(lambda_mnar=3.5)
        self.gate = SelectiveGate(tau_T=0.85, tau_A=0.35, enable_mnar_escalation=True)
        self.topology = OnlineBoutiqueTopology()
        self.feedback_store = FeedbackStore()
        self.recalibrator = OnlineThresholdRecalibrator(initial_tau_T=0.85, initial_tau_A=0.35, initial_lambda_mnar=3.5)
        self.explainer = MissingnessAwareSHAPExplainer(mode="constrained_xaiops", seed=42)
        self.is_loaded = False

    def ensure_loaded(self):
        if not self.is_loaded:
            cases = self.loader.load_all_cases()
            self.cases_map = {c.case_id: c for c in cases}
            self.is_loaded = True

engines = EngineContainer()


# Request / Response Models
class SimulationRequest(BaseModel):
    case_id: str = Field(..., description="Target RCAEval case identifier")
    mechanism: Literal["MCAR", "MAR", "MNAR"] = Field("MNAR", description="Missingness mechanism")
    p_miss: float = Field(0.40, ge=0.0, le=0.80, description="Missingness degradation rate [0.0, 0.80]")
    enable_escalation: bool = Field(True, description="Enable Dual-Branch MNAR Escalation")
    explain_root_cause: bool = Field(True, description="Compute TreeSHAP attributions on top candidate")


class FeedbackRequest(BaseModel):
    case_id: str
    service: str
    verdict: Literal["CONFIRM_RCA", "FALSE_POSITIVE", "CONFIRM_MNAR_CRASH"]
    trust_score: float
    anomaly_score: float


@app.get("/health")
def get_health() -> Dict[str, Any]:
    """Returns hardware utilization and thread-pool concurrency status."""
    vm = psutil.virtual_memory()
    return {
        "status": "healthy",
        "cpu_logical_cores": os.cpu_count(),
        "hardware_concurrency_threads": MAX_WORKERS,
        "ram_total_gb": round(vm.total / (1024**3), 2),
        "ram_used_gb": round(vm.used / (1024**3), 2),
        "ram_percent": vm.percent,
        "active_cases_in_memory": len(engines.cases_map),
        "feedback_records_count": engines.feedback_store.count(),
        "current_tau_T": engines.recalibrator.tau_T,
        "current_tau_A": engines.recalibrator.tau_A,
        "current_lambda_mnar": engines.recalibrator.lambda_mnar,
    }


@app.get("/cases")
def list_cases() -> List[Dict[str, Any]]:
    """Lists all loaded benchmark cases."""
    engines.ensure_loaded()
    out = []
    for cid, c in engines.cases_map.items():
        out.append({
            "case_id": c.case_id,
            "system": c.system,
            "root_cause_service": c.root_cause_service,
            "root_cause_indicator": c.root_cause_indicator,
            "inject_time": c.inject_time,
            "num_metrics": len(c.metrics_data),
            "timestamps_count": len(c.timestamps),
        })
    return out


@app.post("/simulate")
def simulate_incident(req: SimulationRequest) -> Dict[str, Any]:
    """Runs end-to-end telemetry corruption, trust evaluation, selective gating, and RCA."""
    engines.ensure_loaded()
    if req.case_id not in engines.cases_map:
        raise HTTPException(status_code=404, detail=f"Case '{req.case_id}' not found.")

    case = engines.cases_map[req.case_id]
    start_sim = time.perf_counter()

    # 1. Apply corruption
    corr_dict, mask = engines.gen.apply_corruption(
        case=case,
        mechanism=req.mechanism,
        p_miss=req.p_miss,
        seed=42 + int(req.p_miss * 100),
    )

    # 2. Causally impute for Vanilla BARO baseline
    corr_df = pd.DataFrame(corr_dict)
    inj_idx = next((i for i, t in enumerate(case.timestamps) if t >= case.inject_time), len(case.timestamps) // 2)
    imp_df = engines.imputer.impute(corr_df, mask=mask, inject_time_idx=inj_idx)
    imp_case = TelemetryCase(
        case_id=case.case_id,
        system=case.system,
        metrics_data={col: imp_df[col].tolist() for col in imp_df.columns},
        timestamps=case.timestamps,
        inject_time=case.inject_time,
        root_cause_service=case.root_cause_service,
        root_cause_indicator=case.root_cause_indicator,
        data_source_tag=case.data_source_tag,
    )

    # 3. 5D Telemetry Trust Evaluation
    trust_eval = engines.evaluator.evaluate_case(case, mask=mask)

    # 4. Zero-Leakage Anomaly Detection
    anomaly_scores = engines.detector.detect(imp_case, mask=mask)

    # 5. Selective Gate Evaluation
    gate = SelectiveGate(
        tau_T=engines.recalibrator.tau_T,
        tau_A=engines.recalibrator.tau_A,
        enable_mnar_escalation=req.enable_escalation,
    )
    decisions = gate.evaluate_case(
        case=imp_case,
        trust_eval=trust_eval,
        anomaly_scores=anomaly_scores,
        mask=mask,
    )

    # 6. Incident Correlation
    correlation = correlate_incident(
        decisions=decisions,
        trust_eval=trust_eval,
        topology=engines.topology,
    )

    # 7. Localization: Vanilla BARO vs. Constrained-xAIOps (Trust-Weighted BARO)
    vanilla_res = engines.vanilla_baro.localize(imp_case)
    tw_res = engines.tw_baro.localize(
        case=imp_case,
        mask=mask,
        trust_eval=trust_eval,
        enable_mnar_prior=req.enable_escalation,
    )

    # 8. TreeSHAP Attribution on top candidate
    top_candidate = tw_res.ranked_services[0] if tw_res.ranked_services else case.root_cause_service
    explanation_res = {}
    if req.explain_root_cause:
        explanation_res = engines.explainer.explain_service(
            service=top_candidate,
            case=imp_case,
            mask=mask,
        )

    elapsed_ms = (time.perf_counter() - start_sim) * 1000.0

    return {
        "case_id": req.case_id,
        "ground_truth": {
            "root_cause_service": case.root_cause_service,
            "root_cause_indicator": case.root_cause_indicator,
        },
        "simulation_parameters": {
            "mechanism": req.mechanism,
            "p_miss": req.p_miss,
            "enable_escalation": req.enable_escalation,
        },
        "trust_evaluation": {
            "T_sys": round(trust_eval.dimensions["T_sys"], 4),
            "dimensions": {k: round(v, 4) for k, v in trust_eval.dimensions.items()},
            "service_scores": {k: round(v, 4) for k, v in trust_eval.service_scores.items()},
        },
        "anomaly_scores": {k: round(v, 4) for k, v in anomaly_scores.items()},
        "selective_decisions": {
            s: {
                "outcome": d.outcome,
                "trust_score": round(d.trust_score, 4),
                "anomaly_score": round(d.anomaly_score, 4),
            }
            for s, d in decisions.items()
        },
        "incident_correlation": correlation,
        "rca_comparison": {
            "vanilla_baro": {
                "ranked_services": vanilla_res.ranked_services,
                "scores": [round(s, 4) for s in vanilla_res.scores],
                "hit_at_1": vanilla_res.hit_at_1,
                "hit_at_3": vanilla_res.hit_at_3,
                "reciprocal_rank": round(vanilla_res.reciprocal_rank, 4),
            },
            "constrained_xaiops": {
                "ranked_services": tw_res.ranked_services,
                "scores": [round(s, 4) for s in tw_res.scores],
                "hit_at_1": tw_res.hit_at_1,
                "hit_at_3": tw_res.hit_at_3,
                "reciprocal_rank": round(tw_res.reciprocal_rank, 4),
            },
        },
        "explanation": explanation_res,
        "runtime_ms": round(elapsed_ms, 2),
    }


@app.post("/feedback")
def submit_feedback(fb: FeedbackRequest) -> Dict[str, Any]:
    """Records operator triage feedback and recalibrates thresholds online."""
    rec = engines.feedback_store.add_feedback(
        case_id=fb.case_id,
        service=fb.service,
        verdict=fb.verdict,
        trust_score=fb.trust_score,
        anomaly_score=fb.anomaly_score,
    )
    new_state = engines.recalibrator.step(
        verdict=fb.verdict,
        trust_score=fb.trust_score,
        anomaly_score=fb.anomaly_score,
    )
    # Propagate to running gate
    engines.gate.tau_T = new_state["tau_T"]
    engines.gate.tau_A = new_state["tau_A"]
    engines.tw_baro.lambda_mnar = new_state["lambda_mnar"]

    return {
        "status": "success",
        "record": rec,
        "updated_thresholds": new_state,
    }


@app.get("/benchmarks")
def get_benchmarks() -> Dict[str, Any]:
    """Returns precomputed scientific benchmarks from disk."""
    summary_file = Path("artifacts/metrics/statistical_summary.json")
    if not summary_file.exists():
        raise HTTPException(status_code=404, detail="Statistical summary metrics not generated yet.")
    with open(summary_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/benchmarks/multisystem")
def get_multisystem_benchmarks() -> Dict[str, Any]:
    """Returns Phase 6 375-case multi-system, zero-shot, and security metrics from disk."""
    p6_file = Path("artifacts/metrics/phase6_multisystem_and_security.json")
    if not p6_file.exists():
        raise HTTPException(status_code=404, detail="Phase 6 multi-system metrics not generated yet.")
    with open(p6_file, "r", encoding="utf-8") as f:
        return json.load(f)
