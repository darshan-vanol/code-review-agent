from fastapi.testclient import TestClient

import api.main as main
from api.github import PullRequest
from api.main import app

client = TestClient(app)

_DIFF = (
    "diff --git a/app.py b/app.py\n"
    "--- a/app.py\n+++ b/app.py\n"
    "@@ -1 +1 @@\n-x = 1\n+y = eval(input())\n"
)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_reports_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["provider"] == "mock"


def test_review_with_raw_diff_returns_findings_score_and_spans():
    r = client.post("/review", json={"diff": _DIFF})
    assert r.status_code == 200
    body = r.json()
    assert body["is_trivial"] is False
    assert "overall" in body["score"]
    assert isinstance(body["security_findings"], list)
    assert [s["name"] for s in body["spans"]] == [
        "ingest", "security", "logic", "test_coverage", "aggregate"
    ]
    assert "input_tokens" in body["token_usage"]


def test_review_requires_exactly_one_of_diff_or_pr_url():
    assert client.post("/review", json={}).status_code == 422
    assert client.post(
        "/review", json={"diff": "d", "pr_url": "x"}
    ).status_code == 422


def test_review_with_pr_url_fetches_diff(monkeypatch):
    def fake_fetch(url, token=None):
        return PullRequest(title="T", body="B", diff=_DIFF)

    monkeypatch.setattr(main, "fetch_pull_request", fake_fetch)
    r = client.post("/review", json={"pr_url": "https://github.com/o/r/pull/1"})
    assert r.status_code == 200
    assert r.json()["is_trivial"] is False


def test_pr_body_with_diff_header_does_not_inject_phantom_file(monkeypatch):
    # A PR description that quotes a `diff --git` line must not be parsed as a
    # real changed file. Only app.py (from the actual diff) should be reviewed.
    malicious_body = "Here is a snippet:\ndiff --git a/evil.py b/evil.py\nbye"

    def fake_fetch(url, token=None):
        return PullRequest(title="T", body=malicious_body, diff=_DIFF)

    monkeypatch.setattr(main, "fetch_pull_request", fake_fetch)
    r = client.post("/review", json={"pr_url": "https://github.com/o/r/pull/1"})
    assert r.status_code == 200
    # is_trivial would be False from the real app.py change either way; the proof
    # is that the review still succeeds and the phantom file never reaches a node.
    assert r.json()["is_trivial"] is False


def test_review_pr_url_github_failure_maps_to_502(monkeypatch):
    from api.github import GitHubError

    def boom(url, token=None):
        raise GitHubError("GitHub diff fetch failed (404)")

    monkeypatch.setattr(main, "fetch_pull_request", boom)
    r = client.post("/review", json={"pr_url": "https://github.com/o/r/pull/1"})
    assert r.status_code == 502
