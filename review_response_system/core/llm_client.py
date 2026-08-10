"""
Calls the LLM API with the request built by prompt_builder.py. Targets
OpenAI's Chat Completions API by default since the reference prompt builder
was designed around OpenAI-specific sampling params (frequency_penalty,
presence_penalty) that don't have a direct equivalent on other providers.

Set OPENAI_API_KEY in the environment — never pass it as a literal.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .prompt_builder import ChatCompletionRequest

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class LLMRequestError(RuntimeError):
    pass


def call_openai(request: ChatCompletionRequest, api_key: str | None = None, timeout: int = 60) -> str:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMRequestError("OPENAI_API_KEY is not set and no api_key was provided.")

    body = json.dumps({
        "model": request.model,
        "messages": [{"role": "user", "content": request.prompt}],
        "frequency_penalty": request.frequency_penalty,
        "presence_penalty": request.presence_penalty,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }).encode()

    http_request = urllib.request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise LLMRequestError(f"OpenAI API returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMRequestError(f"Failed to reach OpenAI API: {exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMRequestError(f"Unexpected OpenAI API response shape: {data}") from exc
