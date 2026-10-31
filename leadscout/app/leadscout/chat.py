"""Plain chat with the self-hosted model, proxied so the browser never sees the LLM key.

The browser posts the conversation; the server streams the reply back as Server-Sent Events:
    data: {"t": "<answer text>"}      answer tokens
    data: {"r": "<reasoning text>"}   reasoning tokens (only when reasoning is switched on)
    data: {"error": "..."}            a failure; the stream then ends
    data: {"done": true, "tokens": n}
No web access and no tools: this is the bare model. Conversations are not stored on the server.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Literal

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from .config import settings
from .web import require_csrf, require_session

log = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGES = 60
MAX_TOTAL_CHARS = 120_000
MAX_REPLY_TOKENS = 4096

SYSTEM_PROMPT = (
    "You are a helpful assistant for the staff of an IT managed-services and security consultancy. "
    "Answer clearly and concisely. You have no internet access and no tools in this chat, and your "
    "knowledge has a cutoff date: say so when a question depends on current information. "
    "When you are unsure, say so instead of guessing."
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=60_000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    reasoning: bool = False

    @model_validator(mode="after")
    def _check(self) -> "ChatIn":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        if sum(len(m.content) for m in self.messages) > MAX_TOTAL_CHARS:
            raise ValueError("conversation is too long; start a new chat")
        return self


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def stream_completion(messages: list[dict[str, str]], reasoning: bool) -> AsyncIterator[dict[str, Any]]:
    """Yield {"t"|"r": text} deltas from vLLM, then {"done": True}. Raises on transport errors."""
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "stream": True,
        "max_tokens": MAX_REPLY_TOKENS,
        "temperature": 0.6 if reasoning else 0.7,
        "chat_template_kwargs": {"enable_thinking": reasoning},
        "stream_options": {"include_usage": True},
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    tokens = 0
    timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")[:300]
                raise RuntimeError(f"model returned HTTP {resp.status_code}: {body}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    tokens = chunk["usage"].get("completion_tokens", tokens)
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    r = delta.get("reasoning_content") or delta.get("reasoning")
                    if r:
                        yield {"r": r}
                    if delta.get("content"):
                        yield {"t": delta["content"]}
    yield {"done": True, "tokens": tokens}


@router.post("/ui/api/chat", dependencies=[Depends(require_csrf)], include_in_schema=False)
async def ui_chat(body: ChatIn, user: dict = Depends(require_session)):
    msgs = [m.model_dump() for m in body.messages]
    log.info("chat: %s, %d message(s), reasoning=%s", user.get("email"), len(msgs), body.reasoning)

    async def gen() -> AsyncIterator[str]:
        try:
            async for event in stream_completion(msgs, body.reasoning):
                yield _sse(event)
        except httpx.ConnectError:
            yield _sse({"error": "The model is offline. Start the GPU instance and try again."})
        except httpx.TimeoutException:
            yield _sse({"error": "The model took too long to respond."})
        except Exception as exc:  # noqa: BLE001
            log.warning("chat failed: %s", exc)
            yield _sse({"error": f"Chat failed: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
