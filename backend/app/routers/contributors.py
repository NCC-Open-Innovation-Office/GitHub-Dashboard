from fastapi import APIRouter, HTTPException

from ..cache import cache_clear, cache_get, cache_set
from ..config import settings
from ..services import github_service

router = APIRouter()


@router.get("")
async def get_contributors():
    cache_key = f"contributors:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    try:
        repos = await github_service.get_org_repos(settings.github_org)
        # Only pull contributor data from the most recently active non-archived repos
        # to avoid exhausting the GitHub API rate limit on large orgs.
        active_repos = [r for r in repos if not r.get("archived", False)][:150]
        contributors = await github_service.get_all_contributors(
            settings.github_org, active_repos
        )
        result = {
            "contributors": contributors,
            "total_unique_contributors": len(contributors),
            "total_contributions": sum(c["contributions"] for c in contributors),
        }
        cache_set(cache_key, result, settings.contributors_cache_ttl_seconds)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh_contributors():
    cache_clear(f"contributors:{settings.github_org}")
    return await get_contributors()
