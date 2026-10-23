"""Generate High-Resolution Architecture and UML Diagram Suite for Constrained-xAIOps.

Renders publication-grade 300 DPI vector PDFs and raster PNGs:
1. arch1_15stage_pipeline (.pdf, .png)
2. uml1_use_case_diagram (.pdf, .png)
3. uml2_component_and_class_diagram (.pdf, .png)
4. uml3_sequence_diagram_mnar_escalation (.pdf, .png)
5. uml4_kubernetes_deployment_topology (.pdf, .png)
"""

import os
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, ArrowStyle, FancyArrowPatch, Rectangle
import numpy as np

# Styling constants
NAVY = "#0f172a"
BLUE = "#1e3a8a"
LIGHT_BLUE = "#dbeafe"
TEAL = "#0f766e"
LIGHT_TEAL = "#ccfbf1"
AMBER = "#b45309"
LIGHT_AMBER = "#fef3c7"
CRIMSON = "#991b1b"
LIGHT_CRIMSON = "#fee2e2"
SLATE = "#334155"
LIGHT_SLATE = "#f1f5f9"
BORDER_GRAY = "#94a3b8"


def save_fig(fig, out_dir, base_name):
    """Saves figure in both high-res PDF and 300 DPI PNG."""
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"{base_name}.pdf")
    png_path = os.path.join(out_dir, f"{base_name}.png")
    fig.savefig(pdf_path, bbox_inches="tight", dpi=300)
    fig.savefig(png_path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"  + Generated: {base_name}.pdf & .png")


