from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_token: str
    github_org: str
    cache_ttl_seconds: int = 300
    # Cap how many repos to fetch — large academic orgs can have 10 000+
    max_repos: int = 1000

    class Config:
        env_file = ".env"


settings = Settings()
