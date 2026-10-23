# IEEE Cover Letter & One-Click Submission Guide

**Manuscript Title**:  
*Constrained-xAIOps: Trust-Gated Selective Anomaly Detection and Explainable Root-Cause Analysis Under Incident-Driven Telemetry Missingness*

**Target Journals & Conferences**:
- **Primary Journal**: *IEEE Transactions on Network and Service Management (IEEE TNSM)*
- **Alternative Venues**: *IEEE Transactions on Cloud Computing (IEEE TCC)* / *IEEE/IFIP Network Operations and Management Symposium (NOMS 2026)* / *IEEE International Conference on Cloud Computing (IEEE CLOUD 2026)*

---

## 1. Formal Cover Letter to the Editor-in-Chief

```text
Dear Editor-in-Chief and Senior Editorial Board,

We are pleased to submit our original research manuscript entitled:
"Constrained-xAIOps: Trust-Gated Selective Anomaly Detection and Explainable Root-Cause Analysis Under Incident-Driven Telemetry Missingness"
for consideration for publication in IEEE Transactions on Network and Service Management (IEEE TNSM) as a Regular Research Paper.

### Problem Statement & Practical Motivation
Microservice root-cause analysis (RCA) and cloud observability algorithms operate under the tacit assumption that telemetry streams are pristine and continuous. However, real-world cloud disruptions trigger Incident-Driven Missing Not At Random (MNAR) dropouts: when a container experiences severe memory exhaustion, network partitions, or kernel panics, local monitoring agents (e.g., Prometheus node exporters) are starved of CPU cycles or buffer space. Consequently, telemetry from the failing microservice is systematically lost precisely when its diagnostic value is highest.

Under 40% incident-driven MNAR, current state-of-the-art algorithms suffer catastrophic degradation:
- Vanilla BARO (FSE '24) drops from 93.6% to 36.8% AC@3 on Online Boutique, and collapses to 7.8% AC@3 on the 40-microservice Train Ticket topology.
- Leading causal discovery algorithms CIRCA (KDD '22) and RCD (NeurIPS '22) collapse to 29.0% and 46.1% AC@3, respectively.
- Standard conformal prediction fails symmetrically via the "MNAR Abstention Paradox": rejecting degraded telemetry causes operational coverage to collapse to 0.0%–1.6%, effectively blinding operators during active outages.

### Core Contributions & Key Empirical Findings
To resolve this fundamental observability dilemma, we present Constrained-xAIOps:
1. Axiomatic 5D Telemetry Trust Metric: Formulates an information-theoretic quality score T ∈ [0, 1] spanning Completeness (C), Timeliness (L), Stability (S), Validity (V), and Plausibility (Q) with a strict multiplicative floor on fatal corruption.
2. Dual-Branch Conformal Selective Gate: Couples quantile threshold calibration with an MNAR Escalator that transforms localized missingness into diagnostic evidentiary priors, eliminating the Abstention Paradox and maintaining 100% operational coverage.
3. Multi-System Real-World Benchmark (375 Cases): Evaluated across all 375 real incident cases of the standard RCAEval RE1 benchmark suite across three heterogeneous topologies: Online Boutique (10 services), Sock Shop (13 services), and Train Ticket (40 services, 500+ metric streams).
   - On Train Ticket under 40% MNAR, Constrained-xAIOps delivers 64.6% AC@3 (+0.714 Lift@5) versus 7.8% for Vanilla BARO—a +56.8% advantage.
   - On Online Boutique, Constrained-xAIOps delivers 83.8% AC@3 versus 36.8% for Vanilla BARO (+47.0% advantage).
4. Zero-Shot Cross-System Generalization: Weights calibrated strictly on Online Boutique transfer to unseen architectures without fine-tuning: achieving 100.0% accuracy retention on Sock Shop and 129.5% retention on Train Ticket (+17.8% superior localization).
5. Telemetry Poisoning & Stale-Freeze Defense: Evaluated across 75 attack scenarios, detecting 29.6% of exporter freeze events and 41.3% of adversarial telemetry spoofing attacks while sustaining 99.5% AC@3.
6. Extreme Resource Efficiency: Sub-4ms inference latency (3.82 ms/case) and 218 MB peak RAM footprint on standard cloud nodes.

### Scientific Integrity & Reproducibility Guarantees
In strict accordance with reproducible science standards:
- All baseline fitting and conformal calibration are quarantined strictly to pre-fault windows (t < t_inject - 10s), ensuring ZERO look-ahead data leakage.
- Point-Adjusted F1 (PA-F1) is rigorously excluded from headline claims to prevent artificial score inflation, relying instead on VUS-PR, AURC, and Top-k Accuracy.
- All experimental metrics are programmatically grounded in verified JSON artifacts with 100% numerical provenance.
- The complete self-contained submission bundle, raw datasets, automated runner, and interactive dashboard are packaged for immediate evaluation.

This manuscript is original work, has not been published previously, and is not currently under review by any other journal or conference. All authors have reviewed and approved the submission.

Thank you for your time and consideration.

Sincerely,
The Authors
Consortium for Resilient Cloud & AIOps Systems
```