def render_arch1_15stage_pipeline(out_dir):
    """Renders the complete 3-Tier, 15-Stage System Architecture."""
    fig, ax = plt.subplots(figsize=(18, 11), dpi=300)
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 11)
    ax.axis("off")

    # Title header
    ax.text(9, 10.5, "Constrained-xAIOps: 3-Tier, 15-Stage System Architecture", 
            ha="center", va="center", fontsize=18, fontweight="bold", color=NAVY)
    ax.text(9, 10.1, "Data-Quality-Aware, Trust-Gated Selective Anomaly Localization & Explainable Root Cause Analysis",
            ha="center", va="center", fontsize=12, fontstyle="italic", color=SLATE)

    tiers = [
        ("Tier 1: Telemetry Ingestion & 5-Dimensional Trust Auditing", 0.5, 6.7, 17.0, 3.1, LIGHT_BLUE, BLUE),
        ("Tier 2: Conformal Selective Gate & Dual-Branch MNAR Crash Escalator", 0.5, 3.5, 17.0, 3.0, LIGHT_AMBER, AMBER),
        ("Tier 3: Trust-Weighted BARO Causal Discovery & Missingness-Aware TreeSHAP", 0.5, 0.3, 17.0, 3.0, LIGHT_TEAL, TEAL),
    ]

    for title, x, y, w, h, bg, border in tiers:
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1,rounding_size=0.15",
                              ec=border, fc=bg, lw=2.0, alpha=0.6)
        ax.add_patch(rect)
        ax.text(x + 0.3, y + h - 0.35, title, fontsize=12, fontweight="bold", color=border)

    # Tier 1 stages (S1 - S6)
    t1_stages = [
        ("Stage 1\nPrometheus Ingestion\n& Aligner", 0.8, 7.0, 2.4, 1.8),
        ("Stage 2\nCompleteness\nAudit C(s)", 3.6, 7.0, 2.3, 1.8),
        ("Stage 3\nLatency & Drift\nAudit L(s)", 6.3, 7.0, 2.3, 1.8),
        ("Stage 4\nSemantic\nContinuity S(s)", 9.0, 7.0, 2.3, 1.8),
        ("Stage 5\nCross-Metric\nValidity V(s)", 11.7, 7.0, 2.3, 1.8),
        ("Stage 6\n5D Multiplicative\nTrust Score T(s)", 14.4, 7.0, 2.7, 1.8),
    ]

    for name, x, y, w, h in t1_stages:
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.1",
                             ec=BLUE, fc="white", lw=1.5)
        ax.add_patch(box)
        ax.text(x + w/2, y + h/2, name, ha="center", va="center", fontsize=9.5, fontweight="semibold", color=NAVY)

    # Tier 2 stages (S7 - S10)
    t2_stages = [
        ("Stage 7\nSplit-Conformal Gate\n(Non-conformity score R)", 1.2, 3.8, 3.3, 1.9),
        ("Stage 8\n1-Hop Call-Graph\nNeighbor Cascades", 5.2, 3.8, 3.3, 1.9),
        ("Stage 9\nDual-Branch MNAR\nCrash Escalator", 9.2, 3.8, 3.3, 1.9),
        ("Stage 10\n4-State Selective\nDecision Dispatcher", 13.2, 3.8, 3.8, 1.9),
    ]

    for name, x, y, w, h in t2_stages:
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.1",
                             ec=AMBER, fc="white", lw=1.5)
        ax.add_patch(box)
        ax.text(x + w/2, y + h/2, name, ha="center", va="center", fontsize=9.5, fontweight="semibold", color=NAVY)

    # Tier 3 stages (S11 - S15)
    t3_stages = [
        ("Stage 11\nImputation Mask\nPropagation", 0.8, 0.6, 2.8, 1.9),
        ("Stage 12\nTrust-Weighted\nBARO Causal DAG", 4.1, 0.6, 2.9, 1.9),
        ("Stage 13\nMissingness-Aware\nTreeSHAP Attribution", 7.5, 0.6, 3.2, 1.9),
        ("Stage 14\nGini Sparsity &\nReliability Badges", 11.2, 0.6, 2.8, 1.9),
        ("Stage 15\nOperator Feedback\n& Dirichlet Recalib.", 14.5, 0.6, 2.8, 1.9),
    ]

    for name, x, y, w, h in t3_stages:
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.1",
                             ec=TEAL, fc="white", lw=1.5)
        ax.add_patch(box)
        ax.text(x + w/2, y + h/2, name, ha="center", va="center", fontsize=9.5, fontweight="semibold", color=NAVY)

    # Inter-tier connecting arrows
    arrow_style = "Simple,tail_width=1.5,head_width=4.5,head_length=5"
    kw = dict(arrowstyle=arrow_style, color=SLATE)

    # S6 -> S7
    p1 = FancyArrowPatch((15.7, 7.0), (2.8, 5.7), connectionstyle="arc3,rad=-0.15", **kw)
    ax.add_patch(p1)
    ax.text(8.5, 6.4, "Evaluated Trust T(s)", ha="center", fontsize=8.5, fontweight="bold", color=SLATE, bbox=dict(boxstyle="round", fc="white", ec=BORDER_GRAY))

    # S10 -> S11 & S12
    p2 = FancyArrowPatch((15.1, 3.8), (5.5, 2.5), connectionstyle="arc3,rad=-0.15", **kw)
    ax.add_patch(p2)
    ax.text(10.5, 3.2, "Selective Decision: ESCALATE_MNAR / HIGH_CONFIDENCE", ha="center", fontsize=8.5, fontweight="bold", color=AMBER, bbox=dict(boxstyle="round", fc="white", ec=AMBER))

    # S15 -> Tier 1 (Closed-loop feedback)
    p3 = FancyArrowPatch((16.0, 2.5), (16.0, 6.7), connectionstyle="arc3,rad=0.3", **kw)
    ax.add_patch(p3)
    ax.text(17.3, 4.6, "Dirichlet Prior\nFeedback Loop", ha="center", fontsize=8, fontweight="bold", color=TEAL)

    save_fig(fig, out_dir, "arch1_15stage_pipeline")


