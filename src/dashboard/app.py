"""Interactive Operational Dashboard for Constrained-xAIOps.

Features:
1. Real-Time Telemetry Degradation & Incident Simulation (MCAR, MAR, MNAR).
2. 5D Telemetry Trust Score (C, L, S, V, Q) & Multiplicative Floor Monitoring.
3. Call-Graph Topology & Four-State Selective Gate Visualization.
4. Side-by-Side RCA Ranking: Vanilla BARO vs. Constrained-xAIOps.
5. Missingness-Aware TreeSHAP Explanations & Explanation Reliability Badge.
6. Human-in-the-Loop Operator Feedback Triage & Robbins-Monro Recalibration.
7. Multi-Seed Benchmark Explorer & Vector Paper Figures.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psutil
import streamlit as st

from src.dashboard.api import engines, simulate_incident, SimulationRequest, FeedbackRequest

# Streamlit Page Configuration
st.set_page_config(
    page_title="Constrained-xAIOps | Operator Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom High-End Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 1rem;
        border-left: 4px solid #3B82F6;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .badge-normal {
        background-color: #DCFCE7; color: #166534; padding: 4px 8px; border-radius: 4px; font-weight: 600;
    }
    .badge-abstain {
        background-color: #FEF3C7; color: #92400E; padding: 4px 8px; border-radius: 4px; font-weight: 600;
    }
    .badge-incident {
        background-color: #FEE2E2; color: #991B1B; padding: 4px 8px; border-radius: 4px; font-weight: 600;
    }
    .badge-blackout {
        background-color: #F3E8FF; color: #6B21A8; padding: 4px 8px; border-radius: 4px; font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize engines
engines.ensure_loaded()
cases_list = sorted(list(engines.cases_map.keys()))

# Sidebar Controls
st.sidebar.title("🛡️ Constrained-xAIOps")
st.sidebar.markdown("**Data-Quality-Aware Microservice AIOps**")
st.sidebar.markdown("---")

selected_tab = st.sidebar.radio(
    "Navigation Mode",
    [
        "Incident Simulator & RCA",
        "375-Case Multi-System & Security Benchmark",
        "Multi-Seed Benchmark Explorer",
        "Paper Evidence Gallery",
        "Hardware & Live Concurrency",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("Hardware Capacity (Live)")
vm = psutil.virtual_memory()
cpu_count = os.cpu_count() or 16
st.sidebar.write(f"**CPU Cores:** {cpu_count} logical threads")
st.sidebar.write(f"**RAM Utilization:** {vm.used / (1024**3):.1f} / {vm.total / (1024**3):.1f} GB ({vm.percent}%)")
st.sidebar.progress(vm.percent / 100.0)

st.sidebar.markdown("---")
st.sidebar.subheader("Live Operational Parameters")
st.sidebar.write(f"**Conformal Threshold (τ_T):** `{engines.recalibrator.tau_T:.3f}`")
st.sidebar.write(f"**Anomaly Threshold (τ_A):** `{engines.recalibrator.tau_A:.3f}`")
st.sidebar.write(f"**MNAR Prior Weight (λ_mnar):** `{engines.recalibrator.lambda_mnar:.2f}`")


# TAB 1: Incident Simulator & RCA
if selected_tab == "Incident Simulator & RCA":
    st.markdown('<div class="main-header">⚡ Real-Time Incident Simulator & Root Cause Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Evaluate microservice telemetry quality, selective gating, and localization under sensor dropout.</div>', unsafe_allow_html=True)

    col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([2, 1.5, 2, 1.5])

    with col_ctrl1:
        case_id = st.selectbox("Select Benchmark Case", cases_list, index=0)
    with col_ctrl2:
        mechanism = st.selectbox("Missingness Mechanism", ["MNAR", "MAR", "MCAR"], index=0)
    with col_ctrl3:
        p_miss = st.slider("Degradation Rate ($p_{\text{miss}}$)", 0.0, 0.80, 0.40, step=0.10)
    with col_ctrl4:
        enable_escalation = st.checkbox("Enable MNAR Escalator", value=True)

    target_case = engines.cases_map[case_id]
    st.info(
        f"**Case Context:** System: `{target_case.system}` | "
        f"Ground Truth Root Cause: **`{target_case.root_cause_service}`** | "
        f"Fault Indicator: **`{target_case.root_cause_indicator}`** | "
        f"Fault Injected at $t = {target_case.inject_time}$s"
    )

    # Run Simulation
    req = SimulationRequest(
        case_id=case_id,
        mechanism=mechanism,
        p_miss=p_miss,
        enable_escalation=enable_escalation,
        explain_root_cause=True,
    )
    sim_res = simulate_incident(req)

    # Trust & Telemetry Overview Cards
    t_eval = sim_res["trust_evaluation"]
    t_sys = t_eval["T_sys"]
    dims = t_eval["dimensions"]

    st.subheader("1. 5-Dimensional Telemetry Trust Profile")
    m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
    m_col1.metric("System Trust ($T_{\text{sys}}$)", f"{t_sys:.3f}", delta=f"{t_sys - 0.85:.3f}" if t_sys >= 0.85 else f"-{0.85 - t_sys:.3f}")
    m_col2.metric("Completeness ($C$)", f"{dims['C']:.3f}")
    m_col3.metric("Timeliness ($L$)", f"{dims['L']:.3f}")
    m_col4.metric("Consistency ($S$)", f"{dims['S']:.3f}")
    m_col5.metric("Validity ($V$)", f"{dims['V']:.3f}")
    m_col6.metric("Certainty ($Q$)", f"{dims['Q']:.3f}")

    # Microservice Selective Decisions & Call Graph Topology
    st.subheader("2. Microservice Call-Graph & Four-State Selective Decisions")
    decisions = sim_res["selective_decisions"]
    topo_cols = st.columns(5)

    badge_map = {
        "NORMAL": '<span class="badge-normal">NORMAL</span>',
        "ABSTAIN_LOW_TRUST": '<span class="badge-abstain">ABSTAIN (LOW TRUST)</span>',
        "HIGH_CONFIDENCE_INCIDENT": '<span class="badge-incident">HIGH CONFIDENCE ANOMALY</span>',
        "ESCALATE_MNAR_BLACKOUT": '<span class="badge-blackout">ESCALATE (MNAR BLACKOUT)</span>',
    }

    services = sorted(list(decisions.keys()))
    for idx, s in enumerate(services):
        c_idx = idx % 5
        d = decisions[s]
        with topo_cols[c_idx]:
            is_gt = (s == target_case.root_cause_service)
            gt_tag = " ⭐ (Ground Truth)" if is_gt else ""
            st.markdown(
                f"""
                <div class="metric-card" style="margin-bottom: 0.8rem; border-left-color: {'#9333EA' if d['outcome'] == 'ESCALATE_MNAR_BLACKOUT' else ('#EF4444' if d['outcome'] == 'HIGH_CONFIDENCE_INCIDENT' else '#3B82F6')};">
                    <strong>{s}{gt_tag}</strong><br>
                    Status: {badge_map[d['outcome']]}<br>
                    <small>Trust: {d['trust_score']:.2f} | Anomaly: {d['anomaly_score']:.2f}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Side-by-Side RCA Comparison
    st.subheader("3. Root Cause Localization: Vanilla BARO vs. Constrained-xAIOps")
    rca = sim_res["rca_comparison"]
    v_rca = rca["vanilla_baro"]
    tw_rca = rca["constrained_xaiops"]

    rca_col1, rca_col2 = st.columns(2)

    with rca_col1:
        st.markdown("#### ❌ Vanilla BARO (Unguarded + Forward Fill)")
        v_hit_badge = "✅ Hit @ 1" if v_rca["hit_at_1"] else ("⚠️ Hit @ 3" if v_rca["hit_at_3"] else "❌ Missed (> Top 3)")
        st.markdown(f"**Outcome:** {v_hit_badge} | Reciprocal Rank: `{v_rca['reciprocal_rank']:.3f}`")
        v_df = pd.DataFrame({
            "Rank": list(range(1, 6)),
            "Service": v_rca["ranked_services"][:5],
            "Score": v_rca["scores"][:5],
            "Is Ground Truth": [s == target_case.root_cause_service for s in v_rca["ranked_services"][:5]],
        })
        st.dataframe(v_df, use_container_width=True)

    with rca_col2:
        st.markdown("#### 🛡️ Constrained-xAIOps (Trust-Weighted + MNAR Prior)")
        tw_hit_badge = "✅ Hit @ 1" if tw_rca["hit_at_1"] else ("⚠️ Hit @ 3" if tw_rca["hit_at_3"] else "❌ Missed (> Top 3)")
        st.markdown(f"**Outcome:** {tw_hit_badge} | Reciprocal Rank: `{tw_rca['reciprocal_rank']:.3f}`")
        tw_df = pd.DataFrame({
            "Rank": list(range(1, 6)),
            "Service": tw_rca["ranked_services"][:5],
            "Score": tw_rca["scores"][:5],
            "Is Ground Truth": [s == target_case.root_cause_service for s in tw_rca["ranked_services"][:5]],
        })
        st.dataframe(tw_df, use_container_width=True)

    # TreeSHAP Explainability & Explanation Reliability Badge
    st.subheader("4. Missingness-Aware TreeSHAP Attribution & Explanation Reliability Badge")
    expl = sim_res["explanation"]
    if expl and "metric_attributions" in expl:
        e_col1, e_col2 = st.columns([1.5, 2.5])

        with e_col1:
            r_exp = expl.get("reliability_score", 1.0)
            low_warn = expl.get("low_reliability_warning", False)
            st.metric("Explanation Reliability Badge ($R_{\text{exp}}$)", f"{r_exp:.3f}")
            if low_warn:
                st.warning("⚠️ **Low Reliability Warning:** >30% attribution uncertainty due to high missingness/imputation on top metrics!")
            else:
                st.success("🛡️ **High Attribution Certainty:** Attributions grounded in reliable observed telemetry points.")

            st.write(f"**Target Service:** `{expl.get('service')}`")
            st.write(f"**Gini Sparsity Index:** `{expl.get('gini_sparsity', 0.0):.3f}`")

        with e_col2:
            attr_dict = expl.get("metric_attributions", {})
            if attr_dict:
                top_items = sorted(attr_dict.items(), key=lambda x: x[1], reverse=True)[:8]
                m_names = [k for k, _ in top_items]
                m_vals = [v * 100 for _, v in top_items]

                fig, ax = plt.subplots(figsize=(7, 3.2), dpi=150)
                y_pos = np.arange(len(m_names))
                ax.barh(y_pos, m_vals, color="#3B82F6")
                ax.set_yticks(y_pos)
                ax.set_yticklabels([n.split("_")[-1] if len(n) > 20 else n for n in m_names], fontsize=8)
                ax.invert_yaxis()
                ax.set_xlabel("Attribution Weight (%)")
                ax.set_title(f"TreeSHAP Attribution for {expl.get('service')}")
                st.pyplot(fig)
                plt.close()

    # Operator Triage Feedback
    st.subheader("5. Human-in-the-Loop Operator Feedback Triage")
    st.markdown("Submit triage verdicts to dynamically recalibrate conformal thresholds online using Robbins-Monro stochastic approximation:")

    fb_col1, fb_col2, fb_col3 = st.columns(3)
    top_candidate = tw_rca["ranked_services"][0]

    with fb_col1:
        if st.button("✅ Confirm RCA (True Positive)", use_container_width=True):
            fb_res = engines.feedback_store.add_feedback(
                case_id=case_id,
                service=top_candidate,
                verdict="CONFIRM_RCA",
                trust_score=decisions[top_candidate]["trust_score"],
                anomaly_score=decisions[top_candidate]["anomaly_score"],
            )
            st.success("Triage confirmed: Correct RCA localization reinforced.")

    with fb_col2:
        if st.button("⚠️ False Positive (Spurious Alert)", use_container_width=True):
            new_s = engines.recalibrator.step(
                verdict="FALSE_POSITIVE",
                trust_score=decisions[top_candidate]["trust_score"],
                anomaly_score=decisions[top_candidate]["anomaly_score"],
            )
            engines.feedback_store.add_feedback(
                case_id=case_id,
                service=top_candidate,
                verdict="FALSE_POSITIVE",
                trust_score=decisions[top_candidate]["trust_score"],
                anomaly_score=decisions[top_candidate]["anomaly_score"],
            )
            st.warning(f"False alarm logged. Conformal trust threshold raised to $\\tau_T = {new_s['tau_T']:.3f}$.")

    with fb_col3:
        if st.button("🚨 Confirm Silent Crash (MNAR Blackout)", use_container_width=True):
            new_s = engines.recalibrator.step(
                verdict="CONFIRM_MNAR_CRASH",
                trust_score=decisions[top_candidate]["trust_score"],
                anomaly_score=decisions[top_candidate]["anomaly_score"],
            )
            engines.feedback_store.add_feedback(
                case_id=case_id,
                service=top_candidate,
                verdict="CONFIRM_MNAR_CRASH",
                trust_score=decisions[top_candidate]["trust_score"],
                anomaly_score=decisions[top_candidate]["anomaly_score"],
            )
            st.info(f"MNAR blackout verified. Blackout prior boosted to $\\lambda = {new_s['lambda_mnar']:.2f}$.")


