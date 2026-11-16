from fastapi import APIRouter
from datetime import datetime, timezone

from ..cache import cache_get_or_last_good, cache_set
from ..config import settings
from ..public_data import public_cache_key
from ..services import api_queue

router = APIRouter()

_PUBLIC_ORG_FIELDS = {
    "login",
    "name",
    "description",
    "avatar_url",
    "html_url",
    "blog",
    "location",
    "email",
    "followers",
    "following",
    "public_repos",
    "created_at",
    "updated_at",
    "warning",
    "is_placeholder",
    "refreshed_at",
}


@router.get("")
async def get_org_overview():
    cache_key = public_cache_key("org", settings.github_org)
    if cached := cache_get_or_last_good(
        cache_key,
        "Organization data is being refreshed in the background.",
    ):
        return {
            key: value
            for key, value in cached.items()
            if key in _PUBLIC_ORG_FIELDS
        }

    api_queue.enqueue_org_details(settings.github_org)

    placeholder = {
        "login": settings.github_org,
        "name": settings.github_org,
        "description": None,
        "avatar_url": None,
        "html_url": f"https://github.com/{settings.github_org}",
        "blog": None,
        "location": None,
        "email": None,
        "followers": 0,
        "following": 0,
        "public_repos": 0,
        "created_at": None,
        "updated_at": None,
        "warning": "Organization data is being refreshed in the background.",
        "is_placeholder": True,
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    cache_set(cache_key, placeholder, settings.org_cache_ttl_seconds)
    return placeholder


@router.post("/refresh")
async def refresh_org():
    return await get_org_overview()


def _build_result(org_data: dict) -> dict:
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
        "created_at": org_data.get("created_at"),
        "updated_at": org_data.get("updated_at"),
    }