def render_uml1_use_case_diagram(out_dir):
    """Renders UML Use Case Diagram."""
    fig, ax = plt.subplots(figsize=(14, 9), dpi=300)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(7, 8.5, "Constrained-xAIOps: UML Use Case Diagram", 
            ha="center", va="center", fontsize=16, fontweight="bold", color=NAVY)

    # System boundary
    sys_box = FancyBboxPatch((3.5, 0.5), 7.0, 7.5, boxstyle="round,pad=0.1,rounding_size=0.1",
                             ec=SLATE, fc=LIGHT_SLATE, lw=2.0)
    ax.add_patch(sys_box)
    ax.text(7.0, 7.7, "System Boundary: Constrained-xAIOps Platform", 
            ha="center", va="center", fontsize=11, fontweight="bold", color=SLATE)

    # Actors
    actors = [
        ("SRE / DevOps\nOperator", 1.5, 6.0, BLUE),
        ("Kubernetes &\nPrometheus Cluster", 1.5, 2.5, CRIMSON),
        ("Automated RCA\nExecution Engine", 12.3, 4.2, TEAL),
    ]

    for name, x, y, col in actors:
        # Stick figure head
        head = plt.Circle((x, y + 0.5), 0.3, ec=col, fc="white", lw=2)
        ax.add_patch(head)
        # Body
        ax.plot([x, x], [y + 0.2, y - 0.4], color=col, lw=2)
        # Arms
        ax.plot([x - 0.35, x + 0.35], [y, y], color=col, lw=2)
        # Legs
        ax.plot([x, x - 0.3], [y - 0.4, y - 0.9], color=col, lw=2)
        ax.plot([x, x + 0.3], [y - 0.4, y - 0.9], color=col, lw=2)
        # Label
        ax.text(x, y - 1.25, name, ha="center", va="top", fontsize=9.5, fontweight="bold", color=col)

    # Use Cases (Ellipses)
    use_cases = [
        ("UC-01: Ingest & Align\nMulti-Modal Telemetry", 7.0, 6.8),
        ("UC-02: Audit 5D\nTelemetry Trust", 7.0, 5.6),
        ("UC-03: Conformal Gating &\nAbstention Decision", 7.0, 4.4),
        ("UC-04: Escalate Incident\nMNAR Blackout", 7.0, 3.2),
        ("UC-05: Localize Root Cause via\nTrust-Weighted BARO", 7.0, 2.0),
        ("UC-06: Inspect Missingness-\nAware TreeSHAP Explanations", 7.0, 0.9),
    ]

    for text, cx, cy in use_cases:
        ellipse = FancyBboxPatch((cx - 2.5, cy - 0.42), 5.0, 0.84, boxstyle="round,pad=0.05,rounding_size=0.4",
                                 ec=BLUE, fc="white", lw=1.5)
        ax.add_patch(ellipse)
        ax.text(cx, cy, text, ha="center", va="center", fontsize=8.5, fontweight="semibold", color=NAVY)

    # Association lines
    # K8s -> UC-01
    ax.plot([2.2, 4.5], [2.7, 6.8], color=CRIMSON, lw=1.5, ls="--")
    # SRE -> UC-03, UC-05, UC-06
    ax.plot([2.2, 4.5], [5.8, 4.4], color=BLUE, lw=1.5)
    ax.plot([2.2, 4.5], [5.6, 2.0], color=BLUE, lw=1.5)
    ax.plot([2.2, 4.5], [5.4, 0.9], color=BLUE, lw=1.5)
    # Engine -> all UCs
    for _, _, cy in use_cases:
        ax.plot([9.5, 11.5], [cy, 4.2], color=TEAL, lw=1.2)

    save_fig(fig, out_dir, "uml1_use_case_diagram")


