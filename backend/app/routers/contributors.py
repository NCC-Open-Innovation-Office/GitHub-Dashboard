from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone

from ..cache import cache_get_or_last_good, cache_set
from ..config import settings
from ..public_data import public_cache_key
from ..services import api_queue

router = APIRouter()


@router.get("")
async def get_contributors(mode: str = Query(default="org")):
    if mode == "member_wide":
        raise HTTPException(
            status_code=404,
            detail="Member-wide stats are not available on the public dashboard.",
        )
    if mode != "org":
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Use 'org' or 'member_wide'.",
        )

    cache_key = public_cache_key("contributors", settings.github_org)
    if cached := cache_get_or_last_good(
        cache_key,
        "Contributor data is being refreshed in the background.",
    ):
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


@router.get("/member-wide")
async def get_member_wide_stats():
    raise HTTPException(
        status_code=404,
        detail="Member-wide stats are not available on the public dashboard.",
    )


@router.post("/member-wide/refresh")
async def refresh_member_wide_stats():
    return await get_member_wide_stats()
