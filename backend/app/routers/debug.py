from fastapi import APIRouter, HTTPException

from ..cache import cache_info
from ..config import settings
from ..services import github_service, request_queue

router = APIRouter()


@router.get("")
async def debug_info():
    """Returns token scopes, cache info, and basic connectivity info. Useful for diagnosing permission issues."""
    try:
        scopes = await github_service.get_token_scopes()
        org = await github_service.get_org_details(settings.github_org)
        repos_sample = await github_service.get_org_repos(settings.github_org)

        has_repo_scope = any(s in ("repo", "public_repo") for s in scopes)

        return {
            "github_org": settings.github_org,
            "token_scopes": scopes,
            "cache_info": cache_info(),
            "request_queue": request_queue.request_queue.get_status(),
            "warnings": (
                []
                if has_repo_scope
                else [
                    "Token is missing 'repo' scope. Private and internal repositories will NOT be listed. "
                    "Add the 'repo' scope to your Personal Access Token."
                ]
            ),
            "org_accessible": True,
            "org_name": org.get("name") or org.get("login"),
            "repos_visible": len(repos_sample),
            "org_public_repos": org.get("public_repos", 0),
            "org_total_private_repos": org.get("total_private_repos", 0),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/cache-stats")
async def cache_stats():
    """Returns detailed cache statistics"""
    return cache_info()


@router.post("/warm-cache")
async def warm_cache():
    """Manually trigger cache warming"""
    from ..services import cache_warming
    try:
        await cache_warming.warm_cache_if_needed()
        return {"status": "success", "message": "Cache warming completed", "cache_info": cache_info()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache warming failed: {str(e)}")
