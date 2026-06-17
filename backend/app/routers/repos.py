from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter

from ..cache import cache_get_or_last_good, cache_set
from ..config import settings
from ..services import api_queue

router = APIRouter()


@router.get("")
async def get_repos():
    """Return repository data, using the background queue for refresh.

    If the data is cached we return it immediately. When the cache is missing
    (or expired) we enqueue a request to fetch the data via the rate‑limited
    ``api_queue`` and return a lightweight placeholder response. The background
    worker will populate the cache within the next 15‑minute batch window.
    """
    cache_key = f"repos:{settings.github_org}"
    if cached := cache_get_or_last_good(cache_key):
        return cached

    # Cache miss – enqueue a refresh and return a placeholder response.
    # The enqueue function simply adds the call to the global queue; the worker
    # will execute it later respecting the 1 000‑call‑per‑15‑min limit.
    api_queue.enqueue_org_repos(settings.github_org)

    placeholder = {
        "repos": [],
        "total": 0,
        "public": 0,
        "private": 0,
        "internal": 0,
        "archived": 0,
        "total_stars": 0,
        "total_forks": 0,
        "total_open_issues": 0,
        "languages": {},
        "truncated": False,
        "max_repos": settings.max_repos,
        "warning": "Repository data is being refreshed in the background.",
        "is_placeholder": True,
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    cache_set(cache_key, placeholder, settings.repos_cache_ttl_seconds)
    return placeholder


@router.post("/refresh")
async def refresh_repos():
    return await get_repos()


def _build_result(repos: list[dict]) -> dict:
    language_counts: Counter = Counter()
    repo_list = []

    for repo in repos:
        if repo.get("language"):
            language_counts[repo["language"]] += 1

        repo_list.append(
            {
                "id": repo["id"],
                "name": repo["name"],
                "full_name": repo["full_name"],
                "description": repo.get("description"),
                "visibility": repo.get("visibility", "public"),
                "private": repo.get("private", False),
                "html_url": repo.get("html_url"),
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "open_issues": repo.get("open_issues_count", 0),
                "watchers": repo.get("watchers_count", 0),
                "topics": repo.get("topics", []),
                "pushed_at": repo.get("pushed_at"),
                "created_at": repo.get("created_at"),
                "archived": repo.get("archived", False),
                "fork": repo.get("fork", False),
                "size": repo.get("size", 0),
                "default_branch": repo.get("default_branch", "main"),
            }
        )

    return {
        "repos": repo_list,
        "total": len(repo_list),
        "public": sum(1 for r in repo_list if r["visibility"] == "public"),
        "private": sum(1 for r in repo_list if r["visibility"] == "private"),
        "internal": sum(1 for r in repo_list if r["visibility"] == "internal"),
        "archived": sum(1 for r in repo_list if r["archived"]),
        "total_stars": sum(r["stars"] for r in repo_list),
        "total_forks": sum(r["forks"] for r in repo_list),
        "total_open_issues": sum(r["open_issues"] for r in repo_list),
        "languages": dict(language_counts.most_common(10)),
    }
