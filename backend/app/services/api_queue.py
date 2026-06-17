import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from ..cache import cache_set
from ..config import settings
from .github_service import (
    get_all_contributors,
    get_commit_activity,
    get_org_details,
    get_org_events,
    get_org_members,
    get_org_repos,
)

logger = logging.getLogger(__name__)

MAX_CALLS_PER_BATCH = 1000
BATCH_INTERVAL = 15 * 60


@dataclass(order=True)
class ApiCall:
    func: Callable[..., Coroutine[Any, Any, Any]] = field(compare=False)
    args: tuple[Any, ...] = field(default_factory=tuple, compare=False)
    kwargs: dict[str, Any] = field(default_factory=dict, compare=False)
    description: str = field(default="", compare=False)

    async def execute(self) -> Any:
        try:
            logger.debug(
                "Executing queued API call: %s",
                self.description or self.func.__name__,
            )
            return await self.func(*self.args, **self.kwargs)
        except Exception as exc:
            logger.error(
                "Queued API call %s failed: %s",
                self.description or self.func.__name__,
                exc,
            )
            raise


_api_queue: deque[ApiCall] = deque()


def enqueue_call(call: ApiCall) -> None:
    _api_queue.append(call)
    logger.info(
        "Enqueued API call: %s (queue size=%d)",
        call.description or call.func.__name__,
        len(_api_queue),
    )


def queue_length() -> int:
    return len(_api_queue)


async def _refresh_org_repos(org: str, priority: Any = None) -> list[dict]:
    repos = await get_org_repos(org, priority=priority)

    from ..routers.repos import _build_result

    result = _build_result(repos)
    result["truncated"] = len(repos) >= settings.max_repos
    result["max_repos"] = settings.max_repos
    cache_set(f"repos:{org}", result, settings.repos_cache_ttl_seconds)
    return repos


async def _process_batch() -> None:
    if not _api_queue:
        logger.debug("Queue empty - nothing to process this batch.")
        return

    batch: list[ApiCall] = []
    for _ in range(min(MAX_CALLS_PER_BATCH, len(_api_queue))):
        batch.append(_api_queue.popleft())

    logger.info(
        "Processing batch of %d API calls (remaining in queue: %d)",
        len(batch),
        len(_api_queue),
    )

    await asyncio.gather(
        *(call.execute() for call in batch),
        return_exceptions=True,
    )


async def process_queue() -> None:
    logger.info(
        "Starting rate-limited API queue processor (batch every %d seconds, max %d calls per batch)",
        BATCH_INTERVAL,
        MAX_CALLS_PER_BATCH,
    )
    while True:
        try:
            if _api_queue:
                await _process_batch()
                await asyncio.sleep(BATCH_INTERVAL)
            else:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected error while processing API queue")
            await asyncio.sleep(5)


def enqueue_org_details(org: str) -> None:
    enqueue_call(
        ApiCall(
            func=get_org_details,
            args=(org,),
            description=f"org details for {org}",
        )
    )


def enqueue_org_members(org: str) -> None:
    enqueue_call(
        ApiCall(
            func=get_org_members,
            args=(org,),
            description=f"org members for {org}",
        )
    )


def enqueue_org_repos(org: str) -> None:
    enqueue_call(
        ApiCall(
            func=_refresh_org_repos,
            args=(org,),
            description=f"org repos for {org}",
        )
    )


def enqueue_org_events(org: str) -> None:
    enqueue_call(
        ApiCall(
            func=get_org_events,
            args=(org,),
            description=f"org events for {org}",
        )
    )


def enqueue_commit_activity(org: str, repos: list[dict]) -> None:
    enqueue_call(
        ApiCall(
            func=get_commit_activity,
            args=(org, repos),
            description=f"commit activity for {org}",
        )
    )


def enqueue_contributors(org: str, repos: list[dict]) -> None:
    enqueue_call(
        ApiCall(
            func=get_all_contributors,
            args=(org, repos),
            description=f"contributors for {org}",
        )
    )
