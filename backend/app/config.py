from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_token: str
    github_org: str
    cache_ttl_seconds: int = 300
    # Separate cache TTLs for different data types (in seconds)
    org_cache_ttl_seconds: int = 1800      # 30 minutes for org data
    repos_cache_ttl_seconds: int = 1200    # 20 minutes for repos
    contributors_cache_ttl_seconds: int = 900  # 15 minutes for contributors
    activity_cache_ttl_seconds: int = 300   # 5 minutes for activity
    commit_activity_cache_ttl_seconds: int = 600  # 10 minutes for commit activity
    # Cap how many repos to fetch — large academic orgs can have 10 000+
    max_repos: int = 1000

    # No explicit .env loading here. Docker injects the required variables via
    # the `env_file` directive in docker-compose.dev.yml, so Pydantic reads them
    # directly from the process environment.


settings = Settings()