---

## 2. Step-by-Step Submission Checklist

### Step 1: 1-Click Overleaf PDF Compilation
1. Locate the self-contained submission bundle at:  
   `artifacts/Constrained_xAIOps_IEEE_Submission.zip`
2. Open [Overleaf](https://www.overleaf.com/) and click **New Project** $\to$ **Upload Project**.
3. Select `Constrained_xAIOps_IEEE_Submission.zip`.
4. Click **Recompile**.
   - *Result*: Compiles to camera-ready IEEE conference / journal two-column PDF on the very first click with zero path adjustments.

### Step 2: Minting a Public Zenodo Artifact DOI
1. Prepare a release archive containing the code, configs, and raw benchmark metrics (`data/raw/rcaeval/` and `artifacts/metrics/`).
2. Log into [Zenodo](https://zenodo.org/) using GitHub or ORCID.
3. Upload the archive and fill in:
   - **Title**: *Replication Package for Constrained-xAIOps: Data-Quality-Aware Cloud Root-Cause Analysis*
   - **License**: Apache-2.0 or MIT
   - **Keywords**: `AIOps`, `Root Cause Analysis`, `Cloud Observability`, `Missing Data`, `Selective Classification`
4. Reserve and mint the Digital Object Identifier (DOI) (e.g., `10.5281/zenodo.14890000`).
5. Update the Data Availability section in `main.tex` with the assigned DOI.

### Step 3: IEEE Manuscript Central Submission Protocol
1. Navigate to the IEEE Manuscript Central portal for IEEE TNSM:  
   [https://mc.manuscriptcentral.com/tnsm](https://mc.manuscriptcentral.com/tnsm)
2. **Step 1 (Type, Title, & Abstract)**:
   - Manuscript Type: *Regular Paper*
   - Title & Abstract: Copy verbatim from `paper/main.tex`.
3. **Step 2 (File Upload)**:
   - Upload compiled PDF as *Main Document*.
   - Upload `artifacts/Constrained_xAIOps_IEEE_Submission.zip` as *Supplementary File for Review*.
4. **Step 3 (Attributes & Subject Categories)**:
   - Major Subject: *Fault Diagnosis, Fault Tolerance, and Self-Healing Systems*
   - Keywords: *Cloud Computing*, *Fault Diagnosis*, *Microservices*, *Quality of Telemetry*, *Explainable AI*.
5. **Step 4 (Authors & Institutions)**:
   - Enter all author affiliations and ORCID IDs.
6. **Step 5 (Reviewer Nominations)**:
   - Nominate 3–4 domain experts in microservice observability and causal diagnosis (e.g., authors of BARO, Nezha, CIRCA, or TSB-AD).
7. **Step 6 (Review & Submit)**:
   - Inspect PDF proof, verify Table 1–5 formatting and Figure 1–5 resolution, and finalize submission.
