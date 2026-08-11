"""
Calls the LLM API with the request built by prompt_builder.py.

Two providers are supported:
  - OpenAI Chat Completions — the reference prompt builder's sampling params
    (frequency_penalty, presence_penalty) are OpenAI-specific and are sent
    as-is.
  - Anthropic Messages API — has no equivalent for frequency_penalty /
    presence_penalty, so those two are dropped; temperature and max_tokens
    carry over directly.

Set OPENAI_API_KEY / ANTHROPIC_API_KEY in the environment — never pass a key
as a literal.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .prompt_builder import ChatCompletionRequest

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LLMRequestError(RuntimeError):
    pass


def _post_json(url: str, body: dict, headers: dict, timeout: int) -> dict:
    http_request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise LLMRequestError(f"{url} returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMRequestError(f"Failed to reach {url}: {exc.reason}") from exc


def call_openai(request: ChatCompletionRequest, api_key: str | None = None, timeout: int = 60) -> str:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMRequestError("OPENAI_API_KEY is not set and no api_key was provided.")

    data = _post_json(
        OPENAI_CHAT_COMPLETIONS_URL,
        body={
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "frequency_penalty": request.frequency_penalty,
            "presence_penalty": request.presence_penalty,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMRequestError(f"Unexpected OpenAI API response shape: {data}") from exc


def call_anthropic(request: ChatCompletionRequest, api_key: str | None = None, timeout: int = 60) -> str:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMRequestError("ANTHROPIC_API_KEY is not set and no api_key was provided.")

    headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
    body = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "messages": [{"role": "user", "content": request.prompt}],
    }

    try:
        data = _post_json(ANTHROPIC_MESSAGES_URL, body=body, headers=headers, timeout=timeout)
    except LLMRequestError as exc:
        # Some model families (e.g. reasoning-tuned ones) reject `temperature`
        # outright rather than silently ignoring it — retry without it.
        if "temperature" in str(exc) and "deprecated" in str(exc):
            body.pop("temperature")
            data = _post_json(ANTHROPIC_MESSAGES_URL, body=body, headers=headers, timeout=timeout)
        else:
            raise

    try:
        return "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
    except (KeyError, IndexError) as exc:
        raise LLMRequestError(f"Unexpected Anthropic API response shape: {data}") from exc
