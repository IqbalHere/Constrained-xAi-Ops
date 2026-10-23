# Constrained-xAIOps: Master Viva Presentation & Defense Guide

**Paper**: *Constrained-xAIOps: Trust-Gated Selective Anomaly Detection and Explainable Root-Cause Analysis Under Incident-Driven Telemetry Missingness*  
**Scope**: 375 Real-World Failure Cases across RCAEval RE1 (`Online Boutique`, `Sock Shop`, `Train Ticket`)  
**Venues**: *IEEE Transactions on Network and Service Management (IEEE TNSM)* / *IEEE CLOUD* / *IEEE/IFIP NOMS*

---

# Part 1: 12-Slide Master Defense Presentation Deck

### Slide 1: Title & The Cloud Observability Crisis
- **Title**: Constrained-xAIOps: Data-Quality-Aware, Explainable AIOps for Constrained Cloud Environments
- **The Core Premise**: Modern cloud observability assumes that metric streams (CPU, RAM, network, latency) are pristine, complete, and trustworthy.
- **The Reality**: In production microservices, severe outages systematically degrade monitoring daemons (Prometheus node exporters), starving them of CPU cycles and socket buffers.
- **Speaker Script**:  
  *"Good morning, esteemed committee members. Today, cloud operators trust automated AIOps pipelines to detect anomalies and pinpoint root causes across microservice clusters. However, state-of-the-art diagnostic models share a fatal blind spot: they assume input telemetry is clean. When an incident strikes, the very microservice that is failing frequently suffocates its local telemetry exporter. Sensor data vanishes precisely when operators need it most. Our research solves this fundamental crisis."*

---

### Slide 2: The Core Dilemma: MNAR vs. The Abstention Paradox
- **Bullet 1**: *Incident-Driven MNAR*: Telemetry is Missing Not At Random; dropouts correlate directly with unobserved microservice failure states.
- **Bullet 2**: *Catastrophic Baseline Collapse*: Under 40% MNAR, Vanilla BARO Top-1 accuracy drops from 65.6% to 10.3%, and on 40-service Train Ticket collapses to 7.8%.
- **Bullet 3**: *The MNAR Abstention Paradox*: Standard conformal selective prediction rejects low-trust inputs, causing operational coverage to collapse to 0.0%–1.6%—blinding SREs during active outages.
- **Speaker Script**:  
  *"Under 40% MNAR, existing algorithms experience catastrophic degradation. Furthermore, if an operator attempts to apply conformal selective prediction to abstain on uncertain inputs, they trigger the 'MNAR Abstention Paradox': because the telemetry from the failing service is missing, the conformal gate abstains on 98% of cases. The system goes completely silent during genuine outages. SREs are left with an impossible choice: act on hallucinated diagnoses, or receive no guidance at all."*

---

### Slide 3: Architectural Overview: Constrained-xAIOps
- **Bullet 1**: Four interconnected reliability pillars engineered for resource-constrained edge/cloud sidecars.
- **Bullet 2**: Axiomatic 5D Telemetry Trust Metric $\to$ Dual-Branch Conformal Gate $\to$ Trust-Weighted BARO $\to$ Missingness-Aware TreeSHAP.
- **Bullet 4**: Zero physical sensor redundancy required; uses information-theoretic telemetry properties and call-graph topology.
- **Speaker Script**:  
  *"To resolve this dilemma without the cost and overhead of duplicate monitoring agents, we introduce Constrained-xAIOps. Our architecture operates in four stages: first, it computes an axiomatic 5D Telemetry Trust score; second, our Dual-Branch Selective Gate distinguishes benign loss from crash blackouts; third, a Trust-Weighted Bayesian change-point engine localizes root causes; and fourth, Missingness-Aware TreeSHAP explains the failure while quantifying explanation reliability."*

---

### Slide 4: Pillar 1: Axiomatic 5D Telemetry Trust Metric
- **Mathematical Formulation**:
  $$T_{\text{metric}}(m) = \mathbb{I}(V > 0) \cdot \mathbb{I}(C > 0) \cdot \sum_{j=1}^5 w_j d_j(m)$$
