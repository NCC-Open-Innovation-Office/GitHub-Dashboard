import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_ORG", "test-org")

from backend.app.routers.activity import _format_search_results, get_activity
from backend.app.services import api_queue, github_service


class PrivateActivityTests(unittest.TestCase):
    def test_search_results_format_commits_issues_and_pull_requests(self):
        commits = [{
            "repository": {"full_name": "test-org/private"},
            "sha": "abc",
            "author": None,
            "commit": {
                "author": {"name": "Unlinked author"},
                "committer": {"date": "2026-01-03T00:00:00Z"},
                "message": "A commit",
            },
        }]
        issues = [{
            "repository_url": "https://api.github.com/repos/test-org/internal",
            "number": 2,
            "title": "Issue",
            "html_url": "https://github.com/test-org/internal/issues/2",
            "created_at": "2026-01-02T00:00:00Z",
            "user": {"login": "alice", "html_url": "https://github.com/alice"},
        }, {
            "repository_url": "https://api.github.com/repos/test-org/private",
            "number": 3,
            "title": "PR",
            "html_url": "https://github.com/test-org/private/pull/3",
            "created_at": "2026-01-01T00:00:00Z",
            "user": None,
            "pull_request": {},
        }]

        commit = _format_search_results(commits, "test-org", "commits")[0]
        result = _format_search_results(issues, "test-org", "issues")
        self.assertEqual(commit["type"], "CommitEvent")
        self.assertEqual(commit["actor"]["login"], "Unlinked author")
        self.assertIsNone(commit["actor"]["url"])
        self.assertEqual([event["type"] for event in result], ["IssuesEvent", "PullRequestEvent"])
        self.assertEqual(result[0]["payload"]["action"], "opened")
        self.assertEqual(result[1]["actor"]["login"], "Unknown author")
        self.assertEqual(_format_search_results(issues, "other-org", "issues"), [])

    def test_search_requests_both_visibilities_and_rejects_incomplete_results(self):
        calls = []

        async def request(priority, method, url, **kwargs):
            calls.append((url, kwargs["params"]))
            return httpx.Response(
                200, json={"items": [], "incomplete_results": False},
                request=httpx.Request("GET", url),
            )

        with patch.object(github_service.request_queue, "add_request", side_effect=request), \
             patch.object(github_service.asyncio, "sleep", AsyncMock()):
            self.assertEqual(asyncio.run(github_service.search_non_public_activity("test-org", [
                {"full_name": "test-org/internal", "visibility": "internal"},
                {"full_name": "test-org/private", "visibility": "private"},
            ])), [])
        self.assertEqual(len(calls), 5)
        self.assertEqual({params["q"] for _, params in calls}, {
            "org:test-org is:private",
            "org:test-org is:private is:issue", "org:test-org is:private is:pull-request",
            "org:test-org is:internal is:issue", "org:test-org is:internal is:pull-request",
        })
        self.assertEqual({url.rsplit("/", 1)[-1] for url, _ in calls}, {"commits", "issues"})

        response = httpx.Response(
            200, json={"items": [], "incomplete_results": True},
            request=httpx.Request("GET", "https://api.github.com/search/commits"),
        )
        with patch.object(github_service.request_queue, "add_request", AsyncMock(return_value=response)), \
             patch.object(github_service.asyncio, "sleep", AsyncMock()):
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                asyncio.run(github_service.search_non_public_activity("test-org", []))

    def test_enabled_refresh_merges_chronologically_and_separates_cache(self):
        public_event = {
            "id": "public", "type": "WatchEvent", "actor": {"login": "alice"},
            "repo": {"name": "test-org/public"}, "created_at": "2026-01-01T00:00:00Z",
        }
        private_event = {
            "id": "private", "type": "CommitEvent", "actor": {"login": "bob"},
            "repo": "test-org/private", "created_at": "2026-01-02T00:00:00Z",
            "payload": {},
        }
        with patch.object(api_queue.settings, "include_private_activity", True), \
             patch.object(api_queue, "_get_or_refresh_raw_repos", AsyncMock(return_value=[
                 {"full_name": "test-org/public", "visibility": "public", "private": False},
             ])), \
             patch.object(api_queue, "get_org_events", AsyncMock(return_value=[public_event])), \
             patch.object(api_queue, "search_non_public_activity", AsyncMock(return_value=[private_event])), \
             patch.object(api_queue, "_repo_progress", return_value={"complete": True}), \
             patch.object(api_queue, "cache_set") as cache_set, \
             patch.object(api_queue, "cache_set_last_good"):
            result = asyncio.run(api_queue._refresh_activity("test-org"))

        self.assertEqual([event["id"] for event in result["events"]], ["private", "public"])
        self.assertEqual(cache_set.call_args.args[0], "restricted:activity:test-org")
        self.assertEqual(result["total"], 2)

    def test_failed_search_does_not_cache_partial_results(self):
        with patch.object(api_queue.settings, "include_private_activity", True), \
             patch.object(api_queue, "_get_or_refresh_raw_repos", AsyncMock(return_value=[])), \
             patch.object(api_queue, "get_org_events", AsyncMock(return_value=[])), \
             patch.object(api_queue, "search_non_public_activity", AsyncMock(side_effect=RuntimeError("failed"))), \
             patch.object(api_queue, "cache_set") as cache_set, \
             patch.object(api_queue, "cache_set_last_good"):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                asyncio.run(api_queue._refresh_activity("test-org"))
        cache_set.assert_not_called()

    def test_disabled_refresh_does_not_search_private_activity(self):
        with patch.object(api_queue.settings, "include_private_activity", False), \
             patch.object(api_queue, "_get_or_refresh_raw_repos", AsyncMock(return_value=[])), \
             patch.object(api_queue, "get_org_events", AsyncMock(return_value=[])), \
             patch.object(api_queue, "search_non_public_activity", AsyncMock()) as search, \
             patch.object(api_queue, "cache_set") as cache_set, \
             patch.object(api_queue, "cache_set_last_good"):
            asyncio.run(api_queue._refresh_activity("test-org"))
        search.assert_not_called()
        self.assertEqual(cache_set.call_args.args[0], "public:activity:test-org")

    def test_non_public_search_deduplicates_and_skips_per_repo_queries(self):
        commit = {
            "repository": {"full_name": "test-org/private"},
            "sha": "abc",
            "author": {"login": "alice"},
            "commit": {
                "committer": {"date": "2026-01-03T00:00:00Z"},
                "message": "A commit",
            },
        }
        queries = []

        async def request(priority, method, url, **kwargs):
            query = kwargs["params"]["q"]
            queries.append(query)
            items = [commit] if url.endswith("/commits") else []
            return httpx.Response(
                200, json={"items": items, "incomplete_results": False},
                request=httpx.Request("GET", url),
            )

        repos = [
            {"full_name": f"test-org/internal-{i:03d}", "visibility": "internal"}
            for i in range(20)
        ]
        with patch.object(github_service.request_queue, "add_request", side_effect=request), \
             patch.object(github_service.asyncio, "sleep", AsyncMock()):
            result = asyncio.run(github_service.search_non_public_activity("test-org", repos))
        self.assertFalse([query for query in queries if query.startswith("repo:")])
        self.assertEqual(len(result), 1)

    def test_disabled_route_uses_public_cache_and_failed_placeholder_warns(self):
        placeholder = {"events": [], "is_placeholder": True}
        with patch.object(api_queue.settings, "include_private_activity", False), \
             patch("backend.app.routers.activity.cache_get_or_last_good", return_value=placeholder) as get_cache, \
             patch.object(api_queue, "get_queue_status", return_value={
                 "jobs": {"activity:test-org": {"state": "failed"}},
             }), \
             patch.object(api_queue, "enqueue_org_events") as enqueue:
            result = asyncio.run(get_activity())
        self.assertEqual(get_cache.call_args.args[0], "public:activity:test-org")
        self.assertIn("failed", result["warning"])
        enqueue.assert_called_once_with("test-org")


if __name__ == "__main__":
    unittest.main()
