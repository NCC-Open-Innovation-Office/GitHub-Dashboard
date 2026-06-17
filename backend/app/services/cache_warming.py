import asyncio
import logging
from datetime import datetime, timezone

from ..cache import cache_get, cache_set, _expiry
from ..config import settings
from . import api_queue
from . import github_service
from .request_queue import Priority

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


async def warm_cache_if_needed(priority: Priority = Priority.LOW) -> None:
    """Warm the cache with frequently accessed data to reduce API calls"""
    # Check if org data is cached or near expiry
    org_cache_key = f"org:{settings.github_org}"
    if _is_needs_refresh(org_cache_key):
        logger.info("Warming org cache...")
        org_data = await github_service.get_org_details(
            settings.github_org,
            priority=priority,
        )
        members = await github_service.get_org_members(
            settings.github_org,
            priority=priority,
        )
        from ..routers.org import _build_result as _build_org_result

        result = _build_org_result(org_data, members)
        result["is_placeholder"] = False
        result["refreshed_at"] = _now_iso()
        cache_set(org_cache_key, result, settings.org_cache_ttl_seconds)

    # Check if repos data is cached or near expiry
    repos_cache_key = f"repos:{settings.github_org}"
    if _is_needs_refresh(repos_cache_key):
        logger.info("Queueing incremental repos refresh...")
        api_queue.enqueue_org_repos(settings.github_org)

    logger.info("Cache warming completed successfully")


def _is_needs_refresh(key: str, threshold_seconds: int = 60) -> bool:
    """Check if a cache item is missing or near expiry (within threshold)"""
    val = cache_get(key)
    if val is None:
        return True

    expiry = _expiry.get(key)
    if expiry:
        remaining = (expiry - datetime.now(tz=timezone.utc)).total_seconds()
        return remaining < threshold_seconds
    return True


async def schedule_cache_warming(interval_seconds: int = 300) -> None:
    """Schedule periodic cache warming and intelligent refreshing"""
    # Initial warming on startup
    await warm_cache_if_needed(priority=Priority.MEDIUM)

    while True:
        try:
            # Check for near-expiry items every 60 seconds
            result = await asyncio.gather(
                warm_cache_if_needed(priority=Priority.LOW),
                return_exceptions=True,
            )
            if result and isinstance(result[0], Exception):
                logger.error(
                    "Cache warming scheduler error: %s",
                    result[0],
                )
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Cache warming scheduler cancelled")
            break