def render_uml2_component_and_class_diagram(out_dir):
    """Renders Component and Class Diagram illustrating Pydantic Data Contracts."""
    fig, ax = plt.subplots(figsize=(16, 10), dpi=300)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(8, 9.5, "Constrained-xAIOps: Component & Pydantic Data Contract Diagram", 
            ha="center", va="center", fontsize=16, fontweight="bold", color=NAVY)

    # Components (Containers)
    classes = [
        # Contract 1
        ("<<Pydantic BaseModel>>\nTelemetryCase (Immutable)", 0.6, 5.2, 3.8, 3.6, LIGHT_BLUE, BLUE, [
            "+ case_id: str",
            "+ system: str",
            "+ metrics_data: dict[str, list[float]]",
            "+ timestamps: list[int]",
            "+ inject_time: int",
            "+ root_cause_service: str",
            "+ root_cause_indicator: str",
            "+ data_source_tag: Literal",
        ]),
        # Contract 2
        ("<<Pydantic BaseModel>>\nTrustEvaluation", 5.2, 5.2, 3.2, 3.6, LIGHT_AMBER, AMBER, [
            "+ case_id: str",
            "+ window_idx: int",
            "+ service_scores: dict[str, float]",
            "+ dimensions: dict[str, float]",
            "  * C: Completeness",
            "  * L: Latency Freshness",
            "  * S: Semantic Continuity",
            "  * V: Structural Validity",
        ]),
        # Contract 3
        ("<<Pydantic BaseModel>>\nSelectiveDecision", 9.2, 5.2, 3.2, 3.6, LIGHT_CRIMSON, CRIMSON, [
            "+ case_id: str",
            "+ service: str",
            "+ outcome: Literal[",
            "    NORMAL,",
            "    HIGH_CONFIDENCE,",
            "    ABSTAIN_LOW_TRUST,",
            "    ESCALATE_MNAR_BLACKOUT]",
            "+ anomaly_score: float",
            "+ trust_score: float",
        ]),
        # Contract 4
        ("<<Pydantic BaseModel>>\nRCAResult", 12.8, 5.2, 2.7, 3.6, LIGHT_TEAL, TEAL, [
            "+ case_id: str",
            "+ ranked_services: list[str]",
            "+ root_cause_service: str",
            "+ precision_at_1: float",
            "+ precision_at_3: float",
            "+ mrr: float",
        ]),
        # Pipeline Services
        ("<<Service Engine>>\nTelemetryTrustEvaluator", 1.5, 0.8, 4.0, 3.2, "white", SLATE, [
            "+ weights: Sequence[float]",
            "+ evaluate_case(case, mask)",
            "+ compute_5d_trust_score(case)",
            "+ calibrate_weights(validation_cases)",
        ]),
        ("<<Service Engine>>\nSelectiveGate", 6.5, 0.8, 4.0, 3.2, "white", SLATE, [
            "+ tau_T: float = 0.816",
            "+ tau_A: float = 0.35",
            "+ enable_mnar_escalation: bool",
            "+ evaluate_case(case, trust, scores)",
            "+ detect_mnar_blackout(...)",
        ]),
        ("<<Service Engine>>\nTrustWeightedBARO & SHAP", 11.5, 0.8, 4.0, 3.2, "white", SLATE, [
            "+ tau_G: float = 0.50",
            "+ alpha: float = 0.05",
            "+ fit_predict(case, decisions)",
            "+ explain_service(svc, case, mask)",
        ]),
    ]

    for title, x, y, w, h, bg, border, fields in classes:
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.1",
                             ec=border, fc=bg, lw=1.8)
        ax.add_patch(box)
        # Header banner
        header_h = 0.85
        header = FancyBboxPatch((x, y + h - header_h), w, header_h, boxstyle="round,pad=0.08,rounding_size=0.1",
                                ec=border, fc=border, lw=1.8)
        ax.add_patch(header)
        ax.text(x + w/2, y + h - header_h/2, title, ha="center", va="center", fontsize=8.5, fontweight="bold", color="white")

        # Field lines
        fy = y + h - header_h - 0.25
        for field in fields:
            ax.text(x + 0.15, fy, field, fontsize=7.8, fontfamily="monospace", color=NAVY)
            fy -= 0.30

    # Arrows connecting contracts to engines
    arrow_style = "Simple,tail_width=1.2,head_width=3.5,head_length=4"
    kw = dict(arrowstyle=arrow_style, color=SLATE)

    ax.add_patch(FancyArrowPatch((2.5, 5.2), (3.0, 4.0), **kw))
    ax.add_patch(FancyArrowPatch((6.8, 4.0), (6.8, 5.2), **kw))
    ax.add_patch(FancyArrowPatch((8.5, 4.0), (10.0, 5.2), **kw))
    ax.add_patch(FancyArrowPatch((12.5, 4.0), (13.5, 5.2), **kw))

    save_fig(fig, out_dir, "uml2_component_and_class_diagram")


