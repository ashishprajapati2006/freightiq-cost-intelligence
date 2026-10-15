"""Comprehensive API integration test suite using FastAPI TestClient."""

import io
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Verify root endpoint responds with status and doc links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "version" in data


def test_root_cloud_health_endpoint():
    """Verify cloud provider health-check endpoint (/health) used by Render."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert "version" in data


def test_health_endpoint():
    """Verify health endpoint distinguishes application readiness and dataset status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["analysis_engine_ready"] is True
    assert data["total_shipments"] == 2940
    assert data["total_routes"] == 7
    assert data["total_context_notes"] == 10
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time-Ms" in response.headers


def test_metadata_endpoint():
    """Verify metadata returns exact 8 contract columns and parameters."""
    response = client.get("/api/v1/metadata")
    assert response.status_code == 200
    data = response.json()
    assert len(data["case_study_contract_columns"]) == 8
    assert "route" in data["case_study_contract_columns"]
    assert "vs_own_history" in data["case_study_contract_columns"]
    assert data["default_threshold_pct"] == 20.0


def test_list_and_get_dataset():
    """Verify dataset discovery and detail fetching."""
    list_res = client.get("/api/v1/datasets")
    assert list_res.status_code == 200
    datasets = list_res.json()
    assert len(datasets) >= 1
    default_ds = next(d for d in datasets if d["dataset_id"] == "default")
    assert default_ds["shipment_count"] == 2940
    assert default_ds["route_count"] == 7

    get_res = client.get("/api/v1/datasets/default")
    assert get_res.status_code == 200
    assert get_res.json()["dataset_id"] == "default"


def test_unknown_dataset_returns_404():
    """Verify non-existent dataset identifier yields structured 404."""
    response = client.get("/api/v1/datasets/non_existent_dataset_id")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


def test_path_traversal_detection():
    """Verify path traversal attempts are rejected with 400 security error."""
    response = client.get("/api/v1/datasets/invalid..traversal")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "SECURITY_VIOLATION"


