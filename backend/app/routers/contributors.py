from fastapi import APIRouter
from datetime import datetime, timezone

from ..cache import cache_get, cache_set
from ..config import settings
from ..services import api_queue

router = APIRouter()


@router.get("")
async def get_contributors():
    cache_key = f"contributors:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    api_queue.enqueue_contributors(settings.github_org)
    placeholder = {
        "contributors": [],
        "total_unique_contributors": 0,
        "total_contributions": 0,
        "warning": "Contributor data is being refreshed in the background.",
        "is_placeholder": True,
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    cache_set(cache_key, placeholder, settings.contributors_cache_ttl_seconds)
    return placeholder


@router.post("/refresh")
async def refresh_contributors():
    return await get_contributors()
