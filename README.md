# FreightIQ: Smart Freight Cost Intelligence Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776ab?logo=python&logoColor=white)](https://python.org)
[![Tests](https://img.shields.io/badge/pytest-49%20passed-brightgreen?logo=pytest&logoColor=white)](file:///backend/tests)
[![Reproducibility](https://img.shields.io/badge/Reproducibility-100%25%20Bit--for--Bit-success)](#7-reproducibility-benchmark)
[![Deployment](https://img.shields.io/badge/Deployment-Vercel%20%2B%20Render-blue)](file:///render.yaml)

FreightIQ is an end-to-end freight analytics, baseline benchmarking, and anomaly intelligence platform developed for the **Freight Tiger Software Engineer Intern (AI)** case study. It bridges an enterprise dark-theme vanilla HTML/CSS/JavaScript dashboard with a high-performance FastAPI analytics backend.

FreightIQ calculates work-weighted freight unit rates, computes trailing 8-week historical baselines (zero look-ahead) and same-week peer corridor baselines (self-excluding), detects cost spikes exceeding 20%, cross-references qualitative operational context notes with anti-hallucination guardrails, and provides an optional Isolation Forest ML anomaly scoring engine.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Repository Structure](#2-repository-structure)
3. [Prerequisites](#3-prerequisites)
4. [Local Setup & Startup Guide](#4-local-setup--startup-guide)
5. [Environment Variables & Secrets Management](#5-environment-variables--secrets-management)
6. [REST API Documentation & Health Checks](#6-rest-api-documentation--health-checks)
7. [Dataset Contracts & 8-Column CSV Output](#7-dataset-contracts--8-column-csv-output)
8. [Automated Testing & QA](#8-automated-testing--qa)
9. [Frontend Production Build & Vercel Deployment](#9-frontend-production-build--vercel-deployment)
10. [Backend Production Configuration & Render Deployment](#10-backend-production-configuration--render-deployment)
11. [Cross-Origin Communication (CORS) Guide](#11-cross-origin-communication-cors-guide)
12. [GitHub Push Workflow](#12-github-push-workflow)
13. [Troubleshooting Guide](#13-troubleshooting-guide)
14. [Reproducibility Benchmark & Token Accounting](#14-reproducibility-benchmark--token-accounting)

---

## 1. System Architecture

```
┌────────────────────────────────────────────────────────┐
│                   Vercel Deployment                     │
│      Vanilla HTML5 / Modern CSS / ES2022 JavaScript    │
│   • Dark theme dashboard with collapsible navigation   │
│   • Dynamic Chart.js visualizations & 9 CSV exports    │
│   • In-app API configuration (Settings ⚙ & config.js)  │
└───────────────────────────┬────────────────────────────┘
                            │ HTTPS (CORS protected)
                            ▼
┌────────────────────────────────────────────────────────┐
│                   Render Deployment                    │
│            FastAPI Production ASGI Backend             │
│   • Entry point: backend.app.main:app                  │
│   • Dynamic binding: 0.0.0.0:$PORT                     │
│   • Health check: /health and /api/v1/health           │
│   • Dual baselines (Trailing 8-wk & Peer corridors)    │
│   • Anti-hallucination context note audit trail        │
│   • Scikit-learn Isolation Forest ML pipeline          │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│              Bundled Datasets & Storage                │
│   • dataset/shipment_records.csv (2,940 records)       │
│   • dataset/context_notes.csv (10 operational notes)   │
│   • dataset/sample_output_format_v2.csv (Contract)     │
│   • backend/ml_models/model.joblib (Trained model)     │
└────────────────────────────────────────────────────────┘
```

---

## 2. Repository Structure

```text
FreightIQ/
├── backend/
│   ├── app/
│   │   ├── api/v1/              # REST route modules (11 modules)
│   │   ├── core/                # Config, CORS, exceptions, middleware
│   │   ├── schemas/             # Pydantic v2 validation contracts
│   │   ├── services/            # Deterministic analytics, ML & storage
│   │   │   ├── aggregation.py        # Work-weighted unit rates
│   │   │   ├── cost_analysis.py      # Dual-baseline engine
│   │   │   ├── anomaly_detection.py  # Anomaly verdicts & context matching
│   │   │   ├── ml_features.py        # ML feature engineering pipeline
│   │   │   ├── ml_inference.py       # Isolation Forest scoring service
│   │   │   ├── ml_training.py        # Chronological model training
│   │   │   ├── assistant.py          # Grounded assistant engine
│   │   │   └── storage.py            # Dataset SHA-256 and run storage
│   │   └── main.py              # FastAPI app & lifespan management
│   ├── ml_models/               # Serialized Isolation Forest & metadata
│   ├── notebooks/
│   │   └── freight_cost_analysis.ipynb # Executable analysis & ML notebook
│   ├── output/
│   │   └── freight_cost_anomalies.csv  # Canonical 8-column case-study CSV
│   ├── storage/                 # Run history & uploaded datasets
│   ├── tests/                   # 49 comprehensive pytest unit/integration tests
│   ├── requirements.txt         # Pinned production Python dependencies
│   └── README.md                # Backend-specific architecture guide
├── dataset/
│   ├── shipment_records.csv     # 2,940 raw shipments across 7 corridors
│   ├── context_notes.csv        # 10 qualitative operational notes
│   ├── sample_output_format_v2.csv # Authoritative 8-column case-study schema
│   └── FreightTiger_Intern_CaseStudy.pdf # Original case study document
├── frontend/
│   ├── assets/                  # Icons and visual assets
│   ├── css/
│   │   └── styles.css           # Vanilla CSS design system (dark & light)
│   ├── data/                    # Offline fallback datasets
│   ├── js/
│   │   ├── config.js            # Runtime API base URL configuration
│   │   ├── api-client.js        # Centralized HTTP client (retries, timeouts)
│   │   └── app.js               # Dashboard controller and views
│   ├── build-config.js          # Zero-dependency Vercel build injector
│   ├── index.html               # Semantic HTML5 dashboard shell
│   ├── package.json             # Build and serve scripts
│   └── vercel.json              # Clean URLs, caching & security headers
├── .env.example                 # Canonical root environment configuration template
├── .gitignore                   # Production Git ignore rules
├── pytest.ini                   # Pytest runner configuration
├── render.yaml                  # Render Blueprint Web Service definition
└── README.md                    # Project documentation
```

---

## 3. Prerequisites

- **Python**: 3.10, 3.11, or 3.12
- **Node.js**: 18+ (optional, only used during Vercel automated builds or local static serve)
- **Browser**: Any modern web browser (Chrome, Edge, Firefox, Safari)
- **Git**: Installed for version control and deployment

---

## 4. Local Setup & Startup Guide

### Step 1: Clone Repository
```bash
git clone <YOUR-REPOSITORY-URL>
cd "AI Intern Case Study"
```

### Step 2: Backend Setup
```bash
# Create and activate virtual environment
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (cmd):
.\venv\Scripts\activate.bat
# Linux/macOS:
source venv/bin/activate

# Install pinned dependencies
pip install -r backend/requirements.txt

# Start backend server with reload enabled
uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --reload
```
- Interactive Swagger UI: `http://127.0.0.1:8001/docs`
- Root Health Check: `http://127.0.0.1:8001/health`
- API Health Endpoint: `http://127.0.0.1:8001/api/v1/health`

### Step 3: Frontend Setup
In a second terminal:
```bash
cd frontend

# Option A (Python built-in server):
python -m http.server 8000

# Option B (Node.js serve):
npm run dev
```
Open your browser to:
👉 **`http://localhost:8000`**

The dashboard automatically connects to `http://127.0.0.1:8001/api/v1` and displays a green **"Backend Connected (v0.2.0)"** status badge.

---

## 5. Environment Variables & Secrets Management

The canonical configuration template is located at [`.env.example`](file:///.env.example). Copy it to `.env` for local customization:

```bash
cp .env.example .env
```

### Environment Variable Reference

| Variable | Application | Environment | Default / Example | Purpose |
|---|---|---|---|---|
| `FREIGHTIQ_API_BASE_URL` | Frontend | Vercel / Local | `https://YOUR-APP.onrender.com/api/v1` | Production Render backend URL |
| `VITE_API_BASE_URL` | Frontend | Vercel / Local | `https://YOUR-APP.onrender.com/api/v1` | Supported alias for API base URL |
| `ENVIRONMENT` | Backend | Render / Local | `development` / `production` | Deployment mode |
| `HOST` | Backend | Local | `127.0.0.1` | Local server bind address |
| `PORT` | Backend | Render / Local | `8001` (Render injects `$PORT`) | Server listening port |
| `FRONTEND_ORIGINS` | Backend | Render | `https://YOUR-APP.vercel.app` | Allowed CORS origins (comma-separated) |
| `ALLOW_VERCEL_PREVIEWS` | Backend | Render | `true` | Allows `https://*.vercel.app` preview URLs |
| `ANOMALY_THRESHOLD_PCT` | Backend | Both | `20.0` | Case-study anomaly percentage threshold |
| `MAX_HISTORICAL_WEEKS` | Backend | Both | `8` | Maximum trailing historical weeks |
| `NOTE_DATE_WINDOW_DAYS`| Backend | Both | `42` | Post-event context note matching horizon |
| `MAX_UPLOAD_SIZE_BYTES`| Backend | Both | `26214400` (25 MB) | CSV upload security ceiling |

### Security Rules
- `.env` and all `.env.*` files are strictly excluded from version control via `.gitignore`.
- Browser-accessible frontend variables are public by design; never place API keys, private tokens, or database passwords in frontend code.
- Render environment variables are managed directly in the Render dashboard and kept private on the server.

---

## 6. REST API Documentation & Health Checks

Interactive OpenAPI documentation is generated automatically by FastAPI at `/docs` (Swagger UI) and `/redoc` (ReDoc).

### Health Endpoints
- **Root Health Check**: `GET /health`  
  Returns `{ "status": "healthy", "service": "FreightIQ API", "version": "0.2.0", "environment": "production" }`. Configured as Render's primary health check path.
- **Detailed Health Check**: `GET /api/v1/health`  
  Returns application uptime, analysis engine readiness, and active dataset row counts.

### Key API Routes
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Cloud provider lightweight health check |
| `GET` | `/api/v1/health` | Comprehensive engine & dataset health status |
| `GET` | `/api/v1/metadata` | Contract column list, constraints, and parameters |
| `GET` | `/api/v1/dashboard/summary` | Top-level KPIs, route breakdowns, recent anomalies |
| `GET` | `/api/v1/analytics/weekly-costs` | Route-week time series data for charting |
| `GET` | `/api/v1/analytics/routes` | Unique route corridors and volume metrics |
| `GET` | `/api/v1/shipments` | Paginated, filtered shipment records |
| `GET` | `/api/v1/shipments/export.csv` | Direct RFC-4180 CSV export of filtered shipments |
| `GET` | `/api/v1/anomalies` | Paginated route-week anomaly records with baseline diffs |
| `GET` | `/api/v1/anomalies/export.csv` | Direct RFC-4180 CSV export of filtered anomalies |
| `GET` | `/api/v1/context-notes` | Operational context notes with cost-driver flags |
| `POST` | `/api/v1/analysis/run` | Execute analysis pipeline with custom thresholds |
| `GET` | `/api/v1/analysis/runs/{id}/export.csv` | **Authoritative 8-column case-study CSV output** |
| `POST` | `/api/v1/ml/train` | Train scikit-learn Isolation Forest anomaly model |
| `POST` | `/api/v1/ml/score` | Score dataset route-weeks with ML criticality index |
| `GET` | `/api/v1/ml/monitoring/drift` | Feature drift detection across datasets |
| `POST` | `/api/v1/evaluation/reproducibility` | Automated 3-run bit-for-bit determinism test |
| `POST` | `/api/v1/evaluation/tests` | Execute programmatic contract validation suite |

---

## 7. Dataset Contracts & 8-Column CSV Output

### Authoritative Case-Study Output Contract
The primary analysis export (`GET /api/v1/analysis/runs/{run_id}/export.csv`) strictly adheres to the exact eight-column specification defined in the case study:

```text
route,week_of,cost_per_tonne_km,vs_own_history,vs_similar_routes,flagged,matched_note_id,reason
```

| Column | Type | Example | Description |
|---|---|---|---|
| `route` | String | `Delhi-Jaipur` | Standardized Origin-Destination corridor |
| `week_of` | ISO Date | `2023-01-02` | Monday starting the weekly observation |
| `cost_per_tonne_km` | Float (2-4 dec) | `4.18` | Total weekly freight cost divided by total tonne-km |
| `vs_own_history` | Float / empty | `3.45` | Prior $\le 8$ weeks average (excludes current week) |
| `vs_similar_routes`| Float / empty | `3.82` | Same-week peer corridor average (self-excluded) |
| `flagged` | String | `Yes` / `No (justified)` | Verdict: spike $\ge 20\%$ above either baseline |
| `matched_note_id` | String | `N001` / empty | Validated context note ID within 42 days |
| `reason` | String | `Corridor toll revision` | Operational justification from matched note |

### Bundled Datasets
- `dataset/shipment_records.csv`: 2,940 raw shipment records across 7 corridors (`Ahmedabad-Mumbai`, `Bangalore-Hyderabad`, `Chennai-Bangalore`, `Delhi-Jaipur`, `Delhi-Kolkata`, `Hyderabad-Chennai`, `Mumbai-Pune`).
- `dataset/context_notes.csv`: 10 operational context notes containing real-world external factors (toll revisions, diesel surcharges, seasonal spikes, non-cost operational changes).

---

## 8. Automated Testing & QA

Run the complete 49-test suite from the repository root:

```bash
pytest backend/tests -v
```

### Test Suite Breakdown
- `test_aggregation.py`: Monday weekly binning, route normalization, work-weighted rate formula.
- `test_cost_analysis.py`: Trailing 8-week cap, zero look-ahead isolation, peer group exclusion, null baseline handling.
- `test_anomaly_detection.py`: 20% threshold application, corridor scope matching, 42-day window, guardrail rejection of non-cost notes (`N004`, `N010`).
- `test_contract.py`: Exact 8-column header order, RFC-4180 quotation escaping, and round-trip re-ingestion.
- `test_evaluation.py`: Multi-run reproducibility benchmark and 10-note guardrails verification.
- `test_api_integration.py`: Root `/health` endpoint, `/api/v1/health`, metadata, CORS preflight and allowed origins, pagination, filtering, CSV exports, security/path traversal protection.
- `test_ml_pipeline.py`: Feature engineering, chronological train/test split, Isolation Forest serialization, drift detection, and scoring endpoints.

---

## 9. Frontend Production Build & Vercel Deployment

### Architecture on Vercel
The frontend is built using standard Vanilla HTML5, CSS3, and ES2022 JavaScript. It requires zero heavy build frameworks (no Webpack, Vite, or React).

Vercel serves the static frontend directly from the `frontend/` directory with clean URLs and security headers defined in [`frontend/vercel.json`](file:///frontend/vercel.json).

### Vercel Deployment Steps

1. **Sign in to Vercel** and click **"Add New Project"** $\rightarrow$ **"Import Git Repository"**.
2. Select your repository.
3. Configure Project Settings:
   - **Framework Preset**: `Other`
   - **Root Directory**: Click "Edit" and choose `frontend`
   - **Build Command**: `npm run build` (runs zero-dependency `node build-config.js` to inject environment variables)
   - **Output Directory**: `.` (leave default)
4. **Environment Variables**:
   - Add variable: `FREIGHTIQ_API_BASE_URL`
   - Value: `https://YOUR-RENDER-SERVICE.onrender.com/api/v1` (replace with your actual Render service URL)
   - Environments: Select **Production** and **Preview**
5. Click **"Deploy"**.

### Runtime API URL Fallback
If deployed without environment variables, the frontend gracefully detects that it is running on a remote domain:
- Shows a helpful notice indicating that the backend URL is unconfigured.
- Operates in offline demo mode.
- Users can navigate to **Settings (⚙) $\rightarrow$ API Backend**, enter their Render URL, test the connection with one click, and save it to `localStorage`.

---

## 10. Backend Production Configuration & Render Deployment

### Architecture on Render
The backend is deployed as a **Render Web Service** running Python 3.11 with Uvicorn. It listens on `0.0.0.0:$PORT` dynamically supplied by Render.

The service is pre-configured via the root [`render.yaml`](file:///render.yaml) blueprint.

### Option A: Deploy via Render Blueprint (Recommended)
1. In the Render Dashboard, click **"New"** $\rightarrow$ **"Blueprint"**.
2. Connect your GitHub repository.
3. Render automatically reads `render.yaml`:
   - Service Name: `freightiq-api`
   - Runtime: `Python`
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - Health Check Path: `/health`
4. Set the `FRONTEND_ORIGINS` environment variable to your deployed Vercel domain (e.g., `https://freightiq.vercel.app`).
5. Click **"Apply"**.

### Option B: Deploy Manually as a Web Service
1. Click **"New"** $\rightarrow$ **"Web Service"**.
2. Connect your GitHub repository.
3. Settings:
   - **Name**: `freightiq-api`
   - **Region**: Any (e.g. Oregon, Frankfurt)
   - **Branch**: `main`
   - **Root Directory**: `.` (leave empty for repository root)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
4. **Advanced Settings**:
   - **Health Check Path**: `/health`
5. **Environment Variables**:
   | Key | Value |
   |---|---|
   | `PYTHON_VERSION` | `3.11.9` |
   | `ENVIRONMENT` | `production` |
   | `FRONTEND_ORIGINS` | `https://YOUR-VERCEL-DOMAIN.vercel.app` |
   | `ALLOW_VERCEL_PREVIEWS` | `true` |
   | `ANOMALY_THRESHOLD_PCT` | `20.0` |
   | `MAX_HISTORICAL_WEEKS` | `8` |
   | `NOTE_DATE_WINDOW_DAYS`| `42` |
6. Click **"Create Web Service"**.

---

## 11. Cross-Origin Communication (CORS) Guide

When the frontend hosted on `https://your-app.vercel.app` makes API requests to the backend on `https://your-api.onrender.com`, the browser issues preflight `OPTIONS` requests.

The backend handles CORS through FastAPI's `CORSMiddleware`:
1. **Production Origins**: Set via the `FRONTEND_ORIGINS` environment variable (comma-separated if multiple domains are needed).
2. **Vercel Preview Deployments**: When `ALLOW_VERCEL_PREVIEWS=true`, the backend accepts origins matching `^https://[a-zA-Z0-9_-]+\.vercel\.app$`, allowing pull-request preview links to connect safely without wildcards.
3. **Local Development**: In development mode (`ENVIRONMENT=development`), `http://localhost:8000`, `http://127.0.0.1:8000`, and `http://localhost:5173` are enabled by default.

---

## 12. GitHub Push Workflow

Follow these exact steps to push this clean repository to GitHub:

```bash
# 1. Initialize Git (if not already initialized)
git init -b main

# 2. Check status and ensure secret .env files are NOT staged
git status

# 3. Add all project files (governed strictly by .gitignore)
git add .

# 4. Verify staged files (ensure no virtual environments, caches, or credentials)
git status

# 5. Create initial production-ready commit
git commit -m "feat: complete FreightIQ production-ready platform with Vercel and Render deployment configurations"

# 6. Add your GitHub remote repository (replace with your repository URL)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git

# 7. Push to GitHub main branch
git push -u origin main
```

---

## 13. Troubleshooting Guide

### Issue: Frontend displays "Backend Offline" or "Backend Unconfigured"
- **Cause**: The frontend cannot reach the backend URL or the URL is not set.
- **Resolution**:
  1. Open the dashboard and navigate to **Settings (⚙)** $\rightarrow$ **API Backend**.
  2. Confirm the URL is `https://YOUR-RENDER-SERVICE.onrender.com/api/v1` (with `/api/v1`).
  3. Click **"Test"** to verify connection.
  4. On Vercel, ensure `FREIGHTIQ_API_BASE_URL` is set in Project Settings and redeploy.

### Issue: CORS error in browser console (`Access-Control-Allow-Origin missing`)
- **Cause**: The Render backend has not whitelisted the Vercel domain.
- **Resolution**:
  1. Go to your Render Web Service dashboard $\rightarrow$ **Environment**.
  2. Set `FRONTEND_ORIGINS` to include your exact Vercel URL (e.g. `https://your-domain.vercel.app`).
  3. Set `ALLOW_VERCEL_PREVIEWS` to `true`.
  4. Click "Save Changes" (Render will automatically redeploy).

### Issue: Render deployment times out on startup
- **Cause**: Server failed to bind to `$PORT` or Uvicorn didn't start on `0.0.0.0`.
- **Resolution**: Verify the start command in Render is exactly:
  `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
  Ensure the root directory is set to `.` (empty) so Python finds both `backend/` and `dataset/`.

### Issue: Health check fails on Render
- **Cause**: Health check path misconfigured.
- **Resolution**: Set the health check path to `/health` (or `/api/v1/health`).

---

## 14. Reproducibility Benchmark & Token Accounting

### 3-Run Reproducibility Benchmark
To prove absolute determinism, the system incorporates an automated 3-run reproducibility benchmark:
- Runs Executed: 3
- Records per Run: 728 route-weeks (7 corridors $\times$ 104 weeks)
- Flagged Count per Run: 20
- Justified Count per Run: 5
- Unexplained Count per Run: 15
- Bit-for-Bit Discrepancies: 0
- Comparison Outcome: **PERFECT MATCH (100% deterministic)**

Trigger the test programmatically via:
- UI: **Evaluation & testing** view $\rightarrow$ **"Run 3 Comparisons"**
- API: `POST /api/v1/evaluation/reproducibility`

### Token & Cost Accounting
- **0 LLM calls** are made during core anomaly calculation, baseline aggregation, and CSV generation.
- Raw shipment transactions are **never** streamed to third-party generative LLMs.
- Model cost is reported truthfully as **$0.00 / ₹0.00** across all analytical runs.
