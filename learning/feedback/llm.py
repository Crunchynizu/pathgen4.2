"""A small client for the private llama.cpp server running Qwen (docs/rag.md, "Runtime sequence").

It calls the server's OpenAI-compatible chat endpoint with a short timeout and a short output
cap, and returns plain text. Any problem raises LlmError, and the caller keeps the fallback text.
Standard library only, no Django.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request


class LlmError(Exception):
    """The model couldn't answer in time or answered badly. The message is for the logs."""


def complete(base_url: str, messages: list, *, model: str, timeout: float, max_tokens: int) -> str:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "top_p": 0.9,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(64_000).decode("utf-8"))
    except (socket.timeout, TimeoutError) as error:
        raise LlmError(f"timed out after {timeout:g} s") from error
    except urllib.error.HTTPError as error:
        raise LlmError(f"server answered {error.code}") from error
    except (urllib.error.URLError, OSError) as error:
        raise LlmError(f"server unreachable ({getattr(error, 'reason', error)})") from error
    except (ValueError, UnicodeDecodeError) as error:
        raise LlmError("server sent something that isn't JSON") from error
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise LlmError("server reply has no text") from error
    if not isinstance(text, str):
        raise LlmError("server reply has no text")
    return text


def healthy(base_url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False