def render_uml3_sequence_diagram_mnar_escalation(out_dir):
    """Renders UML Sequence Diagram showing the MNAR Escalation execution flow."""
    fig, ax = plt.subplots(figsize=(17, 10), dpi=300)
    ax.set_xlim(0, 17)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(8.5, 9.6, "Constrained-xAIOps: Sequence Diagram — Incident-Driven MNAR Crash Escalation", 
            ha="center", va="center", fontsize=15, fontweight="bold", color=NAVY)

    lifelines = [
        ("Chaos Mesh\nTestbed", 1.5),
        ("Target Service\n(cartservice)", 4.0),
        ("Prometheus\nExporter", 6.8),
        ("Trust Evaluator\n(5D Score)", 9.5),
        ("Conformal\nSelective Gate", 12.2),
        ("Trust-Weighted BARO\n& TreeSHAP", 15.0),
    ]

    # Draw lifeline headers and vertical dotted lines
    for name, x in lifelines:
        box = FancyBboxPatch((x - 1.1, 8.4), 2.2, 0.8, boxstyle="round,pad=0.05,rounding_size=0.1",
                             ec=BLUE, fc=LIGHT_BLUE, lw=1.5)
        ax.add_patch(box)
        ax.text(x, 8.8, name, ha="center", va="center", fontsize=8.5, fontweight="bold", color=NAVY)
        ax.plot([x, x], [1.0, 8.4], color=BORDER_GRAY, ls="--", lw=1.2)

    # Messages
    messages = [
        (1, 1.5, 4.0, 7.8, "1. PodChaos / Kill container (t_inject)", CRIMSON),
        (2, 4.0, 6.8, 7.0, "2. Crash: Process dies & socket closes", CRIMSON),
        (3, 6.8, 9.5, 6.2, "3. Range query: 75% telemetry missing (MNAR)", AMBER),
        (4, 9.5, 9.5, 5.4, "4. Compute 5D Trust: Completeness drops C=0.25, T=0.42 < tau_T", SLATE),
        (5, 9.5, 12.2, 4.6, "5. Forward TrustEvaluation & Call-Graph neighbor symptoms", BLUE),
        (6, 12.2, 12.2, 3.8, "6. Detect Neighbor Cascade: frontend A_neigh=0.88 >= tau_A", AMBER),
        (7, 12.2, 15.0, 3.0, "7. Fire ESCALATE_MNAR_BLACKOUT (Bypass passive drop)", TEAL),
        (8, 15.0, 15.0, 2.2, "8. Inject prior pi(s) propto exp(lambda*(1-C)) -> Rank #1 Root Cause", TEAL),
        (9, 15.0, 1.5, 1.4, "9. Return RCAResult (cartservice) + Missingness-Aware TreeSHAP badge", BLUE),
    ]

    for step, x1, x2, y, text, col in messages:
        if x1 == x2:
            # Self call
            ax.plot([x1, x1 + 0.6, x1 + 0.6, x1], [y + 0.2, y + 0.2, y - 0.2, y - 0.2], color=col, lw=1.5)
            ax.annotate("", xy=(x1, y - 0.2), xytext=(x1 + 0.6, y - 0.2),
                        arrowprops=dict(arrowstyle="->", color=col, lw=1.5))
            ax.text(x1 + 0.7, y, text, va="center", fontsize=8.5, fontweight="bold", color=col)
        else:
            ax.annotate("", xy=(x2, y), xytext=(x1, y),
                        arrowprops=dict(arrowstyle="->", color=col, lw=1.5))
            mid_x = (x1 + x2) / 2
            ax.text(mid_x, y + 0.18, text, ha="center", va="bottom", fontsize=8.2, fontweight="bold", color=col,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=col, alpha=0.9, lw=0.8))

    save_fig(fig, out_dir, "uml3_sequence_diagram_mnar_escalation")