# TAB 2: 375-Case Multi-System & Security Benchmark
elif selected_tab == "375-Case Multi-System & Security Benchmark":
    st.markdown('<div class="main-header">🌐 375-Case Multi-System, Zero-Shot & Security Benchmark</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Evaluated across all 375 failure cases of RCAEval RE1: Online Boutique (10 svcs), Sock Shop (13 svcs), and Train Ticket (40 svcs).</div>', unsafe_allow_html=True)

    p6_file = Path("artifacts/metrics/phase6_multisystem_and_security.json")
    if p6_file.exists():
        with open(p6_file, "r", encoding="utf-8") as f:
            p6_data = json.load(f)

        st.subheader("Panel A: 375-Case Multi-System Benchmark (Clean vs. 40% MNAR)")
        sys_choice = st.selectbox("Select Target System", ["OnlineBoutique", "SockShop", "TrainTicket"])
        exp_a = p6_data["experiment_a_multisystem"][sys_choice]

        models = [
            ("vanilla_baro", "Vanilla BARO"),
            ("epsilon_diagnosis", "e-Diagnosis"),
            ("circa", "CIRCA (KDD '22)"),
            ("rcd", "RCD (NeurIPS '22)"),
            ("passive_conformal", "Passive Conformal"),
            ("constrained_xaiops", "Constrained-xAIOps (Ours)"),
        ]

        pA_rows = []
        base_v_ac3 = exp_a["MNAR_40"]["vanilla_baro"]["AC@3"]["mean"] * 100.0
        for m_key, m_name in models:
            c_entry = exp_a["Clean"][m_key]
            m_entry = exp_a["MNAR_40"][m_key]
            m_ac3 = m_entry["AC@3"]["mean"] * 100.0
            adv = f"{m_ac3 - base_v_ac3:+.1f}%" if m_key != "vanilla_baro" else "---"
            pA_rows.append({
                "Model / Baseline": m_name,
                "Clean AC@1": f"{c_entry['AC@1']['mean']*100:.1f}%",
                "Clean AC@3": f"{c_entry['AC@3']['mean']*100:.1f}%",
                "Clean MRR": f"{c_entry['MRR']['mean']:.3f}",
                "40% MNAR AC@1": f"{m_entry['AC@1']['mean']*100:.1f}%",
                "40% MNAR AC@3": f"{m_entry['AC@3']['mean']*100:.1f}%",
                "40% MNAR MRR": f"{m_entry['MRR']['mean']:.3f}",
                "Coverage": f"{m_entry['Coverage']['mean']*100:.1f}%",
                "Lift@5": f"{m_entry.get('Lift@5', {}).get('mean', 0.0):+.3f}",
                "Accuracy Advantage": adv,
            })
        st.dataframe(pd.DataFrame(pA_rows), use_container_width=True)

        st.markdown("---")
        col_b, col_c = st.columns(2)

        with col_b:
            st.subheader("Panel B: Zero-Shot Cross-System Transfer")
            st.markdown("Model trained *strictly on Online Boutique*, evaluated on unseen architectures with zero retraining.")
            exp_b = p6_data["experiment_b_zeroshot_transfer"]["targets"]
            pB_rows = []
            for tgt, t_data in exp_b.items():
                pB_rows.append({
                    "Target Architecture": tgt,
                    "Cases": t_data["num_test_cases"],
                    "In-Domain AC@3": f"{t_data['in_domain']['AC@3_mean']*100:.1f}%",
                    "Zero-Shot AC@3": f"{t_data['zero_shot']['AC@3_mean']*100:.1f}%",
                    "Generalization Gap": f"{t_data['generalization_gap_AC@3']*100:+.1f}%",
                    "Retention Rate": f"{t_data['retention_percentage']:.1f}%",
                })
            st.dataframe(pd.DataFrame(pB_rows), use_container_width=True)

        with col_c:
            st.subheader("Panel C: Telemetry Threat Defense")
            st.markdown("Detection and resilience against exporter stale-freeze and adversarial spoofing.")
            exp_c = p6_data["experiment_c_security_defense"]
            stale = exp_c["stale_freeze_defense"]
            spoof = exp_c["adversarial_spoofing_defense"]
            pC_rows = [
                {
                    "Threat Scenario": "Exporter Stale-Freeze",
                    "Detection Rate": f"{stale['detection_rate']*100:.1f}%",
                    "Degradation Symptom": f"Timeliness L = {stale['mean_timeliness_L']:.3f}",
                    "Vanilla BARO AC@3": f"{stale['vanilla_baro_AC@3']*100:.1f}%",
                    "Constrained AC@3": f"{stale['constrained_xaiops_AC@3']*100:.1f}%",
                    "Advantage": f"{stale['accuracy_advantage']*100:+.1f}%",
                },
                {
                    "Threat Scenario": "Adversarial Spoofing",
                    "Detection Rate": f"{spoof['detection_rate']*100:.1f}%",
                    "Degradation Symptom": f"S = {spoof['mean_consistency_S']:.3f}, V = {spoof['mean_validity_V']:.3f}",
                    "Vanilla BARO AC@3": f"{spoof['vanilla_baro_AC@3']*100:.1f}%",
                    "Constrained AC@3": f"{spoof['constrained_xaiops_AC@3']*100:.1f}%",
                    "Advantage": f"{spoof['accuracy_advantage']*100:+.1f}%",
                },
            ]
            st.dataframe(pd.DataFrame(pC_rows), use_container_width=True)

        st.markdown("---")
        fig5_path = Path("artifacts/figures/fig5_multisystem_and_security.png")
        if fig5_path.exists():
            st.subheader("Figure 5: Multi-System Benchmark, Transfer & Security Overview")
            st.image(str(fig5_path), use_container_width=True)
    else:
        st.warning("phase6_multisystem_and_security.json not found on disk.")


