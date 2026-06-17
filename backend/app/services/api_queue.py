import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from ..cache import cache_get, cache_set
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
JOB_TIMEOUT_SECONDS = 30 * 60


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
_enqueued_keys: set[str] = set()
_running_keys: set[str] = set()
_job_status: dict[str, dict[str, Any]] = {}


def enqueue_call(call: ApiCall) -> None:
    _api_queue.append(call)
    logger.info(
        "Enqueued API call: %s (queue size=%d)",
        call.description or call.func.__name__,
        len(_api_queue),
    )


def _ensure_status(key: str) -> dict[str, Any]:
    return _job_status.setdefault(
        key,
        {
            "state": "idle",
            "enqueued_at": None,
            "started_at": None,
            "finished_at": None,
            "last_success_at": None,
            "last_error": None,
            "run_count": 0,
        },
    )


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def enqueue_unique(key: str, call: ApiCall) -> bool:
    """Enqueue a call once for a given key until it is executed."""
    if key in _enqueued_keys:
        return False
    _enqueued_keys.add(key)
    status = _ensure_status(key)
    status["state"] = "queued"
    status["enqueued_at"] = _now_iso()
    enqueue_call(call)
    return True


def queue_length() -> int:
    return len(_api_queue)


async def _refresh_org_repos(org: str, priority: Any = None) -> list[dict]:
    repos = await get_org_repos(org, priority=priority)

    from ..routers.repos import _build_result

    result = _build_result(repos)
    result["truncated"] = len(repos) >= settings.max_repos
    result["max_repos"] = settings.max_repos
    result["is_placeholder"] = False
    result["refreshed_at"] = _now_iso()
    cache_set(f"raw_repos:{org}", repos, settings.repos_cache_ttl_seconds)
    cache_set(f"repos:{org}", result, settings.repos_cache_ttl_seconds)
    return repos


async def _get_or_refresh_raw_repos(org: str) -> list[dict]:
    if cached := cache_get(f"raw_repos:{org}"):
        return cached

    repos_key = f"repos:{org}"
    wait_deadline = asyncio.get_running_loop().time() + 120
    while repos_key in _enqueued_keys or repos_key in _running_keys:
        if cached := cache_get(f"raw_repos:{org}"):
            return cached
        if asyncio.get_running_loop().time() >= wait_deadline:
            break
        await asyncio.sleep(1)

    if cached := cache_get(f"raw_repos:{org}"):
        return cached
    return await _refresh_org_repos(org)


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

    async def _execute(call: ApiCall) -> Any:
        key = call.description or call.func.__name__
        status = _ensure_status(key)
        _running_keys.add(key)
        status["state"] = "running"
        status["started_at"] = _now_iso()
        status["run_count"] += 1
        task = asyncio.create_task(call.execute())
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=JOB_TIMEOUT_SECONDS,
            )
            exc = task.exception()
            if exc is not None:
                status["state"] = "failed"
                status["finished_at"] = _now_iso()
                status["last_error"] = str(exc)
                return None

            result = task.result()
            status["state"] = "succeeded"
            status["finished_at"] = _now_iso()
            status["last_success_at"] = status["finished_at"]
            status["last_error"] = None
            return result
        except asyncio.TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            status["state"] = "failed"
            status["finished_at"] = _now_iso()
            status["last_error"] = (
                f"Timed out after {JOB_TIMEOUT_SECONDS} seconds"
            )
            logger.error("Queued API call %s timed out", key)
            return None
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        finally:
            _running_keys.discard(key)
            _enqueued_keys.discard(key)

    await asyncio.gather(
        *(_execute(call) for call in batch),
        return_exceptions=True,
    )


