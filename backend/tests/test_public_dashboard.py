import asyncio
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_ORG", "test-org")

from fastapi import HTTPException

from backend.app.main import app
from backend.app.routers.activity import _build_result as build_activity_result
from backend.app.routers.contributors import get_member_wide_stats
from backend.app.routers.org import get_org_overview
from backend.app.routers.repos import get_repos
from backend.app.routers.repos import _build_result as build_repos_result


class PublicDashboardTests(unittest.TestCase):
    def test_repo_summary_includes_public_repositories_only(self):
        result = build_repos_result(
            [
                {
                    "id": 1,
                    "name": "public",
                    "full_name": "org/public",
                    "visibility": "public",
                    "private": False,
                    "stargazers_count": 2,
                    "open_issues_count": 4,
                },
                {
                    "id": 2,
                    "name": "private",
                    "full_name": "org/private",
                    "visibility": "private",
                    "private": True,
                    "stargazers_count": 90,
                    "open_issues_count": 50,
                },
                {
                    "id": 3,
                    "name": "internal",
                    "full_name": "org/internal",
                    "visibility": "internal",
                    "private": True,
                    "stargazers_count": 80,
                    "open_issues_count": 40,
                },
                {
                    "id": 4,
                    "name": "unknown",
                    "full_name": "org/unknown",
                },
            ]
        )

        self.assertEqual([repo["name"] for repo in result["repos"]], ["public"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["total_stars"], 2)
        self.assertEqual(result["total_open_issues"], 4)
        self.assertNotIn("private", result)
        self.assertNotIn("internal", result)

    def test_restricted_repo_summary_counts_all_repos_but_public_open_issues(self):
        repos = [
            {"id": 1, "name": "a", "full_name": "org/a", "visibility": "public",
             "private": False, "stargazers_count": 2, "open_issues_count": 4},
            {"id": 2, "name": "b", "full_name": "org/b", "visibility": "private",
             "private": True, "stargazers_count": 90, "open_issues_count": 50},
        ]
        result = build_repos_result(repos, include_private=True)

        self.assertEqual([repo["name"] for repo in result["repos"]], ["a", "b"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["total_stars"], 92)
        self.assertEqual(result["total_open_issues"], 54)
        self.assertEqual(result["total_public_open_issues"], 4)

    def test_activity_is_filtered_to_public_repository_names(self):
        events = [
            {
                "id": "public-event",
                "type": "PushEvent",
                "actor": {"login": "contributor"},
                "repo": {"name": "ORG/Public"},
                "payload": {"commits": []},
            },
            {
                "id": "private-event",
                "type": "PushEvent",
                "actor": {"login": "contributor"},
                "repo": {"name": "org/private"},
                "payload": {"commits": []},
            },
        ]

        result = build_activity_result(events, {"org/public"})

        self.assertEqual(result["total"], 1)
        self.assertEqual([event["id"] for event in result["events"]], ["public-event"])

    def test_member_wide_stats_are_not_available_anonymously(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(get_member_wide_stats())

        self.assertEqual(raised.exception.status_code, 404)

    def test_org_response_strips_private_fields_from_cached_data(self):
        private_cache_value = {
            "login": "test-org",
            "public_repos": 10,
            "total_private_repos": 7,
            "owned_private_repos": 5,
            "member_count": 12,
        }

        with patch(
            "backend.app.routers.org.cache_get_or_last_good",
            return_value=private_cache_value,
        ):
            result = asyncio.run(get_org_overview())

        self.assertEqual(result["public_repos"], 10)
        self.assertNotIn("total_private_repos", result)
        self.assertNotIn("owned_private_repos", result)
        self.assertNotIn("member_count", result)

    def test_repo_route_reads_the_new_public_cache_namespace(self):
        with patch(
            "backend.app.routers.repos.cache_get_or_last_good",
            return_value=None,
        ) as cache_get, patch(
            "backend.app.routers.repos.cache_set",
        ), patch(
            "backend.app.routers.repos.api_queue.enqueue_org_repos",
        ):
            result = asyncio.run(get_repos())

        self.assertEqual(
            cache_get.call_args.args[0],
            "public:repos:test-org",
        )
        self.assertNotIn("private", result)
        self.assertNotIn("internal", result)

    def test_debug_routes_are_not_mounted(self):
        paths = set(app.openapi()["paths"])

        self.assertFalse(any(path.startswith("/api/debug") for path in paths))


if __name__ == "__main__":
    unittest.main()