# TAB 3: Multi-Seed Benchmark Explorer
elif selected_tab == "Multi-Seed Benchmark Explorer":
    st.markdown('<div class="main-header">📊 Multi-Seed Scientific Benchmark Explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Evaluated across 5 random seeds (42, 1024, 2025, 2026, 7777) on all 125 RCAEval cases.</div>', unsafe_allow_html=True)

    summary_file = Path("artifacts/metrics/statistical_summary.json")
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            summary = json.load(f)

        grid = summary["main_missingness_grid"]
        mech_choice = st.selectbox("Select Mechanism", ["MNAR", "MAR", "MCAR"])

        table_rows = []
        for r_str in ["0.0", "0.1", "0.2", "0.4", "0.6", "0.8"]:
            entry = grid[mech_choice][r_str]
            table_rows.append({
                "Missingness Rate": f"{int(float(r_str)*100)}%",
                "Vanilla AC@1": f"{entry['vanilla_baro']['AC@1_mean']*100:.1f}% ± {entry['vanilla_baro']['AC@1_std']*100:.1f}%",
                "Vanilla AC@3": f"{entry['vanilla_baro']['AC@3_mean']*100:.1f}% ± {entry['vanilla_baro']['AC@3_std']*100:.1f}%",
                "Constrained AC@1": f"{entry['constrained_xaiops']['AC@1_mean']*100:.1f}% ± {entry['constrained_xaiops']['AC@1_std']*100:.1f}%",
                "Constrained AC@3": f"{entry['constrained_xaiops']['AC@3_mean']*100:.1f}% ± {entry['constrained_xaiops']['AC@3_std']*100:.1f}%",
                "AURC": f"{entry['constrained_xaiops']['aurc_mean']:.3f}",
                "VUS-PR": f"{entry['constrained_xaiops']['vus_pr_mean']:.3f}",
            })

        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

        st.subheader("Statistical Tests Summary")
        stats = summary["statistical_tests"]["pairwise_comparisons"]
        st.json(stats)
    else:
        st.warning("statistical_summary.json not found on disk.")


