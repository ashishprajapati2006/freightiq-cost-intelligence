# FreightIQ — Production-Oriented FastAPI Backend

A production-ready FastAPI backend for the Freight Tiger Software Engineer Intern (AI) case study. It exposes RESTful APIs for freight unit-cost tracking, historical and peer baseline calculation, deterministic anomaly detection, anti-hallucination evidence validation, CSV exports, and grounded natural-language assistant queries.

---

## 1. Architecture Overview

- **Framework**: FastAPI with Pydantic v2 data models and asynchronous request lifecycle.
- **Data Engine**: Reuses the deterministic analysis engine built in Phase 1 (`backend/app/services/`). Zero duplicate business logic.
- **Persistence**: File-based storage abstraction (`backend/storage/`) tracking datasets, content hashes (SHA-256), analytical runs, and canonical CSV artifacts.
- **Security**: Strict input sanitization against path traversal, safe sorting column validation, file upload limits (25MB), and restrictive CORS controls.
- **No Heavy Infrastructure**: Operates cleanly without external databases (MongoDB, PostgreSQL), message brokers (Celery, Redis), or container runtimes, making it lightweight and deployable anywhere.

---

## 2. API Endpoints Reference

### Health & Metadata
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | System health, uptime, dataset status, and engine readiness |
| `GET` | `/api/v1/metadata` | Operational parameters, contract column list, and constraints |
| `GET` | `/api/v1/datasets` | List all available stored datasets with content hashes |
| `GET` | `/api/v1/datasets/{dataset_id}` | Detailed metadata for a specific dataset |

### Dataset Ingestion & Validation
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/datasets/validate` | Validate uploaded shipment/notes CSV without replacing active data |
| `POST` | `/api/v1/datasets/import` | Validate and persist new active dataset |
| `GET` | `/api/v1/datasets/{dataset_id}/validation` | Retrieve validation report for a stored dataset |

### Analysis Engine
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/analysis/run` | Execute full analytical pipeline with configurable thresholds |
| `GET` | `/api/v1/analysis/runs` | List historical analysis runs |
| `GET` | `/api/v1/analysis/runs/{run_id}` | Retrieve run status, execution time, and configuration |
| `GET` | `/api/v1/analysis/runs/{run_id}/results` | Paginated, filterable, sortable analytical records |
| `GET` | `/api/v1/analysis/runs/{run_id}/metrics` | Aggregated KPI metrics and route-type breakdowns |

### Dashboard & Analytics
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/dashboard/summary` | Top-level KPIs, route-type comparisons, and recent deviations |
| `GET` | `/api/v1/analytics/weekly-costs` | Weekly average unit-cost time series for charting |
| `GET` | `/api/v1/analytics/routes` | Origin-destination route list with volume and unit costs |
| `GET` | `/api/v1/analytics/routes/{route_id}` | Chronological timeline and baselines for a single route |
| `GET` | `/api/v1/shipments` | Paginated shipment explorer with filtering and sorting |
| `GET` | `/api/v1/shipments/{shipment_id}` | Detailed single shipment record |

### Anomalies & Qualitative Evidence
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/anomalies` | Paginated anomaly monitor (evidence status, min deviation) |
| `GET` | `/api/v1/anomalies/{anomaly_id}` | Detailed metrics for a single route-week anomaly |
| `GET` | `/api/v1/anomalies/{anomaly_id}/evidence` | Audit trail, matched context note, and guardrail validation |
| `GET` | `/api/v1/context-notes` | List context notes with route applicability and impact status |
| `GET` | `/api/v1/context-notes/{note_id}` | Note details and associated anomaly cases |

### CSV Exports
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/analysis/runs/{run_id}/export.csv` | Exact 8-column case-study contract CSV (RFC-4180 compliant) |
| `GET` | `/api/v1/shipments/export.csv` | Filtered shipment records download |
| `GET` | `/api/v1/anomalies/export.csv` | Filtered anomaly monitor records download |

### Grounded Assistant
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/assistant/query` | Grounded, factual Q&A without LLM hallucination |