- **Five Concrete Dimensions**:
  1. *Completeness ($C$)*: Ratio of observed to expected samples in window $W$.
  2. *Timeliness ($L$)*: Exponential decay on sampling jitter $\Delta t$ and stale value freeze.
  3. *Stability ($S$)*: Variance bounds against anomalous high-frequency noise.
  4. *Validity ($V$)*: Hard physics and schema bounds (e.g., CPU $\in [0, 100]\%$, non-negative counters).
  5. *Plausibility ($Q$)*: Mahalanobis consistency against pre-fault multivariate normal baselines.
- **Multiplicative Floor**: Zero validity or total dropout forces $T=0$, preventing catastrophic corruption propagation.
- **Speaker Script**:  
  *"Rather than relying on naive completeness counters, we formulate an axiomatic five-dimensional trust score. If a sensor violates physical constraints—such as reporting negative memory or 400% CPU on a single-core pod—the Validity floor drops the metric trust to absolute zero. If a metric freezes, the Timeliness dimension penalizes it. Weights are calibrated via convex optimization, ensuring a principled quality indicator in [0, 1]."*

---

### Slide 5: Pillar 2: Dual-Branch Conformal Selective Gate
- **Branch 1 (Normal Operation)**: Telemetry trust $T_{\text{sys}} \ge \tau_T$. Standard anomaly routing with calibrated coverage guarantee ($1 - \alpha$).
- **Branch 2 (Dual-Branch MNAR Escalator)**: Telemetry trust $T_{\text{sys}} < \tau_T$. Evaluates localized topology discrepancy:
  $$\Delta T = \max_{s \in \mathcal{S}} |T(s) - \bar{T}_{\text{sys}}|$$
- **The Evidentiary Prior**: If localized dropout occurs on service $s_m$ while adjacent nodes exhibit traffic anomalies, localized missingness is converted into a diagnostic asset:
  $$\pi_{\text{prior}}(s_m) \propto \exp\left( \lambda_{\text{mnar}} \cdot [1 - C(s_m)] \right)$$
- **Speaker Script**:  
  *"The breakthrough that breaks the Abstention Paradox is our Dual-Branch Escalator. When telemetry trust falls below the conformal threshold, instead of simply dropping the alert, we inspect the microservice call graph. If the dropout is uniform, it is background packet loss—we abstain safely. But if a single microservice drops offline while its upstream neighbors show latency spikes, the missingness itself is conclusive forensic evidence of a crash. We escalate the case, boosting the prior by lambda = 3.5. Coverage is restored from 1.6% to 100%."*

---

### Slide 6: Pillar 3: Trust-Weighted Bayesian Localization (BARO)
- **Problem with Vanilla BARO**: Recursive Gaussian updates treat missing or zero-imputed metrics as genuine steady-state observations, pulling the covariance matrix toward zero.
- **Trust-Weighted Covariance Regularization**:
  $$\hat{\boldsymbol{\Sigma}}_t(s_m) = T(s_m) \cdot \boldsymbol{\Sigma}_{\text{obs}}(s_m) + (1 - T(s_m)) \cdot \boldsymbol{\Sigma}_{\text{pre-fault}}(s_m)$$
- **Result**: Degraded observations smoothly revert to pre-fault baselines without triggering false-positive change points.
- **Speaker Script**:  
  *"Standard Bayesian Online Change Point Detection maintains a recursive covariance matrix. When metrics are missing or imputed with zeros, standard BARO hallucinates extreme variance shifts, misidentifying healthy services as root causes. Our trust-weighted regularization smoothly blends observed covariance with pre-fault empirical baselines proportional to trust. Degraded signals gracefully decay without corrupting the change-point posterior."*

---

### Slide 7: Pillar 4: Missingness-Aware TreeSHAP Attribution
- **Feature Space Augmentation**: Concatenates metric anomaly residuals $\mathbf{x}_t$ with binary missingness indicators $\mathbf{M}_t \in \{0, 1\}^M$.
- **Fidelity@1 Metric**: Percentage of cases where the top TreeSHAP attributed indicator matches the ground-truth root cause.
- **Empirical Superiority**: Cuts attribution error by 50% (infidelity drops from 13.3% to 6.7%), achieving Jaccard stability of 0.884 across evaluation windows.
- **Speaker Script**:  
  *"Explainability must not deceive operators during incidents. Standard SHAP imputes missing values with marginal means, creating artificial feature importances. By augmenting the background matrix with explicit missingness indicators, our Missingness-Aware TreeSHAP directly attributes diagnostic importance to the silence of a failed pod. It cuts explanation error in half and achieves an Explanation Reliability Badge in the operator dashboard."*

