"""Tests for Phase 1 item 2's OpenAI timeout/retry configuration
(core/ai_client.py)."""

from unittest.mock import patch

from app.core.ai_client import get_ai_client
from app.core.config import get_settings


def test_get_ai_client_configures_timeout_and_max_retries():
    get_ai_client.cache_clear()
    settings = get_settings()

    with patch("app.core.ai_client.OpenAI") as mock_openai:
        get_ai_client()

    _, kwargs = mock_openai.call_args
    assert kwargs["timeout"] == settings.openai_timeout_seconds
    assert kwargs["max_retries"] == settings.openai_max_retries
    get_ai_client.cache_clear()
