from fastapi import APIRouter, HTTPException

from ..cache import cache_clear, cache_get, cache_set
from ..config import settings
from ..services import github_service
from ..services.request_queue import Priority

router = APIRouter()


@router.get("")
async def get_org_overview():
    cache_key = f"org:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    try:
        org_data, members = await _fetch_org_data(priority=Priority.HIGH)
        result = _build_result(org_data, members)
        cache_set(cache_key, result, settings.org_cache_ttl_seconds)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh_org():
    cache_clear(f"org:{settings.github_org}")
    return await get_org_overview()


async def _fetch_org_data(priority: Priority = Priority.HIGH):
    import asyncio

    return await asyncio.gather(
        github_service.get_org_details(settings.github_org, priority=priority),
        github_service.get_org_members(settings.github_org, priority=priority),
    )


def _build_result(org_data: dict, members: list) -> dict:
    return {
        "login": org_data["login"],
        "name": org_data.get("name") or org_data["login"],
        "description": org_data.get("description"),
        "avatar_url": org_data.get("avatar_url"),
        "html_url": org_data.get("html_url"),
        "blog": org_data.get("blog"),
        "location": org_data.get("location"),
        "email": org_data.get("email"),
        "followers": org_data.get("followers", 0),
        "following": org_data.get("following", 0),
        "public_repos": org_data.get("public_repos", 0),
        "total_private_repos": org_data.get("total_private_repos", 0),
        "owned_private_repos": org_data.get("owned_private_repos", 0),
        "member_count": len(members),
        "created_at": org_data.get("created_at"),
        "updated_at": org_data.get("updated_at"),
    }
