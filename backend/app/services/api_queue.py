import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from ..cache import cache_get, cache_set, cache_set_last_good
from ..config import settings
from ..public_data import filter_public_repos, public_cache_key
from .request_queue import Priority
from .github_service import (
    get_all_contributors,
    get_commit_activity,
    get_org_details,
    get_org_events,
    get_org_members,
    get_org_repos_page,
    get_user_repos,
)

logger = logging.getLogger(__name__)

MAX_CALLS_PER_BATCH = 1000
BATCH_INTERVAL = 15 * 60
JOB_TIMEOUT_SECONDS = 30 * 60
REPO_PAGES_PER_JOB = 5
CONTRIBUTOR_REPO_SAMPLE = 150
COMMIT_ACTIVITY_REPO_SAMPLE = 200
MEMBER_WIDE_CONCURRENCY = 6


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
_post_run_enqueues: dict[str, tuple[Callable[..., None], tuple[Any, ...]]] = {}


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
            "heartbeat_at": None,
            "current_step": None,
            "current_detail": None,
        },
    )


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _repo_progress_key(org: str) -> str:
    return f"raw_repos_progress:{org}"


def _repo_progress(org: str) -> dict[str, Any]:
    return cache_get(_repo_progress_key(org)) or {
        "next_url": None,
        "complete": False,
        "fetched_repos": 0,
        "updated_at": None,
    }


def _set_repo_progress(org: str, progress: dict[str, Any]) -> None:
    cache_set(
        _repo_progress_key(org),
        progress,
        settings.repos_cache_ttl_seconds,
    )


def get_repo_progress(org: str) -> dict[str, Any]:
    return _repo_progress(org)


def _mark_job_step(key: str, step: str, detail: str | None = None) -> None:
    status = _ensure_status(key)
    status["current_step"] = step
    status["current_detail"] = detail
    status["heartbeat_at"] = _now_iso()


def _mark_job_error(key: str, message: str) -> None:
    status = _ensure_status(key)
    status["last_error"] = message
    status["heartbeat_at"] = _now_iso()


def _mark_job_success(key: str, detail: str | None = None) -> None:
    status = _ensure_status(key)
    status["current_step"] = "completed"
    status["current_detail"] = detail
    status["heartbeat_at"] = _now_iso()


async def _delayed_enqueue(func: Callable[..., None], *args: Any) -> None:
    await asyncio.sleep(0)
    func(*args)


def _enqueue_after_run(
    key: str,
    func: Callable[..., None],
    *args: Any,
) -> None:
    _post_run_enqueues[key] = (func, args)


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


def _cache_repo_snapshot(
    org: str,
    repos: list[dict],
    next_url: str | None,
    complete: bool,
) -> None:
    from ..routers.repos import _build_result

    result = _build_result(repos)
    result["is_placeholder"] = not complete
    result["refreshed_at"] = _now_iso()
    if not complete:
        result["warning"] = "Public repository data is being refreshed."

    cache_set(f"raw_repos:{org}", repos, settings.repos_cache_ttl_seconds)
    repos_key = public_cache_key("repos", org)
    cache_set(repos_key, result, settings.repos_cache_ttl_seconds)
    cache_set_last_good(
        repos_key,
        result,
        settings.repos_cache_ttl_seconds,
    )
    _set_repo_progress(
        org,
        {
            "next_url": next_url,
            "complete": complete,
            "fetched_repos": len(repos),
            "updated_at": _now_iso(),
        },
    )


async def _refresh_org_repos(org: str, priority: Any = None) -> list[dict]:
    effective_priority = (
        priority
        if isinstance(priority, Priority)
        else Priority.MEDIUM
    )
    job_key = f"repos:{org}"
    existing_repos = cache_get(f"raw_repos:{org}") or []
    progress = _repo_progress(org)
    next_url = progress.get("next_url")
    complete = bool(progress.get("complete", False))

    repos = list(existing_repos)
    page_count = 0
    while len(repos) < settings.max_repos and page_count < REPO_PAGES_PER_JOB:
        _mark_job_step(
            job_key,
            "fetching_repo_page",
            (
                f"page_batch_index={page_count + 1}, "
                f"fetched_repos={len(repos)}, "
                f"has_next_url={bool(next_url)}"
            ),
        )
        retries = 0
        while True:
            try:
                page, next_url = await get_org_repos_page(
                    org,
                    next_url=next_url,
                    priority=effective_priority,
                )
                break
            except TimeoutError as exc:
                retries += 1
                if retries <= 2 and page_count == 0:
                    _mark_job_step(
                        job_key,
                        "retrying_repo_page",
                        f"attempt={retries + 1}, fetched_repos={len(repos)}",
                    )
                    await asyncio.sleep(2 * retries)
                    continue
                if repos:
                    _cache_repo_snapshot(
                        org,
                        repos[:settings.max_repos],
                        next_url,
                        False,
                    )
                _mark_job_error(job_key, str(exc))
                raise
            except Exception as exc:
                if repos:
                    _cache_repo_snapshot(
                        org,
                        repos[:settings.max_repos],
                        next_url,
                        False,
                    )
                _mark_job_error(job_key, str(exc))
                raise
        if not page:
            complete = True
            break
        repos.extend(page)
        page_count += 1
        _mark_job_step(
            job_key,
            "repo_page_fetched",
            f"page_size={len(page)}, fetched_repos={len(repos)}",
        )
        _cache_repo_snapshot(
            org,
            repos[:settings.max_repos],
            next_url,
            False,
        )
        asyncio.create_task(_delayed_enqueue(enqueue_contributors, org))
        asyncio.create_task(_delayed_enqueue(enqueue_commit_activity, org))
        if next_url is None:
            complete = True
            break

    repos = repos[:settings.max_repos]
    if len(repos) >= settings.max_repos:
        complete = True

    _cache_repo_snapshot(org, repos, next_url, complete)

    if not complete and next_url:
        _enqueue_after_run(job_key, enqueue_org_repos, org)
    _mark_job_success(
        job_key,
        f"fetched_repos={len(repos)}, scan_complete={complete}",
    )
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
    return await _refresh_org_repos(org, priority=Priority.MEDIUM)


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
            pending = _post_run_enqueues.pop(key, None)
            if pending is not None:
                func, args = pending
                func(*args)

    await asyncio.gather(
        *(_execute(call) for call in batch),
        return_exceptions=True,
    )


