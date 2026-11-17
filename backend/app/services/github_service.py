import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import settings
from .request_queue import request_queue, Priority

BASE_URL = "https://api.github.com"
_SEMAPHORE_LIMIT = 10  # concurrent requests for contributor fetching
_REPO_PAGE_TIMEOUT_SECONDS = 120

# Search allows 30 requests per minute and flags bursts as abuse, so every
# search call goes through one lock and a minimum gap, even across jobs.
_SEARCH_MIN_INTERVAL = 2.2
_search_lock = asyncio.Lock()
_last_search_at = 0.0


async def _search(
    client: httpx.AsyncClient, kind: str, params: dict, priority: Priority
) -> httpx.Response:
    global _last_search_at
    async with _search_lock:
        for attempt in range(4):
            wait = _SEARCH_MIN_INTERVAL - (time.monotonic() - _last_search_at)
            if wait > 0:
                await asyncio.sleep(wait)
            resp = await request_queue.add_request(
                priority,
                client.get,
                f"{BASE_URL}/search/{kind}",
                headers=_headers(),
                params=params,
            )
            _last_search_at = time.monotonic()
            if resp.status_code in (403, 429) and attempt < 3:
                await asyncio.sleep(30)
                continue
            return resp


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


def _next_link(link_header: str) -> str | None:
    if 'rel="next"' not in link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


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
        next_url = _next_link(resp.headers.get("Link", ""))

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


async def get_member_org_activity_counts(
    org: str,
    logins: list[str],
    since: datetime,
    priority: Priority = Priority.HIGH,
) -> dict[str, int]:
    """Count each member's commits in the org's private and internal repos
    since the given date. Commit search treats is:private as covering both."""
    counts = {login: 0 for login in logins}
    async with httpx.AsyncClient(timeout=60.0) as client:
        for login in logins:
            resp = await _search(
                client,
                "commits",
                {
                    "q": f"org:{org} is:private author:{login} "
                    f"committer-date:>={since.date().isoformat()}",
                    "per_page": 1,
                },
                priority,
            )
            resp.raise_for_status()
            counts[login] += resp.json()["total_count"]
    return counts


