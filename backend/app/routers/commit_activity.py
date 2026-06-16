from fastapi import APIRouter, HTTPException

from ..cache import cache_clear, cache_get, cache_set
from ..config import settings
from ..services import github_service
from ..services.request_queue import Priority

router = APIRouter()


@router.get("")
async def get_commit_activity():
    cache_key = f"commit_activity:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    try:
        repos = await github_service.get_org_repos(settings.github_org, priority=Priority.HIGH)
        activity = await github_service.get_commit_activity(settings.github_org, repos, priority=Priority.HIGH)
        cache_set(cache_key, activity, settings.commit_activity_cache_ttl_seconds)
        return activity
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh_commit_activity():
    cache_clear(f"commit_activity:{settings.github_org}")
    return await get_commit_activity()
