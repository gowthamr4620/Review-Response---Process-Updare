"""Top-level entry point: build the prompt from the four uploaded inputs,
call the LLM, return the generated review response."""

from __future__ import annotations

from .llm_client import call_openai
from .models import ReviewResponseRequest
from .prompt_builder import build_review_response_prompt


def generate_review_response(
    request: ReviewResponseRequest,
    api_key: str | None = None,
    model: str = "gpt-4.1-mini",
) -> str:
    chat_request = build_review_response_prompt(request, model=model)
    return call_openai(chat_request, api_key=api_key)
