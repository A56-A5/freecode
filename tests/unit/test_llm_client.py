"""
Phase 3 (ApiFreeLLM client) unit tests.

Uses httpx.MockTransport — no real network.
"""
from __future__ import annotations

import json

import httpx
import pytest

from freecode.config.settings import LLMSettings
from freecode.domain.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMForbiddenError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
    LLMTransportError,
)
from freecode.llm import ApiFreeLLMClient, ChatRequest, ChatResponse
from freecode.llm.request import ChatRequest as ChatRequestDirect
from freecode.llm.response import ResponseFeatures


def _json_response(
    status: int,
    body: dict,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        headers={"Content-Type": "application/json", **(headers or {})},
        content=json.dumps(body).encode("utf-8"),
    )


def _settings(**kwargs) -> LLMSettings:
    base = {
        "endpoint": "https://apifreellm.com/api/v1/chat",
        "model": "apifreellm",
        "timeout_seconds": 30.0,
        "api_key": "test-key",
    }
    base.update(kwargs)
    return LLMSettings(**base)


class TestChatRequest:
    def test_to_body(self):
        req = ChatRequest(message="hello", model="apifreellm")
        assert req.to_body() == {"message": "hello", "model": "apifreellm"}

    def test_rejects_empty_message(self):
        with pytest.raises(ValueError, match="non-empty"):
            ChatRequest(message="   ")

    def test_rejects_empty_model(self):
        with pytest.raises(ValueError, match="model"):
            ChatRequest(message="hi", model="")


class TestChatResponse:
    def test_from_mapping_full(self):
        data = {
            "success": True,
            "response": "Hello there",
            "tier": "community",
            "features": {
                "unlimited": True,
                "delaySeconds": 25,
                "priorityProcessing": False,
            },
        }
        resp = ChatResponse.from_mapping(data)
        assert resp.text == "Hello there"
        assert resp.success is True
        assert resp.tier == "community"
        assert resp.delay_seconds == 25.0
        assert resp.features.unlimited is True
        assert resp.features.priority_processing is False

    def test_from_mapping_minimal(self):
        resp = ChatResponse.from_mapping({"response": "x"})
        assert resp.text == "x"
        assert resp.features.delay_seconds is None

    def test_features_snake_and_camel(self):
        f = ResponseFeatures.from_mapping({"delay_seconds": 20})
        assert f.delay_seconds == 20.0


class TestApiFreeLLMClientSuccess:
    @pytest.mark.asyncio
    async def test_send_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert str(request.url) == "https://apifreellm.com/api/v1/chat"
            assert request.headers["Authorization"] == "Bearer test-key"
            body = json.loads(request.content.decode())
            assert body == {"message": "ping", "model": "apifreellm"}
            return _json_response(
                200,
                {
                    "success": True,
                    "response": "pong",
                    "tier": "community",
                    "features": {"delaySeconds": 25, "unlimited": True},
                },
            )

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            result = await client.send("ping")

        assert isinstance(result, ChatResponse)
        assert result.text == "pong"
        assert result.delay_seconds == 25.0
        assert result.tier == "community"

    @pytest.mark.asyncio
    async def test_send_request_object(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            assert body["model"] == "custom-model"
            return _json_response(200, {"success": True, "response": "ok"})

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            result = await client.send_request(
                ChatRequestDirect(message="hi", model="custom-model")
            )
        assert result.text == "ok"

    @pytest.mark.asyncio
    async def test_send_overrides_model(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            assert body["model"] == "override"
            return _json_response(200, {"response": "ok"})

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            result = await client.send("hi", model="override")
        assert result.text == "ok"

    @pytest.mark.asyncio
    async def test_no_api_key_omits_authorization(self):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization", "")
            return _json_response(200, {"response": "ok"})

        transport = httpx.MockTransport(handler)
        settings = _settings(api_key=None)
        async with ApiFreeLLMClient(settings, transport=transport) as client:
            await client.send("hi")
        assert seen["auth"] == ""


class TestApiFreeLLMClientErrors:
    @pytest.mark.asyncio
    async def test_401_raises_auth(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(401, {"error": "Invalid API key"})

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMAuthError, match="Invalid API key") as exc:
                await client.send("hi")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_403_raises_forbidden(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(403, {"message": "not eligible"})

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMForbiddenError, match="not eligible"):
                await client.send("hi")

    @pytest.mark.asyncio
    async def test_400_raises_bad_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(400, {"error": "Missing parameters"})

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMBadRequestError, match="Missing parameters"):
                await client.send("hi")

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_with_retry_after(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                429,
                {"error": "Rate limit"},
                headers={"Retry-After": "20"},
            )

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMRateLimitError, match="Rate limit") as exc:
                await client.send("hi")
        assert exc.value.retry_after_seconds == 20.0
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_500_raises_server_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(503, {"error": "upstream down"})

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMServerError) as exc:
                await client.send("hi")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_success_false_raises_response_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(
                200,
                {"success": False, "error": "model unavailable"},
            )

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMResponseError, match="model unavailable"):
                await client.send("hi")

    @pytest.mark.asyncio
    async def test_non_json_200_raises_response_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                content=b"not json at all",
                headers={"Content-Type": "text/plain"},
            )

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMResponseError, match="non-JSON"):
                await client.send("hi")

    @pytest.mark.asyncio
    async def test_timeout_raises_transport_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(
            _settings(timeout_seconds=1.0),
            transport=transport,
        ) as client:
            with pytest.raises(LLMTransportError, match="timed out"):
                await client.send("hi")

    @pytest.mark.asyncio
    async def test_connection_error_raises_transport_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        transport = httpx.MockTransport(handler)
        async with ApiFreeLLMClient(_settings(), transport=transport) as client:
            with pytest.raises(LLMTransportError, match="transport error"):
                await client.send("hi")


class TestClientConstruction:
    def test_has_api_key(self):
        assert ApiFreeLLMClient(_settings(api_key="x")).has_api_key is True
        assert ApiFreeLLMClient(_settings(api_key=None)).has_api_key is False

    def test_endpoint_and_model_properties(self):
        client = ApiFreeLLMClient(_settings())
        assert client.endpoint.endswith("/chat")
        assert client.model == "apifreellm"
