from collections import Counter

from fastapi import APIRouter, HTTPException

from ..cache import cache_clear, cache_get, cache_set
from ..config import settings
from ..services import github_service

router = APIRouter()


@router.get("")
async def get_repos():
    cache_key = f"repos:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    try:
        repos = await github_service.get_org_repos(settings.github_org)
        result = _build_result(repos)
        result["truncated"] = len(repos) >= settings.max_repos
        result["max_repos"] = settings.max_repos

        if not repos:
            scopes = await github_service.get_token_scopes()
            has_access = any(s in ("repo", "public_repo") for s in scopes)
            if not has_access:
                result["warning"] = (
                    f"No repositories found — your token has scope(s): "
                    f"[{', '.join(scopes) or 'none'}]. "
                    f"Private and internal repos require the 'repo' scope. "
                    f"Update the token at: GitHub → Settings → Developer settings → Personal access tokens."
                )
            else:
                result["warning"] = "This organization appears to have no repositories visible to this token."

        cache_set(cache_key, result, settings.cache_ttl_seconds)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh_repos():
    cache_clear(f"repos:{settings.github_org}")
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
