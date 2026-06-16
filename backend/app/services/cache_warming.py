import asyncio
import logging
from typing import Callable, Coroutine, Any

from ..cache import cache_get, cache_set
from ..config import settings
from . import github_service

logger = logging.getLogger(__name__)


async def warm_cache_if_needed() -> None:
    """Warm the cache with frequently accessed data to reduce API calls"""
    try:
        # Check if org data is cached, if not, fetch it
        org_cache_key = f"org:{settings.github_org}"
        if not cache_get(org_cache_key):
            logger.info("Warming org cache...")
            org_data = await github_service.get_org_details(settings.github_org)
            members = await github_service.get_org_members(settings.github_org)
            from ..routers.org import _build_result
            result = _build_result(org_data, members)
            cache_set(org_cache_key, result, settings.org_cache_ttl_seconds)
            
        # Check if repos data is cached, if not, fetch it
        repos_cache_key = f"repos:{settings.github_org}"
        if not cache_get(repos_cache_key):
            logger.info("Warming repos cache...")
            repos = await github_service.get_org_repos(settings.github_org)
            from ..routers.repos import _build_result
            result = _build_result(repos)
            result["truncated"] = len(repos) >= settings.max_repos
            result["max_repos"] = settings.max_repos
            cache_set(repos_cache_key, result, settings.repos_cache_ttl_seconds)
            
        logger.info("Cache warming completed successfully")
    except Exception as e:
        logger.warning(f"Cache warming failed: {e}")


async def schedule_cache_warming(interval_seconds: int = 300) -> None:
    """Schedule periodic cache warming"""
    while True:
        try:
            await warm_cache_if_needed()
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Cache warming scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Cache warming scheduler error: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying