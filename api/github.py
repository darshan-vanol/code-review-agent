from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

_API = "https://api.github.com"
_TIMEOUT_S = 30.0
# Anchor github.com to the start or a scheme separator so a host like
# evil.com/github.com/o/r/pull/1 does not parse as a github.com PR.
_FULL_URL = re.compile(r"(?:^|://)github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_SHORTHAND = re.compile(r"^([^/]+)/([^/#]+)#(\d+)$")


class GitHubError(RuntimeError):
    """Raised when the GitHub API returns a non-success response."""


@dataclass
class PullRequest:
    title: str
    body: str
    diff: str


def parse_pr_url(url: str) -> tuple[str, str, int]:
    m = _FULL_URL.search(url) or _SHORTHAND.match(url.strip())
    if not m:
        raise ValueError(f"Not a GitHub PR URL or owner/repo#n shorthand: {url!r}")
    return m.group(1), m.group(2), int(m.group(3))


def _headers(token: str | None, accept: str) -> dict[str, str]:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_pull_request(
    url: str, token: str | None = None, client: httpx.Client | None = None
) -> PullRequest:
    owner, repo, number = parse_pr_url(url)
    client = client or httpx.Client(timeout=_TIMEOUT_S)
    endpoint = f"{_API}/repos/{owner}/{repo}/pulls/{number}"

    meta = client.get(endpoint, headers=_headers(token, "application/vnd.github+json"))
    if meta.status_code != 200:
        raise GitHubError(f"GitHub metadata fetch failed ({meta.status_code}) for {url}")

    diff = client.get(endpoint, headers=_headers(token, "application/vnd.github.v3.diff"))
    if diff.status_code != 200:
        raise GitHubError(f"GitHub diff fetch failed ({diff.status_code}) for {url}")

    payload = meta.json()
    return PullRequest(
        title=payload.get("title") or "",
        body=payload.get("body") or "",
        diff=diff.text,
    )