### Evaluation & Usage
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/evaluation/reproducibility` | Execute 3 untouched runs and confirm bit-for-bit equality |
| `POST` | `/api/v1/evaluation/tests` | Run programmatic verification test suite |
| `GET` | `/api/v1/usage/runs/{run_id}` | Token/cost accounting and provider status |

---

## 3. Running Locally

### Start with Uvicorn
From the workspace root or `backend/` directory:
```bash
# Start backend server on port 8001
uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 --reload
```

Interactive OpenAPI documentation is automatically available at:
- Swagger UI: [http://localhost:8001/docs](http://localhost:8001/docs)
- ReDoc: [http://localhost:8001/redoc](http://localhost:8001/redoc)

---

## 4. Sample Endpoint Requests and Responses

### 1. Health Status
```bash
curl http://localhost:8001/api/v1/health
```
```json
{
  "status": "healthy",
  "app": "FreightIQ API",
  "version": "0.2.0",
  "analysis_engine_ready": true,
  "active_dataset_id": "default",
  "total_shipments": 2940,
  "total_routes": 7,
  "total_context_notes": 10,
  "uptime_seconds": 12.4
}
```

### 2. Trigger Analysis Run
```bash
curl -X POST http://localhost:8001/api/v1/analysis/run \
  -H "Content-Type: application/json" \
  -d '{"threshold_pct": 20.0, "max_history_weeks": 8}'
```
```json
{
  "run_id": "run_1728980000_a1b2c3",
  "dataset_id": "default",
  "status": "COMPLETED",
  "execution_time_ms": 32.4,
  "metrics": {
    "total_route_weeks": 728,
    "flagged_total": 20,
    "justified_count": 5,
    "unexplained_count": 15,
    "avg_cost_per_tonne_km": 2.7042,
    "unique_routes": 7
  }
}
```

### 3. Grounded Assistant Query
```bash
curl -X POST http://localhost:8001/api/v1/assistant/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Which routes have the largest unexplained increases?"}'
```
```json
{
  "query": "Which routes have the largest unexplained increases?",
  "answer": "There are 15 unexplained cost anomalies in the dataset. The highest unexplained deviations are:\n1. Delhi-Jaipur (Week of 2024-11-11): 4.173 ₹/t-km (+35.5% vs history, +21.0% vs peers) — Unexplained...",
  "mode": "deterministic",
  "model": "deterministic-rules-engine",
  "grounded_facts": [
    {"statement": "Identified 15 total unexplained route-week anomalies", "verified": true}
  ],
  "sources": [
    {"type": "analysis_record", "id": "Delhi-Jaipur-2024-11-11", "description": "Delhi-Jaipur spike on 2024-11-11 (+35.5% vs history)"}
  ],
  "execution_time_ms": 2.1
}
```

---

## 5. Machine Learning Anomaly Detection Pipeline

An optional, scientifically rigorous machine-learning anomaly detection pipeline utilizing an unsupervised scikit-learn **Isolation Forest**.

### 5.1 Architecture & Ethical Principles
1. **Deterministic Authority**: The deterministic case-study engine remains 100% authoritative for all required numeric columns (`cost_per_tonne_km`, `vs_own_history`, `vs_similar_routes`, `flagged`, `matched_note_id`, `reason`). ML scores serve strictly as an auxiliary prioritization signal.
2. **Zero Fabrication**: Because ground-truth anomaly labels do not exist in unlabelled freight data, **classification accuracy, precision, recall, and F1 scores are not fabricated**. The model is evaluated empirically against the deterministic domain baseline.
3. **Zero Look-Ahead Bias**: All features (including trailing volatility and 1-week momentum) are computed strictly on observations prior to the current week ($< \text{week\_of}$).
4. **Identifier Avoidance**: Geographic route strings (`route`, `origin`, `destination`) and transporter IDs are excluded from features to prevent corridor bias and carrier memorization.
5. **Anti-Hallucination Guardrail**: The ML model cannot read context notes and is prohibited from inventing evidence or marking an anomaly as justified.

### 5.2 Engineered Feature Set
Implemented in `backend/app/services/ml_features.py`:
- `cost_per_tonne_km`: Work-weighted freight cost in INR.
- `pct_vs_history`: Percentage deviation relative to trailing $\le 8$ weeks history.
- `pct_vs_peers`: Percentage deviation relative to same-week peer route average.
- `momentum_1w`: 1-week absolute unit cost delta from the immediately preceding week.
- `history_volatility`: Rolling sample standard deviation of unit cost over trailing $\le 8$ weeks.
- `z_score_history`: Standardized deviation normalized by trailing route volatility.

### 5.3 Training Command & Serialization
Train via CLI or REST API:
```bash
# Terminal CLI Command
python -m backend.app.services.ml_training --contamination 0.03 --n-estimators 150 --seed 42 --holdout-weeks 26

