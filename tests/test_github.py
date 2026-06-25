import httpx
import pytest

from api.github import GitHubError, PullRequest, fetch_pull_request, parse_pr_url


def test_parse_full_url():
    assert parse_pr_url("https://github.com/octocat/hello/pull/42") == ("octocat", "hello", 42)


def test_parse_shorthand():
    assert parse_pr_url("octocat/hello#42") == ("octocat", "hello", 42)


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_pr_url("not a pr url")


def test_parse_rejects_github_com_as_non_host():
    # A look-alike host must not be parsed as a real github.com PR URL.
    with pytest.raises(ValueError):
        parse_pr_url("https://evil.com/github.com/octocat/hello/pull/42")


def _client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        accept = request.headers.get("accept", "")
        if "diff" in accept:
            return httpx.Response(200, text="diff --git a/x.py b/x.py\n@@ -1 +1 @@\n-a\n+b\n")
        return httpx.Response(200, json={"title": "Add feature", "body": "Why this PR"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_pull_request_returns_title_body_and_diff():
    pr = fetch_pull_request("https://github.com/octocat/hello/pull/42", client=_client())
    assert isinstance(pr, PullRequest)
    assert pr.title == "Add feature"
    assert pr.body == "Why this PR"
    assert "diff --git a/x.py" in pr.diff


def test_fetch_pull_request_raises_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubError):
        fetch_pull_request("https://github.com/octocat/hello/pull/42", client=client)
