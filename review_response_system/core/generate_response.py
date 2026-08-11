"""Top-level entry point: build the prompt from the four uploaded inputs,
call the LLM, return the generated review response."""

from __future__ import annotations

from .llm_client import call_anthropic, call_openai
from .models import ReviewResponseRequest
from .prompt_builder import build_review_response_prompt

DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}


def generate_review_response(
    request: ReviewResponseRequest,
    api_key: str | None = None,
    model: str | None = None,
    provider: str = "openai",
    max_words: int | None = None,
) -> str:
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Unknown provider '{provider}'. Expected one of {list(DEFAULT_MODELS)}.")

    model = model or DEFAULT_MODELS[provider]
    chat_request = build_review_response_prompt(request, model=model, max_words=max_words)

    if provider == "anthropic":
        return call_anthropic(chat_request, api_key=api_key)
    return call_openai(chat_request, api_key=api_key)
