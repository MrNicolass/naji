"""Orquestrador multi-modelo (VoiceModel + ExecutorModel)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from naji.core.models import BaseModelClient
from naji.core.tools import ToolRegistry


@dataclass
class TurnResult:
    """Resultado de um turno de conversa."""

    user_text: str
    final_response: str
    audio_chunks: list[bytes]
    tool_calls_executed: list[dict[str, Any]]


class Orchestrator:
    """
    Orquestra a conversa entre VoiceModel, ExecutorModel e Tools nativas.

    Modos:
    - same_model=True: VoiceModel == ExecutorModel (LFM3-Omni via Realtime)
    - same_model=False: VoiceModel (STT/TTS) + ExecutorModel (chat/tools) separados
    """

    def __init__(
        self,
        voice_model: BaseModelClient,
        executor_model: BaseModelClient | None = None,
        tool_registry: ToolRegistry | None = None,
        same_model: bool = True,
    ) -> None:
        self.voice_model = voice_model
        self.executor_model = executor_model or voice_model
        self.tool_registry = tool_registry or ToolRegistry()
        self.same_model = same_model
        self._conversation_history: list[dict[str, Any]] = []

    async def process_turn(self, audio_pcm16: bytes) -> AsyncIterator[TurnResult]:
        """Processa um turno completo: STT → Executor → Tools → TTS."""
        # 1. STT
        user_text = await self.voice_model.transcribe(audio_pcm16)
        if not user_text.strip():
            return

        # Adiciona ao histórico
        self._conversation_history.append({"role": "user", "content": user_text})

        # 2. Executor (com tools disponíveis)
        tools_schema = self.tool_registry.get_schemas()
        executor_response = await self.executor_model.chat(
            messages=self._conversation_history.copy(),
            tools=tools_schema if tools_schema else None,
        )

        tool_calls = executor_response.get("tool_calls", [])
        final_response = executor_response.get("final_response", "")

        # 3. Executar tool calls se houver
        tool_results = []
        for tc in tool_calls:
            name = tc["function"]["name"]
            arguments = tc["function"].get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            result = await self.tool_registry.execute(name, arguments)
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result,
                }
            )
            self._conversation_history.append(
                {"role": "assistant", "content": None, "tool_calls": [tc]}
            )
            self._conversation_history.append(
                {"role": "tool", "tool_call_id": tc["id"], "name": name, "content": result}
            )

        # 4. Se houve tool calls, pedir resposta final ao executor
        if tool_calls:
            executor_response = await self.executor_model.chat(
                messages=self._conversation_history.copy(),
                tools=tools_schema if tools_schema else None,
            )
            final_response = executor_response.get("final_response", "")

        # 5. Adicionar resposta final ao histórico
        self._conversation_history.append({"role": "assistant", "content": final_response})

        # 6. TTS streaming
        audio_chunks = []
        async for chunk in self.voice_model.synthesize(final_response):
            audio_chunks.append(chunk)
            yield TurnResult(
                user_text=user_text,
                final_response=final_response,
                audio_chunks=[chunk],
                tool_calls_executed=tool_calls,
            )

    def clear_history(self) -> None:
        self._conversation_history.clear()
