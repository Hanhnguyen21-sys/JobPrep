"""Shared OpenAI client.

Every AI-backed service (skill_extraction now; matching/embeddings/roadmap
later per the file-structure plan) imports `get_ai_client()` instead of
instantiating its own `OpenAI(...)`. One place to hold the API key, swap
models/providers later, or add retry/logging without touching every
service that calls out to the model.
"""

from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings


@lru_cache
def get_ai_client() -> OpenAI:
    settings = get_settings()

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set — add it to backend/.env before "
            "calling any AI-backed endpoint."
        )

    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
