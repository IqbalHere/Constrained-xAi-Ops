"""Core Pydantic v2 Data Contracts for Constrained-xAIOps."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TelemetryCase(BaseModel):
    """Immutable data contract for a single telemetry failure case."""
    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., description="Unique case identifier (e.g., 'cpu-1')")
    system: str = Field(..., description="Target system name (e.g., 'OnlineBoutique')")
    metrics_data: dict[str, list[float]] = Field(
        ..., description="Map of metric names to aligned time-series values"
    )
    timestamps: list[int] = Field(..., description="Aligned Unix timestamps (in seconds)")
    inject_time: int = Field(..., description="Timestamp of fault injection")
    root_cause_service: str = Field(..., description="Ground truth root cause microservice")
    root_cause_indicator: str = Field(..., description="Ground truth root cause metric/indicator")
    data_source_tag: Literal[
        "PUBLIC_BENCHMARK", "LIVE_K8S_TESTBED", "SYNTHETIC_DEMO"
    ] = Field(default="PUBLIC_BENCHMARK", description="Provenance of telemetry data")


class TrustEvaluation(BaseModel):
    """Immutable data contract for telemetry quality and trust evaluation."""
    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., description="Case identifier")
    window_idx: int = Field(..., description="Evaluation window index")
    service_scores: dict[str, float] = Field(
        ..., description="Trust score per service in [0, 1]"
    )
    dimensions: dict[str, float] = Field(
        ..., description="Trust dimension breakdown (e.g., completeness, freshness)"
    )


class SelectiveDecision(BaseModel):
    """Immutable data contract for selective classification and abstention decisions."""
    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., description="Case identifier")
    service: str = Field(..., description="Target service")
    outcome: Literal[
        "NORMAL",
        "HIGH_CONFIDENCE_INCIDENT",
        "ABSTAIN_LOW_TRUST",
        "ESCALATE_MNAR_BLACKOUT",
    ] = Field(..., description="Decision outcome")
    anomaly_score: float = Field(..., description="Computed anomaly score")
    trust_score: float = Field(..., description="Telemetry trust score in [0, 1]")


class RCAResult(BaseModel):
    """Immutable data contract for Root Cause Analysis localization output."""
    model_config = ConfigDict(frozen=True)

    case_id: str = Field(..., description="Case identifier")
    ranked_services: list[str] = Field(
        ..., description="Microservices ranked in descending order of suspicion"
    )
    scores: list[float] = Field(..., description="Suspicion scores corresponding to ranked_services")
    ground_truth_service: str = Field(..., description="Ground truth root cause microservice")
    hit_at_1: bool = Field(..., description="Whether ground truth service is at rank 1")
    hit_at_3: bool = Field(..., description="Whether ground truth service is within top 3")
    hit_at_5: bool = Field(..., description="Whether ground truth service is within top 5")
    reciprocal_rank: float = Field(..., description="1.0 / rank (1-indexed)")
    runtime_ms: float = Field(..., description="Localization runtime in milliseconds")
