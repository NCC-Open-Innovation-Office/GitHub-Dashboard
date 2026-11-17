import asyncio
import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_ORG", "test-org")

from backend.app.routers.contributors import get_contributors
from backend.app.services import api_queue, github_service


def graphql_member(login, count):
    return {
        "login": login,
        "avatarUrl": f"https://avatars.example/{login}",
        "url": f"https://github.com/{login}",
        "contributionsCollection": {
            "contributionCalendar": {"totalContributions": count},
        },
    }


def graphql_page(members, total, has_next=False, cursor=None):
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.github.com/graphql"),
        json={"data": {"organization": {"membersWithRole": {
            "nodes": members,
            "totalCount": total,
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        }}}},
    )


class MemberContributorsTests(unittest.TestCase):
    def test_graphql_paginates_all_members_with_one_fixed_year_window(self):
        requests = []
        pages = [
            graphql_page([graphql_member("alice", 3)], 2, True, "page-2"),
            graphql_page([graphql_member("bob", 12)], 2),
        ]

        async def request(priority, method, url, **kwargs):
            requests.append(kwargs["json"]["variables"])
            return pages.pop(0)

        with patch.object(github_service.request_queue, "add_request", side_effect=request):
            result = asyncio.run(github_service.get_member_contributions("test-org"))

        self.assertEqual([member["login"] for member in result["members"]], ["alice", "bob"])
        self.assertEqual(result["members"][1]["contributions"], 12)
        self.assertIsNone(requests[0]["after"])
        self.assertEqual(requests[1]["after"], "page-2")
        self.assertEqual(requests[0]["from"], requests[1]["from"])
        self.assertEqual(requests[0]["to"], requests[1]["to"])
        start = datetime.fromisoformat(result["from"])
        end = datetime.fromisoformat(result["to"])
        self.assertEqual(start.year, end.year - 1)
        self.assertEqual((start.month, start.hour, start.minute), (end.month, end.hour, end.minute))
        self.assertEqual(start.day, min(end.day, 28) if end.month == 2 and end.day == 29 else end.day)

    def test_graphql_errors_and_incomplete_pagination_fail(self):
        error = httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.github.com/graphql"),
            json={"errors": [{"message": "access denied"}], "data": None},
        )
        for response in (error, graphql_page([graphql_member("alice", 3)], 2)):
            with self.subTest(response=response), \
                 patch.object(github_service.request_queue, "add_request", AsyncMock(return_value=response)):
                with self.assertRaises(RuntimeError):
                    asyncio.run(github_service.get_member_contributions("test-org"))

    def test_member_ranking_covers_every_member_and_uses_restricted_cache(self):
        members = [
            {"login": f"user-{i:02}", "avatar_url": None, "html_url": None, "contributions": i}
            for i in range(25)
        ]
        with patch.object(api_queue.settings, "member_contribution_leaderboard", True), \
             patch.object(api_queue, "get_member_contributions", AsyncMock(return_value={
                 "members": members, "from": "2025-01-01", "to": "2026-01-01",
             })), \
             patch.object(api_queue, "_get_or_refresh_raw_repos", AsyncMock()) as repos, \
             patch.object(api_queue, "cache_set") as cache_set, \
             patch.object(api_queue, "cache_set_last_good"):
            result = asyncio.run(api_queue._refresh_contributors("test-org"))
        repos.assert_not_called()
        self.assertEqual(len(result["contributors"]), 10)
        self.assertEqual(result["contributors"][0]["login"], "user-24")
        self.assertEqual(result["contributors"][-1]["login"], "user-15")
        self.assertEqual(result["total_members"], 25)
        self.assertEqual(result["total_contributions"], sum(range(25)))
        self.assertEqual(cache_set.call_args.args[0], "restricted:member_contributors:test-org")

    def test_failed_member_query_does_not_cache_partial_results(self):
        with patch.object(api_queue.settings, "member_contribution_leaderboard", True), \
             patch.object(api_queue, "get_member_contributions", AsyncMock(side_effect=RuntimeError("failed"))), \
             patch.object(api_queue, "cache_set") as cache_set, \
             patch.object(api_queue, "cache_set_last_good"):
            with self.assertRaises(RuntimeError):
                asyncio.run(api_queue._refresh_contributors("test-org"))
        cache_set.assert_not_called()

    def test_public_and_member_cache_are_separate_and_failed_refresh_warns(self):
        for enabled, expected in (
            (False, "public:contributors:test-org"),
            (True, "restricted:member_contributors:test-org"),
        ):
            with self.subTest(enabled=enabled), \
                 patch.object(api_queue.settings, "member_contribution_leaderboard", enabled), \
                 patch("backend.app.routers.contributors.cache_get_or_last_good", return_value={
                     "contributors": [], "is_placeholder": True,
                 }) as get_cache, \
                 patch.object(api_queue, "get_queue_status", return_value={
                     "jobs": {"contributors:test-org": {"state": "failed"}},
                 }), \
                 patch.object(api_queue, "enqueue_contributors"):
                result = asyncio.run(get_contributors("org"))
                self.assertEqual(get_cache.call_args.args[0], expected)
                self.assertIn("failed", result["warning"])


if __name__ == "__main__":
    unittest.main()
