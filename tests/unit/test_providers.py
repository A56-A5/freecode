"""Provider router + Groq/ApiFreeLLM multi-backend tests."""
from __future__ import annotations

import json

import httpx
import pytest

from freecode.domain.errors import LLMRateLimitError
from freecode.llm.providers.groq import GroqProvider
from freecode.llm.providers.router import ProviderRouter
from freecode.llm.response import ChatResponse, ResponseFeatures


class FakeProvider:
    def __init__(self, name: str, *, fail: bool = False, text: str = "ok") -> None:
        self.name = name
        self._fail = fail
        self._text = text
        self.has_api_key = True
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def send(self, message: str, *, model: str | None = None) -> ChatResponse:
        self.calls += 1
        if self._fail:
            raise LLMRateLimitError(
                "Community daily request limit (50 requests / 24h) exceeded.",
                status_code=429,
            )
        return ChatResponse(text=self._text, features=ResponseFeatures())

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_router_failover_on_daily_quota():
    a = FakeProvider("apifreellm", fail=True)
    b = FakeProvider("groq", text="from-groq")
    router = ProviderRouter([a, b])
    out = await router.send("hi")
    assert out.text == "from-groq"
    assert a.calls == 1
    assert b.calls == 1
    assert router.active_name == "groq"


@pytest.mark.asyncio
async def test_router_force_provider():
    a = FakeProvider("apifreellm", text="a")
    b = FakeProvider("groq", text="b")
    router = ProviderRouter([a, b])
    assert router.force("groq")
    out = await router.send("x")
    assert out.text == "b"


@pytest.mark.asyncio
async def test_groq_parses_openai_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "choices": [{"message": {"role": "assistant", "content": "hello groq"}}],
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    p = GroqProvider(api_keys=("k1",), transport=transport)
    async with p:
        chat = await p.send("hi")
    assert chat.text == "hello groq"


@pytest.mark.asyncio
async def test_groq_rotates_keys_on_429():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        auth = request.headers.get("Authorization", "")
        if "k1" in auth:
            return httpx.Response(429, json={"error": {"message": "Rate limit reached"}})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    p = GroqProvider(api_keys=("k1", "k2"), transport=transport)
    async with p:
        chat = await p.send("hi")
    assert chat.text == "ok"
    assert calls["n"] == 2


def test_scheduler_no_floor_for_fast_provider():
    from freecode.llm.scheduler import Scheduler, TimerMode
    from freecode.config.settings import SchedulerSettings

    sched = Scheduler(SchedulerSettings(cooldown_floor_seconds=20.0))
    sched.record_success(0.0, apply_floor=False)
    assert sched.mode is TimerMode.IDLE
    assert sched.remaining_seconds == 0.0


def test_groq_model_list_contains_instant():
    from freecode.llm.providers.groq import GROQ_MODELS, DEFAULT_MODEL

    assert DEFAULT_MODEL in GROQ_MODELS
    assert "llama-3.3-70b-versatile" in GROQ_MODELS
