from fastapi import APIRouter
from datetime import datetime, timezone

from ..cache import cache_clear, cache_get, cache_set
from ..config import settings
from ..services import api_queue

router = APIRouter()

_INTERESTING = {
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


@router.get("")
async def get_activity():
    cache_key = f"activity:{settings.github_org}"
    if cached := cache_get(cache_key):
        return cached

    api_queue.enqueue_org_events(settings.github_org)
    placeholder = {
        "events": [],
        "total": 0,
        "warning": "Activity data is being refreshed in the background.",
        "is_placeholder": True,
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    cache_set(cache_key, placeholder, settings.activity_cache_ttl_seconds)
    return placeholder


@router.post("/refresh")
async def refresh_activity():
    cache_clear(f"activity:{settings.github_org}")
    return await get_activity()


def _format_event(event: dict) -> dict:
    return {
        "id": event.get("id"),
        "type": event.get("type"),
        "actor": {
            "login": event["actor"]["login"],
            "avatar_url": event["actor"].get("avatar_url"),
            "url": f"https://github.com/{event['actor']['login']}",
        },
        "repo": event.get("repo", {}).get("name", ""),
        "created_at": event.get("created_at"),
        "payload": _extract_payload(event),
    }


def _extract_payload(event: dict) -> dict:
    payload = event.get("payload", {})
    event_type = event.get("type", "")

    if event_type == "PushEvent":
        commits = payload.get("commits", [])
        return {
            "ref": payload.get("ref", ""),
            "commit_count": len(commits),
            "message": commits[0]["message"][:120] if commits else "",
        }
    if event_type == "PullRequestEvent":
        pr = payload.get("pull_request", {})
        return {
            "action": payload.get("action"),
            "title": pr.get("title", ""),
            "number": pr.get("number"),
            "html_url": pr.get("html_url", ""),
            "merged": pr.get("merged", False),
        }
    if event_type == "IssuesEvent":
        issue = payload.get("issue", {})
        return {
            "action": payload.get("action"),
            "title": issue.get("title", ""),
            "number": issue.get("number"),
            "html_url": issue.get("html_url", ""),
        }
    if event_type == "CreateEvent":
        return {
            "ref_type": payload.get("ref_type"),
            "ref": payload.get("ref"),
        }
    if event_type == "ReleaseEvent":
        release = payload.get("release", {})
        return {
            "action": payload.get("action"),
            "tag_name": release.get("tag_name"),
            "name": release.get("name"),
            "html_url": release.get("html_url", ""),
        }
    if event_type == "ForkEvent":
        forkee = payload.get("forkee", {})
        return {"forkee": forkee.get("full_name", "")}
    return {}


def _build_result(events: list[dict]) -> dict:
    filtered = [
        _format_event(e) for e in events if e.get("type") in _INTERESTING
    ]
    return {"events": filtered[:50], "total": len(filtered)}