# TAB 4: Paper Evidence Gallery
elif selected_tab == "Paper Evidence Gallery":
    st.markdown('<div class="main-header">📄 Publication-Quality Figures & LaTeX Tables</div>', unsafe_allow_html=True)

    fig_dir = Path("artifacts/figures")
    figures = [
        ("Figure 1: Telemetry Degradation Curves (MCAR, MAR, MNAR)", "fig1_degradation_curves.png"),
        ("Figure 2: Selective Risk vs. Coverage (AURC)", "fig2_risk_coverage_aurc.png"),
        ("Figure 3: Missingness-Aware TreeSHAP Attribution & Fidelity", "fig3_shap_fidelity_and_ablations.png"),
        ("Figure 4: Label Scarcity Curve & Causal Imputer Comparison", "fig4_label_scarcity_and_imputers.png"),
        ("Figure 5: Multi-System Benchmark, Zero-Shot Generalization & Security", "fig5_multisystem_and_security.png"),
    ]

    for title, fname in figures:
        p = fig_dir / fname
        if p.exists():
            st.markdown(f"### {title}")
            st.image(str(p), use_container_width=True)
            st.markdown("---")


# TAB 4: Hardware & Live Concurrency
elif selected_tab == "Hardware & Live Concurrency":
    st.markdown('<div class="main-header">⚡ Hardware Capacity & Concurrency Monitor</div>', unsafe_allow_html=True)

    c_col1, c_col2, c_col3 = st.columns(3)
    c_col1.metric("Available CPU Cores", os.cpu_count())
    c_col2.metric("Concurrency Workers", MAX_WORKERS)
    c_col3.metric("RAM Capacity", f"{vm.total / (1024**3):.1f} GB")

    st.subheader("CPU Utilization across Cores")
    cpu_percents = psutil.cpu_percent(percpu=True)
    cpu_df = pd.DataFrame({
        f"Core {i}": [p] for i, p in enumerate(cpu_percents)
    })
    st.bar_chart(cpu_df.T)