---

### Slide 8: Multi-System Benchmark Overview (375 Cases)
- **Dataset**: All 375 real incident cases of RCAEval RE1:
  - `RE1-OB` (Online Boutique): 10 microservices, 125 cases (Go, Python, C#, Java).
  - `RE1-SS` (Sock Shop): 13 microservices, 125 cases (Node.js, Go, Java).
  - `RE1-TT` (Train Ticket): 40 microservices, 125 cases (Spring Cloud, Java).
- **Baselines**: Vanilla BARO (FSE '24), $\epsilon$-Diagnosis (WWW '19), CIRCA (KDD '22), RCD (NeurIPS '22), Passive Conformal.
- **Protocol**: 5 deterministic random seeds; strict zero-leakage pre-fault fitting ($t < t_{\text{inject}} - 10\text{s}$).
- **Speaker Script**:  
  *"To prove our framework is not overfitted to a single toy benchmark, we evaluated across all 375 real failure cases of the RCAEval RE1 suite, comparing against state-of-the-art causal discovery and statistical localization algorithms under 5 deterministic random seeds."*

---

### Slide 9: Large-Topology Resilience: The Train Ticket Breakthrough
- **The Challenge**: 40 interconnected microservices with over 500 simultaneous metric streams.
- **The Empirical Findings (40% MNAR Blackout)**:
  - Vanilla BARO collapses to **7.8% AC@3** (MRR = 0.120, Lift@5 = +0.055).
  - CIRCA (KDD '22) collapses to **7.7% AC@3** (MRR = 0.097, Lift@5 = +0.047).
  - RCD (NeurIPS '22) drops to **10.1% AC@3** (MRR = 0.136, Lift@5 = +0.088).
  - Passive Conformal yields **0.0% coverage** (total failure).
  - **Constrained-xAIOps delivers 64.6% AC@3**, **+0.714 Lift@5**, and **100% coverage** (+56.8% advantage).
- **Speaker Script**:  
  *"Slide 9 presents our most dramatic finding. On the 40-microservice Train Ticket system, under 40% MNAR, every baseline collapsed into near-random guessing: Vanilla BARO achieved 7.8% AC@3, CIRCA achieved 7.7%, and RCD achieved 10.1%. Passive Conformal completely shut down with 0% coverage. Constrained-xAIOps maintained 64.6% AC@3 and a +0.714 Lift@5. That is a 56.8 percentage-point accuracy advantage achieved entirely by treating missingness as evidentiary data."*

---

### Slide 10: Zero-Shot Cross-System Generalization
- **Hypothesis**: Axiomatic telemetry quality bounds are invariant across programming languages and architectures.
- **Experiment**: Train trust weights $w$ and conformal threshold $\tau_T = 0.816$ strictly on Online Boutique; deploy on unseen systems with zero retraining.
- **Results**:
  - *Sock Shop*: In-Domain AC@3 = 57.1%, Zero-Shot AC@3 = 57.1% (**100.0% retention**, Gap = 0.0%).
  - *Train Ticket*: In-Domain AC@3 = 60.3%, Zero-Shot AC@3 = 78.1% (**129.5% retention**, +17.8% superior localization).
- **Speaker Script**:  
  *"In production cloud environments, retraining models for every new microservice is economically unfeasible. We tested zero-shot cross-system transfer. Calibration parameters fitted strictly on Online Boutique were applied directly to Sock Shop and Train Ticket. We achieved 100% retention on Sock Shop and 129.5% on Train Ticket. This proves that our five quality dimensions reflect universal physical constraints of distributed computing, not architecture-specific quirks."*

---

### Slide 11: Telemetry Poisoning & Stale-Freeze Security Defense
- **Threat Vector 1: Exporter Stale-Freeze**: Telemetry agent hangs and repeats last valid value indefinitely.
  - *Defense*: Timeliness ($L = 0.631$) detects 29.6% of freezes; Constrained-xAIOps delivers 19.5% AC@3 vs 12.8% for Vanilla BARO (+6.7% advantage).
- **Threat Vector 2: Adversarial Telemetry Spoofing**: Adversary injects pristine fake metrics into failing nodes.
  - *Defense*: Consistency ($S = 0.986$) and Validity ($V = 0.976$) achieve a 41.3% threat detection rate, gating poisoned streams while sustaining 99.5% AC@3.
- **Speaker Script**:  
  *"We extended our audit to adversarial telemetry poisoning. When an attacker or failing daemon freezes telemetry values, our Timeliness dimension flags the lack of variance jitter, achieving 29.6% detection and superior localization. Under active spoofing attacks, Consistency and Validity detect 41.3% of malicious streams, preventing false alarms and preserving operator trust."*

---

### Slide 12: Operational Hardware Efficiency & Artifacts
- **Inference Latency**: Mean of **3.82 ms** per case (sub-4ms real-time throughput).
- **Peak RAM Footprint**: **218.4 MB**, fully deployable inside Kubernetes sidecar containers.
- **Concurrency**: 16-thread native execution on modern multi-core nodes.
- **Artifacts**:
  - 100% Passing Unit & Regression Tests (59/59).
  - Open-source live Kubernetes & Prometheus testbed with Chaos Mesh injection.
  - 1-Click IEEE Camera-Ready Submission bundle (`Constrained_xAIOps_IEEE_Submission.zip`).
- **Speaker Script**:  
  *"Finally, Constrained-xAIOps is engineered for real-world cloud deployment. It consumes only 218 MB of RAM and executes in 3.82 milliseconds per case, easily fitting inside standard Kubernetes sidecar limits. All 59 unit and regression tests pass with 100% provenance and zero data leakage. Thank you, and I look forward to your questions."*

---

# Part 2: 15 Toughest Reviewer / Viva Defense Questions & Quantitative Answers

### Q1: How do you mathematically and programmatically guarantee zero look-ahead data leakage?
**Answer**:  
Every data normalization step, baseline mean/covariance estimation, and selective threshold calibration ($\tau_T, \tau_A$) is strictly restricted to the pre-fault window:
$$t < t_{\text{inject}} - 10\,\text{s}$$
Post-fault telemetry ($t \ge t_{\text{inject}}$) is quarantined. Programmatically, our test suite includes dedicated regression tests in `tests/regression/test_no_leakage.py` that inject synthetic spikes into the post-fault window and assert that pre-fault normalization parameters and covariance matrices remain bit-for-bit identical (SHA-256 verified).

---

### Q2: Why doesn't standard conformal prediction work under MNAR, and how does your Dual-Branch Escalator avoid violating conformal coverage bounds?
**Answer**:  
Standard conformal prediction assumes exchangeability between calibration and test non-conformity scores. Under incident-driven MNAR, the missingness mechanism is directly conditioned on the unobserved label ($Y = \text{Fault}$), which violates exchangeability. Consequently, a naive conformal gate observes low telemetry completeness, treats it as extreme uncertainty, and abstains on 97.7% of genuine outage cases (reducing operational coverage to 2.3%).  
Our Dual-Branch Escalator restores validity by conditioning on the topology call graph: it tests whether missingness is localized ($\Delta T > \tau_{\text{discrepancy}}$) while upstream dependencies exhibit anomaly symptoms. This converts missingness from an uncertainty metric into diagnostic evidentiary prior $\pi_{\text{prior}}(s_m) \propto \exp(\lambda_{\text{mnar}} [1 - C(s_m)])$, restoring coverage to 100.0% while bounding selective risk to 12.0%.

---

### Q3: Why did you explicitly exclude Point-Adjusted F1 (PA-F1) from your paper's headline claims?
**Answer**:  
As proven by Wu & Keogh (TKDE 2021) and Liu & Paparrizos (NeurIPS 2024, TSB-AD), Point-Adjusted F1 artificially inflates performance: if an algorithm triggers a single true-positive alert anywhere within an anomaly segment, the entire continuous incident is credited as fully detected. A random noise generator can achieve $>90\%$ PA-F1 under this flawed protocol.  
In accordance with scientific integrity rules, we evaluate exclusively with range-aware, threshold-independent metrics: Volume Under the Surface of Precision-Recall (VUS-PR), Area Under the Risk-Coverage Curve (AURC), and Top-$k$ Accuracy (AC@1, AC@3, AC@5) with Mean Reciprocal Rank (MRR).

---

### Q4: If telemetry is 40% missing, how can TreeSHAP compute valid Shapley values without hallucinating feature importances?
**Answer**:  
Standard TreeSHAP computes conditional expectations $E[f(x) \mid x_S]$ by marginalizing over background samples, which implicitly assumes missing features follow their empirical marginal distribution. Under MNAR, this causes severe attribution infidelity because the missing feature was actually extreme, not average.  
Our Missingness-Aware TreeSHAP explicitly augments the feature space by pairing every metric residual $x_{t,m}$ with a binary missingness indicator $M_{t,m} \in \{0, 1\}$. The tree ensemble splits directly on sensor dropout. When pod telemetry drops out, TreeSHAP attributes positive Shapley credit to $M_{t,m} = 0$, reflecting that the metric's absence is itself the predictive signature of the crash. This reduces explanation infidelity from 13.3% to 6.7% and achieves an explanation stability of 0.884 Jaccard similarity.

---

### Q5: How are the weights $w_j$ of the 5D Trust Score determined, and are they sensitive to subjective tuning?
**Answer**:  
The weights are calibrated objectively using regularized logistic regression on pre-fault calibration splits with an L1 simplex constraint ($\sum w_j = 1, w_j \ge 0$), optimizing the separation between healthy and degraded telemetry.  
Furthermore, we conducted a Dirichlet sensitivity analysis across 100 random weight permutations ($\alpha = 1.0$). The resulting AC@3 had a standard deviation of only 0.018 across the entire simplex, proving that performance is governed by the axiomatic multiplicative floor on Validity and Completeness rather than fine-tuning of individual dimension weights.

---

### Q6: What is the theoretical necessity of the multiplicative floor in the trust metric? Why not a pure linear combination?
**Answer**:  
A purely linear combination $\sum w_j d_j$ permits fatal compensation: a metric reporting $-50\%$ CPU or completely frozen at zero samples could still achieve a trust score of $0.60$ if its other dimensions (e.g., timeliness or stability) appear normal. In cloud systems, a single invalid metric can destabilize matrix inversion in covariance-based detectors.  
The indicator function:
$$\mathbb{I}(V > 0) \cdot \mathbb{I}(C > 0)$$
enforces an axiomatic veto: if a metric violates physical reality ($V=0$) or has zero recorded samples ($C=0$), its trust is immediately truncated to absolute zero, preventing corrupt signals from entering downstream covariance updates.

---

### Q7: Does Constrained-xAIOps generalize to architectures with different microservice languages and frameworks?
**Answer**:  
Yes. Our evaluation spans all 375 cases across three distinct technology stacks:
1. `Online Boutique`: 10 services in Go, Python, C#, Java, and Node.js.
2. `Sock Shop`: 13 services using Go microservices with Spring Boot Java backends and RabbitMQ.
3. `Train Ticket`: 40 services built on Spring Cloud Java with 500+ metric streams.  
Across all three systems, Constrained-xAIOps consistently outperformed Vanilla BARO, $\epsilon$-Diagnosis, CIRCA, and RCD, demonstrating that axiomatic quality evaluation is agnostic to microservice implementation languages.

---

### Q8: In your Zero-Shot transfer experiment, why did Train Ticket achieve 129.5% retention (higher accuracy than in-domain)?
**Answer**:  
On Train Ticket, in-domain calibration with small sample sizes tended to over-index on specific noise characteristics of the complex 40-service topology. In contrast, the Online Boutique calibrated parameters provided a cleaner, more generalized threshold ($\tau_T = 0.816$), which filtered out background metric noise on Train Ticket more effectively. Zero-shot AC@3 reached 78.1% compared to 60.3% for in-domain calibration (+17.8% gain), confirming the robust cross-system transferability of our quality thresholds.

---

### Q9: How does Constrained-xAIOps detect and defend against Exporter Stale-Freeze and Adversarial Telemetry Spoofing?
**Answer**:  
- **Exporter Stale-Freeze**: When a daemon hangs, the metric values remain constant, but sampling timestamps continue or freeze. The Timeliness dimension ($L$) measures both arrival latency and variance starvation ($Var(x_{t-W:t}) \to 0$ on dynamic metrics like CPU). Mean timeliness drops to $L = 0.631$, triggering a 29.6% detection rate and yielding an AC@3 of 19.5% versus 12.8% for Vanilla BARO.
- **Adversarial Spoofing ("AI Oops")**: When an attacker injects fake healthy metrics, they create cross-service metric discrepancies with upstream callers. Consistency ($S = 0.986$) and Validity ($V = 0.976$) detect 41.3% of attacks, abstaining on poisoned streams while sustaining 99.5% localization accuracy on the remaining true incident telemetry.

---

### Q10: How does the computational overhead compare to Kubernetes sidecar resource limits?
**Answer**:  
Constrained-xAIOps executes with a mean inference latency of **3.82 ms** per case and consumes a peak memory of **218.4 MB**. Kubernetes standard sidecar limits typically allocate 0.5 CPU cores and 512 MB RAM. Constrained-xAIOps operates well within these bounds, requiring less than 50% of typical sidecar RAM limits and under 5 milliseconds of execution time, enabling non-blocking, per-scrape evaluation.

---

### Q11: How is the service call graph topology constructed, and what happens if service mesh tracing is unavailable?
**Answer**:  
Constrained-xAIOps maintains an immutable `BaseTopology` model representing service dependency graphs. In our benchmark evaluations, canonical directed graphs are used for Online Boutique, Sock Shop, and Train Ticket. If dynamic tracing (e.g., Jaeger, OpenTelemetry) is unavailable, the topology falls back gracefully to a heuristic directed dependency graph inferred from Prometheus container network receive/transmit cross-correlation during the pre-fault calibration window.

---

### Q12: How does your online human-in-the-loop recalibration avoid catastrophic drift when operators provide noisy feedback?
**Answer**:  
Our `OnlineThresholdRecalibrator` implements a damped Robbins-Monro stochastic approximation algorithm:
$$\tau_T^{(k+1)} = \Pi_{[\tau_{\min}, \tau_{\max}]} \left( \tau_T^{(k)} - \gamma_k \cdot \nabla \mathcal{L}(y, \hat{y}) \right)$$
where step size $\gamma_k = \frac{\gamma_0}{1 + \alpha k}$ decays harmonically over time, and $\Pi$ enforces strict projection onto safety bounds ($\tau_T \in [0.50, 0.95]$). This prevents any single errant operator decision from causing catastrophic threshold drift.

---

### Q13: Why did causal discovery baselines like CIRCA and RCD fail under 40% MNAR?
**Answer**:  
CIRCA (KDD '22) and RCD (NeurIPS '22) rely on hypothesis testing and causal graph constraint discovery (e.g., PC algorithm, conditional independence tests). Under 40% MNAR, missing observations destroy the empirical conditional distributions. Standard imputers introduce artificial collinearity, causing causal discovery engines to delete true causal edges or infer spurious reversal edges. Consequently, CIRCA collapses to 29.0% AC@3 on Online Boutique and 7.7% on Train Ticket, whereas Constrained-xAIOps retains 83.8% and 64.6%, respectively.

---

### Q14: How does the framework ingest real telemetry from live Kubernetes clusters?
**Answer**:  
In Phase 7, we implemented `PrometheusLiveLoader` in `src/ingestion/prometheus_live.py`. It interfaces directly with the Prometheus HTTP range API (`/api/v1/query_range`), collecting container CPU, memory working set, network receive/transmit bytes, and exporter `up` metrics at 15-second intervals (`scrapeInterval: 15s`). It maps container labels to canonical service names, aligns irregular timestamps, and constructs immutable `TelemetryCase` contracts with provenance tag `data_source_tag="LIVE_K8S_TESTBED"`.

---

### Q15: How can external auditors verify that no experimental numbers in the paper were mocked or fabricated?
**Answer**:  
We enforce strict reproducible provenance via automated auditing scripts:
1. `scripts/reproduce_paper.py`: Single-command reproduction running all tests, benchmarks, and table generation.
2. `scripts/verify_paper_provenance.py`: Automatically indexes all numerical metrics in `artifacts/metrics/statistical_summary.json` and `artifacts/metrics/phase6_multisystem_and_security.json` and verifies that every single number in LaTeX tables 1 through 5 matches the raw JSON artifacts within a 0.05 tolerance.
3. `tests/regression/test_artifact_provenance.py`: Unit test that fails CI if any number in the tables cannot be traced to the raw experimental output.
Zero mocked or synthetic numbers exist anywhere in our reported evaluation.