def test_dataset_validate_valid_csv():
    """Verify dataset validation on a clean CSV upload."""
    valid_csv = (
        "shipment_id,origin,destination,route_type,material,quantity_tonnes,distance_km,freight_cost_inr,shipment_date,transporter\n"
        "TEST01,Mumbai,Pune,Short,Steel Coils,15.0,150.0,5000,2024-05-01,Test Transport\n"
    )
    files = {"shipments_file": ("test.csv", io.BytesIO(valid_csv.encode("utf-8")), "text/csv")}
    response = client.post("/api/v1/datasets/validate", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["total_records"] == 1
    assert data["invalid_records"] == 0


def test_dataset_validate_invalid_csv():
    """Verify dataset validation detects missing columns and invalid negative numbers."""
    invalid_csv = (
        "shipment_id,origin,destination,route_type,material,quantity_tonnes,distance_km,freight_cost_inr,shipment_date,transporter\n"
        "TEST01,Mumbai,Pune,InvalidType,Steel Coils,-5.0,0.0,-100,bad-date,Test Transport\n"
    )
    files = {"shipments_file": ("test_bad.csv", io.BytesIO(invalid_csv.encode("utf-8")), "text/csv")}
    response = client.post("/api/v1/datasets/validate", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert len(data["errors"]) > 0


def test_dataset_import_blocks_on_invalid_data():
    """Verify dataset import rejects invalid datasets and does not replace active data."""
    bad_csv = "shipment_id,bad_col\n1,2\n"
    files = {"shipments_file": ("bad.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")}
    data = {"dataset_name": "Bad Dataset"}
    response = client.post("/api/v1/datasets/import", files=files, data=data)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_analysis_run_and_retrieval():
    """Verify triggering an analysis run and retrieving its results."""
    run_req = {
        "dataset_id": "default",
        "threshold_pct": 20.0,
        "max_history_weeks": 8,
        "note_window_days": 42,
    }
    response = client.post("/api/v1/analysis/run", json=run_req)
    assert response.status_code == 200
    run_meta = response.json()
    run_id = run_meta["run_id"]
    assert run_meta["status"] == "COMPLETED"
    assert run_meta["metrics"]["total_route_weeks"] == 728
    assert run_meta["metrics"]["flagged_total"] == 20

    # Retrieve run metadata
    get_res = client.get(f"/api/v1/analysis/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["run_id"] == run_id

    # Retrieve metrics
    metrics_res = client.get(f"/api/v1/analysis/runs/{run_id}/metrics")
    assert metrics_res.status_code == 200
    assert "by_route_type" in metrics_res.json()

    # Retrieve paginated results
    res_page = client.get(f"/api/v1/analysis/runs/{run_id}/results?page=1&page_size=10")
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert len(page_data["items"]) == 10
    assert page_data["pagination"]["total_items"] == 728


def test_dashboard_summary():
    """Verify dashboard overview KPIs."""
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_shipments"] == 2940
    assert data["total_routes"] == 7
    assert data["flagged_route_weeks"] == 20
    assert data["unexplained_anomalies"] == 15
    assert data["evidence_supported"] == 5
    assert len(data["recent_anomalies"]) > 0


def test_weekly_costs_and_routes_analytics():
    """Verify analytics time-series and route listings."""
    weekly_res = client.get("/api/v1/analytics/weekly-costs?limit=12")
    assert weekly_res.status_code == 200
    weeks = weekly_res.json()
    assert len(weeks) == 12

    routes_res = client.get("/api/v1/analytics/routes")
    assert routes_res.status_code == 200
    routes = routes_res.json()
    assert len(routes) == 7

    # Single route detail
    route_timeline = client.get("/api/v1/analytics/routes/Delhi-Jaipur")
    assert route_timeline.status_code == 200
    r_data = route_timeline.json()
    assert r_data["route"] == "Delhi-Jaipur"
    assert len(r_data["timeline"]) == 104


def test_shipment_explorer_pagination_and_detail():
    """Verify shipment pagination and single ID inspection."""
    res = client.get("/api/v1/shipments?page=1&page_size=20&route=Delhi-Jaipur")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 20
    assert data["pagination"]["total_items"] == 416

    first_shp_id = data["items"][0]["shipment_id"]
    detail_res = client.get(f"/api/v1/shipments/{first_shp_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["shipment_id"] == first_shp_id


def test_anomalies_filtering_and_evidence_audit():
    """Verify anomaly monitor filters and evidence audit."""
    # Supported only
    sup_res = client.get("/api/v1/anomalies?evidence=supported")
    assert sup_res.status_code == 200
    sup_items = sup_res.json()["items"]
    assert len(sup_items) == 5
    for item in sup_items:
        assert item["flagged_label"] == "No (justified)"
        assert len(item["matched_note_id"]) > 0

    # Unexplained only
    un_res = client.get("/api/v1/anomalies?evidence=unexplained")
    assert un_res.status_code == 200
    un_items = un_res.json()["items"]
    assert len(un_items) == 15
    for item in un_items:
        assert item["flagged_label"] == "Yes"
        assert item["matched_note_id"] == ""

    # Deep dive evidence
    first_anom = sup_items[0]
    anom_id = first_anom["id"]
    ev_res = client.get(f"/api/v1/anomalies/{anom_id}/evidence")
    assert ev_res.status_code == 200
    ev_data = ev_res.json()
    assert ev_data["validation_outcome"] == "SUPPORTED_BY_AUTHENTIC_EVIDENCE"
    assert ev_data["matched_note"] is not None


def test_context_notes_and_classification():
    """Verify notes listing and non-cost-driver guardrail classification."""
    res = client.get("/api/v1/context-notes")
    assert res.status_code == 200
    notes = res.json()
    assert len(notes) == 10

    # N001 (flooding) is cost driver
    n001 = next(n for n in notes if n["note_id"] == "N001")
    assert n001["is_cost_driver"] is True

    # N005 (maintenance without cost impact) is NOT cost driver
    n005 = next(n for n in notes if n["note_id"] == "N005")
    assert n005["is_cost_driver"] is False


def test_csv_exports():
    """Verify CSV export format and exact 8-column case-study contract."""
    # 1. Contract export
    latest_run_id = client.get("/api/v1/analysis/runs").json()[0]["run_id"]
    exp_res = client.get(f"/api/v1/analysis/runs/{latest_run_id}/export.csv")
    assert exp_res.status_code == 200
    assert exp_res.headers["content-type"].startswith("text/csv")
    csv_text = exp_res.content.decode("utf-8")
    lines = [l.strip() for l in csv_text.splitlines() if l.strip()]
    header = lines[0]
    expected_header = "route,week_of,cost_per_tonne_km,vs_own_history,vs_similar_routes,flagged,matched_note_id,reason"
    assert header == expected_header

    # 2. Shipments export
    shp_exp = client.get("/api/v1/shipments/export.csv")
    assert shp_exp.status_code == 200

    # 3. Anomalies export
    anom_exp = client.get("/api/v1/anomalies/export.csv")
    assert anom_exp.status_code == 200


def test_assistant_query():
    """Verify grounded assistant returns verified facts without hallucination."""
    query_payload = {"query": "Which routes have the largest unexplained increases?"}
    res = client.post("/api/v1/assistant/query", json=query_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "deterministic"
    assert len(data["sources"]) > 0
    assert len(data["grounded_facts"]) > 0
    assert "unexplained" in data["answer"].lower()


def test_evaluation_reproducibility_endpoint():
    """Verify programmatic 3-run reproducibility endpoint confirms bit-for-bit equality."""
    res = client.post("/api/v1/evaluation/reproducibility")
    assert res.status_code == 200
    data = res.json()
    assert data["is_reproducible"] is True
    assert data["num_runs"] == 3
    assert data["total_records"] == 728
    assert data["discrepancies"] == []


def test_evaluation_tests_endpoint():
    """Verify verification checks endpoint runs all programmatic tests."""
    res = client.post("/api/v1/evaluation/tests")
    assert res.status_code == 200
    data = res.json()
    assert data["all_passed"] is True
    assert data["failed"] == 0
    assert data["total_tests"] >= 4


def test_cors_preflight_and_origin():
    """Verify CORS preflight OPTIONS and response headers for allowed origins."""
    # 1. Allowed origin test
    res = client.get("/health", headers={"Origin": "http://localhost:8000"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:8000"

    # 2. Preflight OPTIONS test
    options_res = client.options(
        "/api/v1/dashboard/summary",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert options_res.status_code == 200
    assert options_res.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert "GET" in options_res.headers.get("access-control-allow-methods", "")
