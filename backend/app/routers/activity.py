from fastapi import APIRouter
from datetime import datetime, timezone

from ..cache import cache_get_or_last_good, cache_set
from ..config import settings
from ..public_data import activity_cache_key
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
    cache_key = activity_cache_key(settings.github_org, settings.include_private_activity)
    if cached := cache_get_or_last_good(
        cache_key,
        "Activity data is being refreshed in the background.",
    ):
        if cached.get("is_placeholder"):
            status = api_queue.get_queue_status()["jobs"].get(
                f"activity:{settings.github_org}", {}
            )
            if status.get("state") == "failed":
                cached["warning"] = (
                    "Activity refresh failed. Check server logs and GitHub token permissions."
                )
            api_queue.enqueue_org_events(settings.github_org)
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


def _build_result(events: list[dict], public_repo_names: set[str]) -> dict:
    filtered = []
    for event in events:
        repo_name = (event.get("repo") or {}).get("name")
        if (
            event.get("type") in _INTERESTING
            and isinstance(repo_name, str)
            and repo_name.casefold() in public_repo_names
        ):
            filtered.append(_format_event(event))
    return {"events": filtered[:50], "total": len(filtered)}


def _format_search_results(items: list[dict], org: str, kind: str) -> list[dict]:
    formatted = []
    for item in items:
        if kind == "commits":
            repo = item["repository"]["full_name"]
            commit = item["commit"]
            author = item.get("author") or {}
            login = author.get("login") or (commit.get("author") or {}).get("name") or "Unknown author"
            timestamp = commit["committer"]["date"]
            event_type = "CommitEvent"
            payload = {"message": commit.get("message", "")[:120]}
            event_id = f"commit:{repo}:{item['sha']}"
        else:
            repo = item["repository_url"].rstrip("/").split("/repos/", 1)[-1]
            author = item.get("user") or {}
            login = author.get("login") or "Unknown author"
            timestamp = item["created_at"]
            event_type = "PullRequestEvent" if "pull_request" in item else "IssuesEvent"
            payload = {
                "action": "opened",
                "title": item["title"],
                "number": item["number"],
                "html_url": item["html_url"],
            }
            event_id = f"issue:{repo}:{item['number']}"
        if repo.split("/", 1)[0].casefold() != org.casefold():
            continue
        formatted.append({
            "id": event_id,
            "type": event_type,
            "actor": {
                "login": login,
                "avatar_url": author.get("avatar_url"),
                "url": author.get("html_url"),
            },
            "repo": repo,
            "created_at": timestamp,
            "payload": payload,
        })
    return formatted
