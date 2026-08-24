from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    database_url: str

    cors_origins: str = "http://localhost:3000"

    openai_api_key: str | None = None

    # ATS (Greenhouse/Lever) HTTP timeouts, split connect vs. read since
    # they fail differently (an unreachable host vs. a slow response) --
    # both public APIs are normally fast (sub-second), so these are
    # generous-but-bounded: enough headroom for a real slow response, not
    # enough to let one bad company stall a /jobs/match request for
    # minutes. Overridable via env for a slower/flakier network.
    ats_connect_timeout_seconds: float = 5.0
    ats_read_timeout_seconds: float = 10.0

    # Bounded concurrency for fetching multiple companies' ATS boards at
    # once (ingestion/runner.py's _fetch_sources_concurrently). Kept
    # conservative by default -- enough to overlap I/O-bound waits across
    # companies without hammering any one ATS provider if several tracked
    # companies happen to share a platform.
    ats_max_concurrency: int = 4

    # OpenAI request timeout + retry cap. 20s comfortably covers a normal
    # batched extraction call (BATCH_SIZE postings/prompt); max_retries
    # bounds the OpenAI SDK's own retry-on-transient-error behavior so a
    # degraded OpenAI doesn't multiply one slow call into several.
    openai_timeout_seconds: float = 20.0
    openai_max_retries: int = 2

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

# don't have to call get_settings everytime

@lru_cache
def get_settings() -> Settings:
    return Settings()