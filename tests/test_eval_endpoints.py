import json

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_REPORT = {
    "aggregate": {"faithfulness": 0.9, "answer_correctness": 0.85},
    "threshold": 0.75,
    "passed": True,
    "items": [{"id": "01-x", "faithfulness": 0.9, "answer_correctness": 0.85}],
}


def _seed(tmp_path, monkeypatch, n=1):
    monkeypatch.setenv("EVAL_REPORTS_DIR", str(tmp_path))
    for i in range(1, n + 1):
        (tmp_path / f"{i}.json").write_text(json.dumps(_REPORT))


def test_list_reports_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_REPORTS_DIR", str(tmp_path / "nope"))
    r = client.get("/eval/reports")
    assert r.status_code == 200
    assert r.json() == []


def test_list_reports_returns_summaries(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, n=2)
    r = client.get("/eval/reports")
    body = r.json()
    assert len(body) == 2
    assert body[0]["id"] == "1"
    assert body[0]["passed"] is True
    assert body[0]["aggregate"]["faithfulness"] == 0.9


def test_get_report_returns_full(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    r = client.get("/eval/reports/1")
    assert r.status_code == 200
    assert r.json()["items"][0]["id"] == "01-x"


def test_get_report_unknown_is_404(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    r = client.get("/eval/reports/999")
    assert r.status_code == 404


def test_cors_header_present_for_web_origin():
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