async def process_queue() -> None:
    logger.info(
        (
            "Starting rate-limited API queue processor "
            "(max %d calls per batch)"
        ),
        MAX_CALLS_PER_BATCH,
    )
    while True:
        try:
            if _api_queue:
                await _process_batch()
                if _api_queue:
                    await asyncio.sleep(0.1)
                else:
                    await asyncio.sleep(1)
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


def enqueue_full_refresh(org: str) -> None:
    """Queue refresh jobs for all dashboard datasets."""
    enqueue_org_details(org)
    enqueue_org_repos(org)
    enqueue_org_events(org)
    enqueue_contributors(org)
    enqueue_commit_activity(org)


def enqueue_member_wide_stats(org: str) -> None:
    key = f"member_wide_stats:{org}"
    enqueue_unique(
        key,
        ApiCall(
            func=_refresh_member_wide_stats,
            args=(org,),
            description=key,
        ),
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
    job_key = f"org:{org}"
    _mark_job_step(job_key, "fetching_org_overview")
    org_data = await get_org_details(org)

    from ..routers.org import _build_result

    result = _build_result(org_data)
    result["is_placeholder"] = False
    result["refreshed_at"] = _now_iso()
    org_key = public_cache_key("org", org)
    cache_set(org_key, result, settings.org_cache_ttl_seconds)
    cache_set_last_good(
        org_key,
        result,
        settings.org_cache_ttl_seconds,
    )
    _mark_job_success(job_key, "org overview cached")
    return result


async def _refresh_activity(org: str) -> dict:
    job_key = f"activity:{org}"
    _mark_job_step(job_key, "fetching_activity")
    repos = await _get_or_refresh_raw_repos(org)
    public_repo_names = {
        repo["full_name"].casefold()
        for repo in filter_public_repos(repos)
        if repo.get("full_name")
    }
    events = await get_org_events(org)
    from ..routers.activity import _build_result

    result = _build_result(events, public_repo_names)
    result["is_placeholder"] = False
    result["refreshed_at"] = _now_iso()
    activity_key = public_cache_key("activity", org)
    cache_set(activity_key, result, settings.activity_cache_ttl_seconds)
    cache_set_last_good(
        activity_key,
        result,
        settings.activity_cache_ttl_seconds,
    )
    _mark_job_success(job_key, f"events={len(result['events'])}")
    return result


async def _refresh_contributors(org: str) -> dict:
    job_key = f"contributors:{org}"
    _mark_job_step(job_key, "loading_repo_sample")
    repos = await _get_or_refresh_raw_repos(org)
    progress = _repo_progress(org)
    active_repos = [
        repo
        for repo in filter_public_repos(repos)
        if not repo.get("archived", False)
    ][:CONTRIBUTOR_REPO_SAMPLE]
    _mark_job_step(
        job_key,
        "fetching_contributors",
        f"repo_sample_size={len(active_repos)}",
    )
    contributors = await get_all_contributors(org, active_repos)
    complete = bool(progress.get("complete", False))
    result = {
        "contributors": contributors,
        "total_unique_contributors": len(contributors),
        "total_contributions": sum(
            c.get("contributions", 0) for c in contributors
        ),
        "repo_sample_size": len(active_repos),
        "is_placeholder": not complete,
        "refreshed_at": _now_iso(),
    }
    if not complete:
        result["warning"] = (
            "Contributor data is based on a partial public repository scan."
        )
    contributors_key = public_cache_key("contributors", org)
    cache_set(
        contributors_key,
        result,
        settings.contributors_cache_ttl_seconds,
    )
    cache_set_last_good(
        contributors_key,
        result,
        settings.contributors_cache_ttl_seconds,
    )
    _mark_job_success(
        job_key,
        f"contributors={len(contributors)}, repo_scan_complete={complete}",
    )
    return result


async def _refresh_commit_activity(org: str) -> dict:
    job_key = f"commit_activity:{org}"
    _mark_job_step(job_key, "loading_repo_sample")
    repos = await _get_or_refresh_raw_repos(org)
    progress = _repo_progress(org)
    sample_repos = sorted(
        filter_public_repos(repos),
        key=lambda repo: repo.get("pushed_at") or "",
        reverse=True,
    )[:COMMIT_ACTIVITY_REPO_SAMPLE]
    _mark_job_step(
        job_key,
        "fetching_commit_activity",
        f"repo_sample_size={len(sample_repos)}",
    )
    result = await get_commit_activity(org, sample_repos)
    complete = bool(progress.get("complete", False))
    result["repo_sample_size"] = len(sample_repos)
    result["is_placeholder"] = not complete
    result["refreshed_at"] = _now_iso()
    if not complete:
        result["warning"] = "Commit activity is based on a partial public repository scan."
    commit_activity_key = public_cache_key("commit_activity", org)
    cache_set(
        commit_activity_key,
        result,
        settings.commit_activity_cache_ttl_seconds,
    )
    cache_set_last_good(
        commit_activity_key,
        result,
        settings.commit_activity_cache_ttl_seconds,
    )
    _mark_job_success(
        job_key,
        f"repo_sample_size={len(sample_repos)}, repo_scan_complete={complete}",
    )
    return result


async def _refresh_member_wide_stats(org: str) -> dict:
    job_key = f"member_wide_stats:{org}"
    _mark_job_step(job_key, "loading_org_members")
    members = await get_org_members(org)
    members = members[: settings.member_wide_max_members]

    semaphore = asyncio.Semaphore(MEMBER_WIDE_CONCURRENCY)

    async def _fetch_member_stats(member: dict[str, Any]) -> dict[str, Any]:
        login = member.get("login")
        if not login:
            return {}

        async with semaphore:
            repos = await get_user_repos(
                login,
                max_items=settings.member_wide_repo_limit_per_member,
                priority=Priority.LOW,
            )

        visibility_counts = {"public": 0, "private": 0, "internal": 0}
        for repo in repos:
            visibility = repo.get("visibility", "public")
            if visibility not in visibility_counts:
                visibility = "public"
            visibility_counts[visibility] += 1

        pushed_dates: list[str] = [
            pushed_at
            for repo in repos
            if (pushed_at := repo.get("pushed_at")) is not None
        ]

        return {
            "login": login,
            "avatar_url": member.get("avatar_url"),
            "html_url": f"https://github.com/{login}",
            "repo_count": len(repos),
            "total_stars": sum(
                int(repo.get("stargazers_count", 0)) for repo in repos
            ),
            "total_forks": sum(
                int(repo.get("forks_count", 0)) for repo in repos
            ),
            "total_open_issues": sum(
                int(repo.get("open_issues_count", 0)) for repo in repos
            ),
            "last_pushed_at": max(pushed_dates) if pushed_dates else None,
            "visibility_breakdown": visibility_counts,
        }

    _mark_job_step(
        job_key,
        "fetching_member_repo_stats",
        f"member_count={len(members)}",
    )
    rows = await asyncio.gather(
        *(_fetch_member_stats(m) for m in members),
        return_exceptions=True,
    )

    member_stats: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and row:
            member_stats.append(row)

    member_stats.sort(
        key=lambda item: (
            int(item.get("repo_count", 0)),
            int(item.get("total_stars", 0)),
        ),
        reverse=True,
    )

    result = {
        "scope": "member_wide",
        "member_count": len(member_stats),
        "members": member_stats,
        "totals": {
            "repos": sum(int(m.get("repo_count", 0)) for m in member_stats),
            "stars": sum(int(m.get("total_stars", 0)) for m in member_stats),
            "forks": sum(int(m.get("total_forks", 0)) for m in member_stats),
            "open_issues": sum(
                int(m.get("total_open_issues", 0)) for m in member_stats
            ),
        },
        "limits": {
            "max_members": settings.member_wide_max_members,
            "max_repos_per_member": settings.member_wide_repo_limit_per_member,
        },
        "warning": (
            "Member-wide stats include only repositories visible to this "
            "token. "
            "Private repositories outside organization access are excluded."
        ),
        "is_placeholder": False,
        "refreshed_at": _now_iso(),
    }

    cache_set(
        f"member_wide_stats:{org}",
        result,
        settings.member_wide_cache_ttl_seconds,
    )
    cache_set_last_good(
        f"member_wide_stats:{org}",
        result,
        settings.member_wide_cache_ttl_seconds,
    )
    _mark_job_success(
        job_key,
        f"member_count={len(member_stats)}",
    )
    return result
