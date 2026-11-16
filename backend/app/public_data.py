def public_cache_key(dataset: str, org: str) -> str:
    return f"public:{dataset}:{org}"


def is_public_repo(repo: dict) -> bool:
    return repo.get("visibility") == "public" and not repo.get("private", False)


def filter_public_repos(repos: list[dict]) -> list[dict]:
    return [repo for repo in repos if is_public_repo(repo)]
