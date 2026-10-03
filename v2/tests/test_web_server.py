"""
test_web_server.py - Unit tests for profile-driven Web Server & REST APIs.
"""

import json
import threading
import urllib.request
import urllib.error
import pytest
from http.server import HTTPServer
from v2.core.web_server import make_handler, get_dashboard_html


@pytest.fixture
def test_server(real_profile, temp_db_path, tmp_path):
    """Spin up an ephemeral test HTTP server on port 0."""
    json_path = str(tmp_path / "jobs.json")
    handler_cls = make_handler(real_profile, temp_db_path, json_path)
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.shutdown()
    server.server_close()


def test_get_dashboard_html_replaces_candidate_name(real_profile):
    """Verify HTML template embeds candidate name and tagline."""
    html = get_dashboard_html(real_profile)
    cand_name = real_profile.candidate_background.personal_info.name
    assert cand_name in html


def test_http_dashboard_route(test_server, real_profile):
    """Verify GET / returns 200 OK and valid HTML."""
    req = urllib.request.Request(f"{test_server}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert real_profile.candidate_background.personal_info.name in content


def test_http_options_cors(test_server):
    """Verify OPTIONS preflight returns CORS headers."""
    req = urllib.request.Request(f"{test_server}/api/jobs", method="OPTIONS")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"


def test_http_api_jobs(test_server):
    """Verify GET /api/jobs returns active job listings."""
    req = urllib.request.Request(f"{test_server}/api/jobs")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert isinstance(data, list)
        assert len(data) > 0
        assert "company" in data[0]


def test_http_apply_and_unapply_flow(test_server):
    """Verify 1-Click Apply redirect (GET /apply/<id>) and reversion (GET /unapply/<id>)."""
    # 1. Test /apply/1 with a custom redirect handler to intercept 302
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(f"{test_server}/apply/1")
    except urllib.error.HTTPError as e:
        assert e.code == 302
        assert "databricks.com/job/1" in e.headers.get("Location")

    # 2. Test /unapply/1
    req = urllib.request.Request(f"{test_server}/unapply/1")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("success") is True
        assert data.get("status") == "unapplied"


def test_http_extract_keywords_api(test_server):
    """Verify POST /api/extract-keywords extracts candidate skills."""
    payload = {
        "text": "Looking for a Python and PyTorch ML Engineer with Docker and Kubernetes skills.",
        "title": "Machine Learning Engineer",
        "location": "Amsterdam, Netherlands"
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{test_server}/api/extract-keywords",
        data=data_bytes,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        result = json.loads(resp.read().decode("utf-8"))
        assert result["success"] is True
        assert "Python" in result["data"]["all_keywords"]
        assert result["data"]["match_score"] > 80.0


def test_http_manual_add_job_api(test_server):
    """Verify POST /api/jobs/add scores and persists a new job."""
    payload = {
        "company": "Axelera AI",
        "title": "Edge AI Compiler Engineer",
        "location": "Eindhoven, Netherlands",
        "url": "https://jobs.ashbyhq.com/axelera-ai/custom-job-123",
        "description": "Python, C++, ONNX, ML inference on Titania hardware."
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{test_server}/api/jobs/add",
        data=data_bytes,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["success"] is True
        assert res["id"] is not None
        assert res["score"] >= 70.0