def render_uml4_kubernetes_deployment_topology(out_dir):
    """Renders Kubernetes deployment topology diagram."""
    fig, ax = plt.subplots(figsize=(16, 10), dpi=300)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(8, 9.5, "Constrained-xAIOps: Kubernetes Cloud-Native Deployment Topology", 
            ha="center", va="center", fontsize=16, fontweight="bold", color=NAVY)

    # Kubernetes Cluster boundary
    k8s_box = FancyBboxPatch((0.5, 0.5), 15.0, 8.6, boxstyle="round,pad=0.1,rounding_size=0.15",
                             ec=BLUE, fc="#f8fafc", lw=2.0)
    ax.add_patch(k8s_box)
    ax.text(0.8, 8.8, "Kubernetes Cluster (16 vCPU, 24 GB RAM)", fontsize=12, fontweight="bold", color=BLUE)

    # Namespace 1: Online Boutique Microservices
    ns1 = FancyBboxPatch((0.8, 4.4), 8.5, 4.0, boxstyle="round,pad=0.08,rounding_size=0.1",
                         ec=TEAL, fc=LIGHT_TEAL, lw=1.5, alpha=0.5)
    ax.add_patch(ns1)
    ax.text(1.1, 8.1, "Namespace: boutique (10 Microservices)", fontsize=10.5, fontweight="bold", color=TEAL)

    # 10 Microservice pods
    services = [
        ("frontend", 1.2, 7.1),
        ("cartservice", 3.3, 7.1),
        ("checkoutservice", 5.4, 7.1),
        ("recommendation", 1.2, 5.8),
        ("productcatalog", 3.3, 5.8),
        ("shipping", 5.4, 5.8),
        ("currency", 1.2, 4.6),
        ("payment", 3.3, 4.6),
        ("email", 5.4, 4.6),
        ("adservice", 7.4, 5.8),
    ]

    for name, sx, sy in services:
        p = FancyBboxPatch((sx, sy), 1.8, 0.9, boxstyle="round,pad=0.05,rounding_size=0.08",
                           ec=TEAL, fc="white", lw=1.2)
        ax.add_patch(p)
        ax.text(sx + 0.9, sy + 0.45, f"pod:\n{name}", ha="center", va="center", fontsize=7.5, fontweight="bold", color=NAVY)

    # Namespace 2: Observability & Chaos
    ns2 = FancyBboxPatch((9.7, 4.4), 5.5, 4.0, boxstyle="round,pad=0.08,rounding_size=0.1",
                         ec=AMBER, fc=LIGHT_AMBER, lw=1.5, alpha=0.5)
    ax.add_patch(ns2)
    ax.text(10.0, 8.1, "Observability & Ingress", fontsize=10.5, fontweight="bold", color=AMBER)

    obs = [
        ("Prometheus Server\n(15s scrape interval)", 10.0, 6.7, 4.8, 1.1),
        ("Chaos Mesh Controller\n(PodChaos / NetworkChaos)", 10.0, 5.2, 4.8, 1.1),
    ]
    for text, ox, oy, ow, oh in obs:
        p = FancyBboxPatch((ox, oy), ow, oh, boxstyle="round,pad=0.05,rounding_size=0.08",
                           ec=AMBER, fc="white", lw=1.2)
        ax.add_patch(p)
        ax.text(ox + ow/2, oy + oh/2, text, ha="center", va="center", fontsize=8.5, fontweight="bold", color=NAVY)

    # Namespace 3: Constrained-xAIOps Engine & Dashboard
    ns3 = FancyBboxPatch((0.8, 0.8), 14.4, 3.2, boxstyle="round,pad=0.08,rounding_size=0.1",
                         ec=NAVY, fc=LIGHT_SLATE, lw=1.5)
    ax.add_patch(ns3)
    ax.text(1.1, 3.6, "Namespace: aiops-control-plane (Constrained-xAIOps)", fontsize=10.5, fontweight="bold", color=NAVY)

    engines = [
        ("FastAPI Inference Backend\n(16 CPU Workers, port 8000)", 1.2, 1.2, 4.3, 2.0),
        ("Streamlit Multi-Tab Dashboard\n(port 8501, 5 tabs)", 5.8, 1.2, 4.3, 2.0),
        ("Locust Workload Generator\n(300 Users, headless)", 10.5, 1.2, 4.3, 2.0),
    ]
    for text, ex, ey, ew, eh in engines:
        p = FancyBboxPatch((ex, ey), ew, eh, boxstyle="round,pad=0.05,rounding_size=0.08",
                           ec=NAVY, fc="white", lw=1.2)
        ax.add_patch(p)
        ax.text(ex + ew/2, ey + eh/2, text, ha="center", va="center", fontsize=9, fontweight="bold", color=NAVY)

    # Scrape arrow: Prometheus -> Boutique
    ax.annotate("", xy=(8.5, 7.2), xytext=(10.0, 7.2),
                arrowprops=dict(arrowstyle="->", color=AMBER, lw=2.0))
    ax.text(9.2, 7.45, "15s scrape", ha="center", fontsize=8, fontweight="bold", color=AMBER)

    # API query arrow: FastAPI -> Prometheus
    ax.annotate("", xy=(12.0, 6.7), xytext=(4.0, 3.2),
                arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.8, connectionstyle="arc3,rad=-0.15"))
    ax.text(8.0, 4.1, "HTTP Range Queries /api/v1/query_range", ha="center", fontsize=8, fontweight="bold", color=BLUE)

    save_fig(fig, out_dir, "uml4_kubernetes_deployment_topology")


