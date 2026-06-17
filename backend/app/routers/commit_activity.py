from fastapi import APIRouter
from datetime import datetime, timezone

from ..cache import cache_clear, cache_get, cache_set
from ..config import settings
from ..services import api_queue

router = APIRouter()


@router.get("")
async def get_commit_activity():
    cache_key = f"commit_activity:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    api_queue.enqueue_commit_activity(settings.github_org)
    placeholder = {
        "per_repo": {},
        "aggregated": [],
        "warning": "Commit activity is being refreshed in the background.",
        "is_placeholder": True,
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    cache_set(
        cache_key,
        placeholder,
        settings.commit_activity_cache_ttl_seconds,
    )
    return placeholder


@router.post("/refresh")
async def refresh_commit_activity():
    cache_clear(f"commit_activity:{settings.github_org}")
    return await get_commit_activity()
