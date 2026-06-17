import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings
from .request_queue import request_queue, Priority

BASE_URL = "https://api.github.com"
_SEMAPHORE_LIMIT = 10  # concurrent requests for contributor fetching


def _is_bot_login(login: str | None) -> bool:
    if not login:
        return False
    return "[bot]" in login.lower()


def _rate_limit_message(resp: httpx.Response) -> str:
    reset_ts = resp.headers.get("X-RateLimit-Reset")
    if reset_ts:
        reset_dt = datetime.fromtimestamp(int(reset_ts), tz=timezone.utc)
        delta = reset_dt - datetime.now(tz=timezone.utc)
        mins = max(0, int(delta.total_seconds() // 60))
        secs = max(0, int(delta.total_seconds() % 60))
        return (
            f"GitHub API rate limit exceeded. "
            f"Resets in {mins}m {secs}s (at {reset_dt.strftime('%H:%M UTC')}). "
            f"Wait and then click Refresh All."
        )
    return "GitHub API rate limit exceeded. Wait a few minutes and click Refresh All."



def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _paginate(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
    max_items: int | None = None,
    priority: Priority = Priority.HIGH,
) -> list[dict]:
    """Follow GitHub Link-header pagination and return results.

    Stops gracefully when:
    - max_items is reached (returns the slice collected so far)
    - GitHub returns 403 / 429 (secondary rate limit) mid-pagination
    """
    results: list[dict] = []
    next_url: str | None = url
    first = True

    while next_url:
        if max_items and len(results) >= max_items:
            break

        resp = await request_queue.add_request(
            priority,
            client.get,
            next_url,
            headers=_headers(),
            params=params if first else None,
        )

        # Stop cleanly on secondary rate-limit or permission boundary
        if resp.status_code in (403, 429):
            if first:
                # 403/429 on the very first page = hard stop; surface the real error.
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                msg = body.get("message", "")

                # Rate limit (primary or secondary)
                if resp.status_code == 429 or "rate limit" in msg.lower():
                    raise Exception(_rate_limit_message(resp))

                # SAML / SSO enforcement
                if "SAML" in msg or "single sign-on" in msg.lower() or "SSO" in msg:
                    raise PermissionError(
                        f"SSO authorization required for this organization. "
                        f"Go to GitHub \u2192 Settings \u2192 Personal access tokens \u2192 "
                        f"Configure SSO \u2192 Authorize, then restart the app."
                    )

                raise PermissionError(
                    f"GitHub API 403: {msg or 'Access denied. Check token scopes and org membership.'}"
                )
            # Rate-limit mid-pagination — return what we collected so far
            break

        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return [data]

        # Small delay to stay well under GitHub's secondary rate limit
        await asyncio.sleep(0.05)

        first = False
        next_url = None
        link_header = resp.headers.get("Link", "")
        if 'rel="next"' in link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    break

    return results[:max_items] if max_items else results


async def get_token_scopes(priority: Priority = Priority.HIGH) -> list[str]:
    """Return the OAuth scopes of the configured token.
    Uses /rate_limit — a free endpoint that returns X-OAuth-Scopes headers."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await request_queue.add_request(priority, client.get, f"{BASE_URL}/rate_limit", headers=_headers())
        raw = resp.headers.get("X-OAuth-Scopes", "")
        return [s.strip() for s in raw.split(",") if s.strip()]


async def get_org_details(org: str, priority: Priority = Priority.HIGH) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await request_queue.add_request(priority, client.get, f"{BASE_URL}/orgs/{org}", headers=_headers())
        if resp.status_code in (403, 429):
            try:
                body = resp.json()
            except Exception:
                body = {}
            msg = body.get("message", "")
            if resp.status_code == 429 or "rate limit" in msg.lower():
                raise Exception(_rate_limit_message(resp))
            if "SAML" in msg or "single sign-on" in msg.lower() or "SSO" in msg:
                raise PermissionError(
                    f"SSO authorization required for '{org}'. "
                    f"Go to GitHub \u2192 Settings \u2192 Personal access tokens \u2192 "
                    f"Configure SSO \u2192 Authorize for '{org}', then restart the app."
                )
            raise PermissionError(
                f"GitHub API 403 for org '{org}': {msg or 'Access denied. Check token scopes and org membership.'}"
            )
        resp.raise_for_status()
        return resp.json()


async def get_org_members(org: str, priority: Priority = Priority.HIGH) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await _paginate(
            client,
            f"{BASE_URL}/orgs/{org}/members",
            {"per_page": 100, "role": "all"},
            priority=priority,
        )


async def get_org_repos(org: str, priority: Priority = Priority.HIGH) -> list[dict]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await _paginate(
            client,
            f"{BASE_URL}/orgs/{org}/repos",
            {"type": "all", "per_page": 100, "sort": "pushed"},
            max_items=settings.max_repos,
            priority=priority,
        )


async def _fetch_repo_contributors(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    org: str,
    repo_name: str,
    priority: Priority = Priority.HIGH,
) -> list[dict]:
    async with semaphore:
        try:
            resp = await request_queue.add_request(
                priority,
                client.get,
                f"{BASE_URL}/repos/{org}/{repo_name}/contributors",
                headers=_headers(),
                params={"per_page": 100, "anon": "false"},
            )
            if resp.status_code in (204, 409):  # empty or uninitialized repo
                return []
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError):
            return []


async def get_all_contributors(org: str, repos: list[dict], priority: Priority = Priority.HIGH) -> list[dict]:
    """Aggregate contributor commit counts across every repository."""
    semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)
    totals: dict[str, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [
            _fetch_repo_contributors(client, semaphore, org, r["name"], priority=priority)
            for r in repos
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if not isinstance(result, list):
            continue
        for contributor in result:
            login = contributor.get("login")
            if _is_bot_login(login):
                continue
            if login not in totals:
                totals[login] = {
                    "login": login,
                    "avatar_url": contributor.get("avatar_url"),
                    "html_url": contributor.get("html_url"),
                    "contributions": 0,
                    "type": contributor.get("type", "User"),
                }
            totals[login]["contributions"] += contributor.get("contributions", 0)

    return sorted(totals.values(), key=lambda x: x["contributions"], reverse=True)[:25]


async def get_org_events(org: str, priority: Priority = Priority.HIGH) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await request_queue.add_request(
            priority,
            client.get,
            f"{BASE_URL}/orgs/{org}/events",
            headers=_headers(),
            params={"per_page": 100},
        )
        resp.raise_for_status()
        return resp.json()


async def get_commit_activity(org: str, repos: list[dict], priority: Priority = Priority.HIGH) -> dict:
    """Return per-repo and aggregated weekly commit activity for the top repos."""
    top_repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[
        :8
    ]
    semaphore = asyncio.Semaphore(3)

    async def _fetch(client: httpx.AsyncClient, repo_name: str):
        async with semaphore:
            try:
                resp = await request_queue.add_request(
                    priority,
                    client.get,
                    f"{BASE_URL}/repos/{org}/{repo_name}/stats/commit_activity",
                    headers=_headers(),
                )
                if resp.status_code == 200:
                    return repo_name, resp.json()
                return repo_name, []
            except (httpx.HTTPStatusError, httpx.RequestError):
                return repo_name, []

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [_fetch(client, r["name"]) for r in top_repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    per_repo: dict[str, list] = {}
    weekly_totals: dict[int, int] = {}

    for result in results:
        if not isinstance(result, tuple):
            continue
        repo_name, data = result
        if not isinstance(data, list) or not data:
            continue
        per_repo[repo_name] = data
        for week in data[-26:]:
            ts: int = week.get("week", 0)
            weekly_totals[ts] = weekly_totals.get(ts, 0) + week.get("total", 0)

    aggregated = [
        {"week": ts, "commits": count}
        for ts, count in sorted(weekly_totals.items())
    ]

    return {"per_repo": per_repo, "aggregated": aggregated}