async def process_queue() -> None:
    logger.info(
        (
            "Starting rate-limited API queue processor "
            "(batch every %d seconds, max %d calls per batch)"
        ),
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
            logger.info("API queue processor cancelled")
            break


def enqueue_org_details(org: str) -> None:
    key = f"org:{org}"
    enqueue_unique(
        key,
        ApiCall(
            func=_refresh_org_overview,
            args=(org,),
            description=key,
        )
    )


def enqueue_org_members(org: str) -> None:
    key = f"org_members:{org}"
    enqueue_unique(
        key,
        ApiCall(
            func=get_org_members,
            args=(org,),
            description=key,
        )
    )


def enqueue_org_repos(org: str) -> None:
    key = f"repos:{org}"
    enqueue_unique(
        key,
        ApiCall(
            func=_refresh_org_repos,
            args=(org,),
            description=key,
        )
    )


def enqueue_org_events(org: str) -> None:
    key = f"activity:{org}"
    enqueue_unique(
        key,
        ApiCall(
            func=_refresh_activity,
            args=(org,),
            description=key,
        )
    )


def enqueue_commit_activity(org: str) -> None:
    enqueue_org_repos(org)
    key = f"commit_activity:{org}"
    enqueue_unique(
        key,
        ApiCall(
            func=_refresh_commit_activity,
            args=(org,),
            description=key,
        )
    )


def enqueue_contributors(org: str) -> None:
    enqueue_org_repos(org)
    key = f"contributors:{org}"
    enqueue_unique(
        key,
        ApiCall(
            func=_refresh_contributors,
            args=(org,),
            description=key,
        )
    )


def get_queue_status() -> dict[str, Any]:
    return {
        "queue_size": len(_api_queue),
        "enqueued_keys": sorted(_enqueued_keys),
        "running_keys": sorted(_running_keys),
        "batch_interval_seconds": BATCH_INTERVAL,
        "max_calls_per_batch": MAX_CALLS_PER_BATCH,
        "job_timeout_seconds": JOB_TIMEOUT_SECONDS,
        "jobs": _job_status,
    }


async def _refresh_org_overview(org: str) -> dict:
    org_data = await get_org_details(org)
    members = await get_org_members(org)

    from ..routers.org import _build_result

    result = _build_result(org_data, members)
    result["is_placeholder"] = False
    result["refreshed_at"] = _now_iso()
    cache_set(f"org:{org}", result, settings.org_cache_ttl_seconds)
    return result


async def _refresh_activity(org: str) -> dict:
    events = await get_org_events(org)
    interesting = {
        "PushEvent",
        "PullRequestEvent",
        "IssuesEvent",
        "CreateEvent",
        "ReleaseEvent",
        "ForkEvent",
        "WatchEvent",
        "PullRequestReviewEvent",
        "DeleteEvent",
    }

    formatted = []
    for event in events:
        event_type = event.get("type", "")
        if event_type not in interesting:
            continue

        payload = event.get("payload", {})
        extracted: dict[str, Any] = {}
        if event_type == "PushEvent":
            commits = payload.get("commits", [])
            extracted = {
                "ref": payload.get("ref", ""),
                "commit_count": len(commits),
                "message": commits[0]["message"][:120] if commits else "",
            }
        elif event_type == "PullRequestEvent":
            pr = payload.get("pull_request", {})
            extracted = {
                "action": payload.get("action"),
                "title": pr.get("title", ""),
                "number": pr.get("number"),
                "html_url": pr.get("html_url", ""),
                "merged": pr.get("merged", False),
            }
        elif event_type == "IssuesEvent":
            issue = payload.get("issue", {})
            extracted = {
                "action": payload.get("action"),
                "title": issue.get("title", ""),
                "number": issue.get("number"),
                "html_url": issue.get("html_url", ""),
            }
        elif event_type == "CreateEvent":
            extracted = {
                "ref_type": payload.get("ref_type"),
                "ref": payload.get("ref"),
            }
        elif event_type == "ReleaseEvent":
            release = payload.get("release", {})
            extracted = {
                "action": payload.get("action"),
                "tag_name": release.get("tag_name"),
                "name": release.get("name"),
                "html_url": release.get("html_url", ""),
            }
        elif event_type == "ForkEvent":
            forkee = payload.get("forkee", {})
            extracted = {"forkee": forkee.get("full_name", "")}

        actor = event.get("actor", {})
        login = actor.get("login", "unknown")
        formatted.append(
            {
                "id": event.get("id"),
                "type": event_type,
                "actor": {
                    "login": login,
                    "avatar_url": actor.get("avatar_url"),
                    "url": f"https://github.com/{login}",
                },
                "repo": event.get("repo", {}).get("name", ""),
                "created_at": event.get("created_at"),
                "payload": extracted,
            }
        )

    result = {
        "events": formatted[:50],
        "total": len(formatted),
        "is_placeholder": False,
        "refreshed_at": _now_iso(),
    }
    cache_set(f"activity:{org}", result, settings.activity_cache_ttl_seconds)
    return result


async def _refresh_contributors(org: str) -> dict:
    repos = await _get_or_refresh_raw_repos(org)
    active_repos = [r for r in repos if not r.get("archived", False)][:150]
    contributors = await get_all_contributors(org, active_repos)
    result = {
        "contributors": contributors,
        "total_unique_contributors": len(contributors),
        "total_contributions": sum(
            c.get("contributions", 0) for c in contributors
        ),
        "is_placeholder": False,
        "refreshed_at": _now_iso(),
    }
    cache_set(
        f"contributors:{org}",
        result,
        settings.contributors_cache_ttl_seconds,
    )
    return result


async def _refresh_commit_activity(org: str) -> dict:
    repos = await _get_or_refresh_raw_repos(org)
    result = await get_commit_activity(org, repos)
    result["is_placeholder"] = False
    result["refreshed_at"] = _now_iso()
    cache_set(
        f"commit_activity:{org}",
        result,
        settings.commit_activity_cache_ttl_seconds,
    )
    return result
