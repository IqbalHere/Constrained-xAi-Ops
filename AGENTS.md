# AGENTS.md - Scientific Integrity & Architectural Rules

## Constrained-xAIOps: Data-Quality-Aware, Explainable AIOps for Constrained Cloud Environments

### Non-Negotiable Scientific Integrity Rules:
1. **NO FABRICATED OR MOCKED RESULTS**: Every metric reported must be computed programmatically from the real downloaded RCAEval files. No synthetic placeholders or mock values may substitute for experimental outputs.
2. **ZERO LEAKAGE**: Fitting, calibration, and threshold-setting must be restricted strictly to pre-fault windows (`t < inject_time - 10s`). Post-fault data (`t >= inject_time`) must never touch normalization parameters, baselines, or covariance matrices.
3. **NO HARD-CODED METRICS**: Write experimental metrics strictly to dynamic JSON artifacts in `artifacts/metrics/clean_baselines_re1_ob.json`.
4. **IMMUTABLE DATA CONTRACTS**: All pipeline stages must communicate using validated Pydantic v2 schemas defined in `src/schemas.py`.
5. **REPRODUCIBILITY**: All randomized components must respect deterministic random seeds specified in `configs/`. Default seeds: `[42, 1024, 2025, 2026, 7777]`.
