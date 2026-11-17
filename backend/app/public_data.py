def public_cache_key(dataset: str, org: str) -> str:
    return f"public:{dataset}:{org}"


def activity_cache_key(org: str, include_private: bool) -> str:
    if include_private:
        return f"restricted:activity:{org}"
    return public_cache_key("activity", org)


def contributors_cache_key(org: str, member_leaderboard: bool) -> str:
    if member_leaderboard:
        return f"restricted:member_contributors:{org}"
    return public_cache_key("contributors", org)


def repos_cache_key(org: str, include_private: bool) -> str:
    if include_private:
        return f"restricted:repos:{org}"
    return public_cache_key("repos", org)


def commit_activity_cache_key(org: str, include_private: bool) -> str:
    if include_private:
        return f"restricted:commit_activity:{org}"
    return public_cache_key("commit_activity", org)


def is_public_repo(repo: dict) -> bool:
    return repo.get("visibility") == "public" and not repo.get("private", False)


def filter_public_repos(repos: list[dict]) -> list[dict]:
    return [repo for repo in repos if is_public_repo(repo)]