def main():
    print("======================================================================")
    print("Generating Complete Architecture & UML Diagram Suite (300 DPI Vector)")
    print("======================================================================")
    out_dir = "FINAL_SUBMISSION_PACKAGE/04_Architecture_and_UML_Diagrams"
    os.makedirs(out_dir, exist_ok=True)

    render_arch1_15stage_pipeline(out_dir)
    render_uml1_use_case_diagram(out_dir)
    render_uml2_component_and_class_diagram(out_dir)
    render_uml3_sequence_diagram_mnar_escalation(out_dir)
    render_uml4_kubernetes_deployment_topology(out_dir)

    # Also copy the 5 experimental figures (fig1..fig5) into the architecture folder
    import shutil
    fig_dir = "artifacts/figures"
    for i in range(1, 6):
        for ext in (".pdf", ".png"):
            fname = f"fig{i}"
            for f in os.listdir(fig_dir):
                if f.startswith(fname) and f.endswith(ext):
                    src_f = os.path.join(fig_dir, f)
                    dst_f = os.path.join(out_dir, f)
                    shutil.copy(src_f, dst_f)
                    print(f"  + Copied figure: {f}")

    print("\n[SUCCESS] All UML and Architecture diagrams generated in:")
    print(f"  {out_dir}")
    print("======================================================================")


if __name__ == "__main__":
    main()