async def get_member_contributions(
    org: str, priority: Priority = Priority.HIGH
) -> dict:
    now = datetime.now(tz=timezone.utc)

    def years_ago(years: int) -> datetime:
        try:
            return now.replace(year=now.year - years)
        except ValueError:
            return now.replace(year=now.year - years, day=28)

    # GitHub limits each contributionsCollection to one year, so request one
    # aliased window per year and add them together.
    years = max(1, settings.member_contribution_years)
    start = years_ago(years)
    # Each member costs one contribution collection per year; keep a page
    # near 40 collections to stay under GitHub's GraphQL resource limits.
    page_size = max(1, 40 // years)
    windows = "\n".join(
        f'y{i}: contributionsCollection(from: "{years_ago(i + 1).isoformat()}", '
        f'to: "{years_ago(i).isoformat()}") '
        "{ totalCommitContributions }"
        for i in range(years)
    )
    query = """
        query($org: String!, $after: String) {
          organization(login: $org) {
            membersWithRole(first: %d, after: $after) {
              totalCount
              pageInfo { hasNextPage endCursor }
              nodes {
                login avatarUrl url
                %s
              }
            }
          }
        }
    """ % (page_size, windows)
    members = []
    seen_logins = set()
    cursor = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            for attempt in range(4):
                response = await request_queue.add_request(
                    priority,
                    client.post,
                    f"{BASE_URL}/graphql",
                    headers=_headers(),
                    json={
                        "query": query,
                        "variables": {
                            "org": org,
                            "after": cursor,
                        },
                    },
                )
                # Retry transient 5xx errors and secondary rate limits.
                if attempt == 3 or not (
                    response.status_code >= 500 or response.status_code in (403, 429)
                ):
                    break
                retry_after = response.headers.get("retry-after", "")
                await asyncio.sleep(
                    int(retry_after) if retry_after.isdigit() else 60
                    if response.status_code in (403, 429) else 5
                )
            response.raise_for_status()
            body = response.json()
            if body.get("errors"):
                raise RuntimeError(f"GitHub GraphQL contributor query failed: {body['errors']}")
            organization = body["data"]["organization"]
            if organization is None:
                raise RuntimeError(f"GitHub organization {org} is not accessible to the token")
            connection = organization["membersWithRole"]
            for member in connection["nodes"]:
                login = member["login"]
                if login.casefold() in seen_logins:
                    raise RuntimeError("GitHub returned duplicate organization members")
                seen_logins.add(login.casefold())
                members.append({
                    "login": login,
                    "avatar_url": member["avatarUrl"],
                    "html_url": member["url"],
                    "contributions": sum(
                        member[f"y{i}"]["totalCommitContributions"]
                        for i in range(years)
                    ),
                })
            page = connection["pageInfo"]
            if not page["hasNextPage"]:
                if len(members) != connection["totalCount"]:
                    raise RuntimeError("GitHub organization member list changed during pagination")
                break
            next_cursor = page["endCursor"]
            if not next_cursor or next_cursor == cursor:
                raise RuntimeError("GitHub organization member pagination did not advance")
            cursor = next_cursor
    if settings.include_private_activity:
        # Profile commit counts already include public repositories, so add
        # only commits in the org's private and internal repositories.
        counts = await get_member_org_activity_counts(
            org, [m["login"] for m in members], start, priority
        )
        for member in members:
            member["contributions"] += counts[member["login"]]
    return {"members": members, "from": start.isoformat(), "to": now.isoformat()}


async def get_org_repos(org: str, priority: Priority = Priority.HIGH) -> list[dict]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await _paginate(
            client,
            f"{BASE_URL}/orgs/{org}/repos",
            {"type": "all", "per_page": 100, "sort": "pushed"},
            max_items=settings.max_repos,
            priority=priority,
        )


async def get_user_repos(
    username: str,
    max_items: int | None = None,
    priority: Priority = Priority.HIGH,
) -> list[dict]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await _paginate(
            client,
            f"{BASE_URL}/users/{username}/repos",
            {"type": "owner", "per_page": 100, "sort": "updated"},
            max_items=max_items,
            priority=priority,
        )


async def get_org_repos_page(
    org: str,
    next_url: str | None = None,
    priority: Priority = Priority.HIGH,
) -> tuple[list[dict], str | None]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        url = next_url or f"{BASE_URL}/orgs/{org}/repos"
        try:
            resp = await asyncio.wait_for(
                request_queue.add_request(
                    priority,
                    client.get,
                    url,
                    headers=_headers(),
                    params=None
                    if next_url
                    else {"type": "all", "per_page": 100, "sort": "pushed"},
                ),
                timeout=_REPO_PAGE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Timed out fetching a repo page after {_REPO_PAGE_TIMEOUT_SECONDS} seconds"
            ) from exc
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return [], None
        await asyncio.sleep(0.05)
        return data, _next_link(resp.headers.get("Link", ""))


async def probe_org_repos_page(
    org: str,
    next_url: str | None = None,
    priority: Priority = Priority.HIGH,
) -> dict[str, Any]:
    started_at = datetime.now(tz=timezone.utc)
    page, next_link = await get_org_repos_page(
        org,
        next_url=next_url,
        priority=priority,
    )
    finished_at = datetime.now(tz=timezone.utc)
    return {
        "count": len(page),
        "next_url": next_link,
        "sample_repo_names": [repo.get("name") for repo in page[:10]],
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(
            (finished_at - started_at).total_seconds(),
            3,
        ),
    }


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


async def search_non_public_activity(
    org: str, repos: list[dict], priority: Priority = Priority.HIGH
) -> list[dict]:
    from ..routers.activity import _format_search_results

    events = []
    # Commit search has no is:internal filter, but is:private also matches
    # commits in internal repositories.
    queries = [
        ("commits", "committer-date", f"org:{org} is:private"),
        *(
            ("issues", "created", f"org:{org} is:{visibility} is:{item_type}")
            for visibility in ("private", "internal")
            for item_type in ("issue", "pull-request")
        ),
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        for kind, sort, query in queries:
            # Search can time out and flag results as incomplete; retry briefly.
            for attempt in range(3):
                resp = await _search(
                    client,
                    kind,
                    {
                        "q": query,
                        "sort": sort,
                        "order": "desc",
                        "per_page": 100,
                    },
                    priority,
                )
                resp.raise_for_status()
                result = resp.json()
                if not result.get("incomplete_results"):
                    break
                if attempt == 2:
                    raise RuntimeError(f"GitHub {kind} search returned incomplete results")
                await asyncio.sleep(2)
            events.extend(_format_search_results(result["items"], org, kind))
    return list({event["id"]: event for event in events}.values())


async def get_commit_activity(
    org: str,
    include_private: bool,
    days: int = 30,
    priority: Priority = Priority.HIGH,
) -> dict:
    """Return daily commit counts for the last ``days`` days (UTC) in the org.

    One commit search per day; search is limited to 30 requests per minute.
    """
    today = datetime.now(tz=timezone.utc).date()
    visibility = "" if include_private else " is:public"
    aggregated = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            resp = await _search(
                client,
                "commits",
                {
                    "q": f"org:{org}{visibility} committer-date:{day.isoformat()}",
                    "per_page": 1,
                },
                priority,
            )
            resp.raise_for_status()
            midnight = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            aggregated.append(
                {"date": int(midnight.timestamp()), "commits": resp.json()["total_count"]}
            )
    return {"aggregated": aggregated}
