from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone

from ..cache import cache_get_or_last_good, cache_set
from ..config import settings
from ..services import api_queue

router = APIRouter()


@router.get("")
async def get_contributors(mode: str = Query(default="org")):
    if mode == "member_wide":
        return await get_member_wide_stats()
    if mode != "org":
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Use 'org' or 'member_wide'.",
        )

    cache_key = f"contributors:{settings.github_org}"
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
    if not settings.member_wide_mode_enabled:
        return {
            "scope": "member_wide",
            "enabled": False,
            "warning": (
                "Member-wide mode is disabled. Set "
                "MEMBER_WIDE_MODE_ENABLED=true to enable it."
            ),
            "is_placeholder": True,
            "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    cache_key = f"member_wide_stats:{settings.github_org}"
    if cached := cache_get_or_last_good(
        cache_key,
        "Member-wide stats are being refreshed in the background.",
    ):
        return cached

    api_queue.enqueue_member_wide_stats(settings.github_org)
    placeholder = {
        "scope": "member_wide",
        "enabled": True,
        "member_count": 0,
        "members": [],
        "totals": {
            "repos": 0,
            "stars": 0,
            "forks": 0,
            "open_issues": 0,
        },
        "warning": "Member-wide stats are being refreshed in the background.",
        "is_placeholder": True,
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    cache_set(
        cache_key,
        placeholder,
        settings.member_wide_cache_ttl_seconds,
    )
    return placeholder


@router.post("/member-wide/refresh")
async def refresh_member_wide_stats():
    return await get_member_wide_stats()