# REST API Call
curl -X POST http://localhost:8001/api/v1/ml/train \
  -H "Content-Type: application/json" \
  -d '{"contamination": 0.03, "n_estimators": 150, "random_state": 42, "holdout_weeks": 26}'
```
Artifacts are versioned and serialized to `backend/ml_models/`:
- `model.joblib`: Serialized Isolation Forest estimator.
- `feature_schema.json`: Strict feature typing, fill values, and bounds.
- `preprocessing_config.json`: RobustScaler centers, scales, and score calibration bounds.
- `metadata.json`: SHA-256 data hash, hyperparameters, record counts, and training timestamp.
- `evaluation_report.json`: Chronological holdout evaluation and contingency matrix.

### 5.4 Empirical Evaluation & Baseline Concordance
- **Overall Agreement Rate**: **98.08%** (714 / 728 route-week observations)
- **Chronological Holdout Agreement**: **98.35%** (179 / 182 out-of-sample weeks)
- **Rule Spikes Identified**: 16 / 20 (80.0% concordance on severe spikes)
- **Contingency Matrix**:
  | | Deterministic Flagged ($\ge 20\%$) | Deterministic Normal ($< 20\%$) |
  |---|---|---|
  | **ML Flagged Outlier** | **16** (Both flagged) | **10** (Subtle volatility outliers) |
  | **ML Normal Inlier** | **4** (Boundary threshold crossings) | **698** (Both normal) |

### 5.5 Inference & Transparent Fallback
Inference service (`backend/app/services/ml_inference.py`) safely loads model artifacts:
- Calibrates raw decision function into normalized `ml_anomaly_score` ($0.0 \dots 1.0$) and qualitative tiers (`LOW`, `MODERATE`, `ELEVATED`, `CRITICAL`).
- **Transparent Fallback**: If model artifacts are missing or unreadable, the inference engine transparently falls back to heuristic baseline scoring without raising 500 errors.

### 5.6 Model Governance & Drift Monitoring
Endpoint `GET /api/v1/ml/monitoring/drift` tracks:
- **Input Schema Health**: Missing column rates, non-numeric types, infinite values.
- **Feature Distribution Drift**: Normalized Median Shift against training IQR.
- **Score Distribution Drift**: Anomaly rate divergence vs expected contamination.
- **Model Age**: Alerts if model exceeds 90 days.
- **Explicit Retraining Guardrail**: Enforces minimum 90% agreement before auto-deployment.

---

## 6. Test Suite Verification

Run the complete test suite (unit checks, contract checks, API integration tests, and ML pipeline tests):
```bash
pytest -v backend/tests
```

**Result**: 47 passed tests in ~50 seconds:
- **14 analytical tests**: Monday grouping, work done, baselines, guardrails, contract formatting.
- **19 integration tests**: FastAPI endpoints, security sanitization, pagination, CSV exports, assistant, reproducibility.
- **14 machine learning pipeline tests**: Feature extraction, zero look-ahead check, chronological holdout agreement, seed reproducibility, safe serialization/loading, transparent fallback mode, schema drift detection, deployment policy guardrail, and ML API routes.
