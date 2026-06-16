from fastapi import APIRouter, HTTPException

from ..cache import cache_clear, cache_get, cache_set
from ..config import settings
from ..services import github_service

router = APIRouter()


@router.get("")
async def get_commit_activity():
    cache_key = f"commit_activity:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    try:
        repos = await github_service.get_org_repos(settings.github_org)
        activity = await github_service.get_commit_activity(settings.github_org, repos)
        cache_set(cache_key, activity, settings.cache_ttl_seconds)
        return activity
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh_commit_activity():
    cache_clear(f"commit_activity:{settings.github_org}")
    return await get_commit_activity()
