"""Abstração de modelos (VoiceModel + ExecutorModel)."""

from __future__ import annotations

import abc
import asyncio
from collections.abc import AsyncIterator
from typing import Any


class BaseModelClient(abc.ABC):
    """Interface base para clientes de modelo (voz e executor)."""

    @abc.abstractmethod
    async def transcribe(self, audio_pcm16: bytes) -> str:
        """Transcreve áudio PCM16 para texto."""
        ...

    @abc.abstractmethod
    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Sintetiza texto em áudio PCM16 (stream de chunks)."""
        ...

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Envia mensagens para o modelo executor.
        Retorna dict com 'tool_calls' (list) e/ou 'final_response' (str).
        """
        ...


class LlamaCppRealtimeClient(BaseModelClient):
    """Implementação via WS /v1/realtime (modo único: voz + executor no mesmo modelo)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str | None = None,
        *,
        instructions: str = "Você é um assistente pessoal que conversa por voz em português do Brasil. Fale de forma curta, natural e direta, sem listas, sem markdown e sem emojis.",
        modalities: list[str] | None = None,
        chunk_ms: int = 100,
        open_timeout: float = 20.0,
        response_timeout: float = 180.0,
    ) -> None:
        from naji.core.realtime_client import (
            RealtimeClient,
            normalize_server_url,
        )

        self._base_url = normalize_server_url(base_url)
        self._api_key = api_key
        self._model = model
        self._instructions = instructions
        self._modalities = list(modalities or ["text", "audio"])
        self._chunk_ms = chunk_ms
        self._open_timeout = open_timeout
        self._response_timeout = response_timeout
        self._client: RealtimeClient | None = None
        self._ws_ctx = None
        self._ws = None

    async def __aenter__(self) -> LlamaCppRealtimeClient:
        from naji.core.realtime_client import RealtimeClient

        self._client = RealtimeClient(
            self._base_url,
            self._api_key,
            self._model,
            instructions=self._instructions,
            modalities=self._modalities,
            chunk_ms=self._chunk_ms,
            open_timeout=self._open_timeout,
            response_timeout=self._response_timeout,
        )
        await self._client.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def transcribe(self, audio_pcm16: bytes) -> str:
        import numpy as np

        from naji.core.realtime_client import transcribe_audio

        samples = np.frombuffer(audio_pcm16, dtype=np.int16)
        return await transcribe_audio(
            self._base_url,
            self._api_key,
            self._model,
            samples,
            rate=16000,
            language="pt",
        )

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        import numpy as np

        from naji.core.realtime_client import pcm_f32_to_i16, request_tts

        payload, content_type = await request_tts(
            self._base_url,
            self._api_key,
            text=text,
            voice="female",
            lang="pt",
            response_format="pcm",
            stream=True,
        )
        rate = 24000  # default
        samples = pcm_f32_to_i16(payload)
        # Yield em chunks de ~100ms
        chunk_size = rate // 10
        for start in range(0, samples.size, chunk_size):
            chunk = samples[start : start + chunk_size]
            yield chunk.astype(np.int16).tobytes()
            await asyncio.sleep(0.01)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # No modo único, o chat é feito via RealtimeClient.create_response + wait_response
        # Esta implementação é placeholder; o fluxo real usa send_audio + create_response
        if not self._client:
            raise RuntimeError("Cliente não conectado. Use async with.")
        # Para tool calling no modo único, o LFM3-Omni faz nativamente via realtime
        # Retorna formato compatível
        return {"tool_calls": [], "final_response": ""}


class LlamaCppChatClient(BaseModelClient):
    """Implementação via HTTP /v1/chat/completions (ExecutorModel no modo dual)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        from naji.core.realtime_client import normalize_server_url, server_root

        self._base_url = normalize_server_url(base_url)
        self._root = server_root(self._base_url)
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client: Any = None

    async def __aenter__(self) -> LlamaCppChatClient:
        import httpx

        from naji.core.realtime_client import auth_headers

        self._client = httpx.AsyncClient(
            base_url=self._root,
            headers=auth_headers(self._api_key),
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _post_with_retry(self, payload: dict[str, Any], retries: int = 2) -> Any:
        """POST em /v1/chat/completions com retry em erros 5xx (llama.cpp é instável)."""
        import httpx

        response = await self._client.post("/v1/chat/completions", json=payload)
        for delay in (1.0, 2.0)[:retries]:
            if response.status_code < 500:
                break
            await asyncio.sleep(delay)
            response = await self._client.post("/v1/chat/completions", json=payload)
        if response.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"servidor retornou HTTP {response.status_code} após {retries + 1} tentativas",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        return response

    async def transcribe(self, audio_pcm16: bytes) -> str:
        raise NotImplementedError("Use LlamaCppRealtimeClient ou WhisperCppClient para STT")

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        raise NotImplementedError("Use LlamaCppRealtimeClient ou TTS client para TTS")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("Cliente não conectado. Use async with.")

        payload: dict[str, Any] = {
            "model": self._model or "default",
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await self._post_with_retry(payload)
        data = response.json()

        choice = data["choices"][0]
        message = choice["message"]

        tool_calls = list(message.get("tool_calls") or [])
        return {
            "tool_calls": tool_calls,
            "final_response": message.get("content", ""),
        }


class WhisperCppClient(BaseModelClient):
    """STT via Whisper.cpp (subprocess ou server local). Placeholder."""

    async def transcribe(self, audio_pcm16: bytes) -> str:
        raise NotImplementedError("Implementar integração com Whisper.cpp")

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        raise NotImplementedError("WhisperCppClient é apenas STT")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("WhisperCppClient é apenas STT")


class KokoroTTSClient(BaseModelClient):
    """TTS via Kokoro. Placeholder."""

    async def transcribe(self, audio_pcm16: bytes) -> str:
        raise NotImplementedError("KokoroTTSClient é apenas TTS")

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        raise NotImplementedError("Implementar integração com Kokoro TTS")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("KokoroTTSClient é apenas TTS")
