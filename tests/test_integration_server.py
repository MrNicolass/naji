"""Testes de integração end-to-end contra o servidor local real.

Cobrem: preflight, TTS, STT (transcription realtime), chat completions
(com e sem tool calling), turno de voz completo via /v1/realtime e o
pipeline dual do Orchestrator (STT → Executor+Tools → TTS).

Todos os testes são pulados automaticamente se o servidor estiver fora do ar.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from conftest import synth_wav

from naji.core.models import LlamaCppChatClient, LlamaCppRealtimeClient
from naji.core.orchestrator import Orchestrator
from naji.core.realtime_client import (
    RealtimeClient,
    pcm_f32_to_i16,
    preflight,
    request_tts,
    resample_i16,
    transcribe_audio,
    wav_to_i16_mono,
)
from naji.core.tools import ToolRegistry
from naji.core.tools.datetime import get_datetime, get_datetime_schema

QUESTION = "Qual é a capital do Brasil?"


async def test_preflight(server_ok: str) -> None:
    result = await preflight(server_ok, wait_seconds=5.0)
    assert result["ok"], f"preflight falhou: {result['errors']} {result['warnings']}"
    assert result["health"]["status"] == 200
    assert result["realtime"]["ok"], f"realtime indisponível: {result['realtime']}"
    assert result["model"]["id"], "modelo não anunciado em /v1/models"
    assert "audio" in (result["model"]["output_modalities"] or [])


async def test_tts_wav_roundtrip(server_ok: str, tmp_path: Path) -> None:
    data, content_type = await request_tts(
        server_ok, None, text="Olá, teste de síntese.", response_format="wav", stream=False
    )
    assert data[:4] == b"RIFF", "resposta não é um WAV"
    assert b"WAVE" in data[:12]
    assert len(data) > 1000
    assert "wav" in content_type
    wav_path = tmp_path / "tts.wav"
    wav_path.write_bytes(data)
    samples, rate = wav_to_i16_mono(wav_path)
    assert samples.size > 0
    assert rate in (16000, 22050, 24000, 44100, 48000)


async def test_tts_pcm_float32(server_ok: str) -> None:
    data, content_type = await request_tts(
        server_ok, None, text="Olá, teste de síntese.", response_format="pcm", stream=False
    )
    assert "rate=" in content_type, f"content-type sem taxa: {content_type!r}"
    samples = pcm_f32_to_i16(data)
    assert samples.dtype == np.int16
    assert samples.size > 0
    assert np.abs(samples).max() > 0, "áudio todo zerado"


async def test_stt_transcribe(server_ok: str, tmp_path: Path) -> None:
    wav = await synth_wav(QUESTION, tmp_path / "q.wav")
    samples, rate = wav_to_i16_mono(wav)
    text = await transcribe_audio(server_ok, None, None, samples, rate, language="pt", timeout=60.0)
    assert text, "transcrição vazia"
    assert "brasil" in text.lower() or "capital" in text.lower(), f"transcrição inesperada: {text!r}"


async def test_chat_completions(server_ok: str) -> None:
    async with LlamaCppChatClient(server_ok) as client:
        result = await client.chat(
            messages=[{"role": "user", "content": "Responda apenas com a palavra: ok"}]
        )
    assert result["final_response"].strip(), "resposta vazia"
    assert result["tool_calls"] == []


async def test_chat_completions_tool_calling(server_ok: str) -> None:
    registry = ToolRegistry()
    registry.register("get_datetime", get_datetime, get_datetime_schema())
    async with LlamaCppChatClient(server_ok) as client:
        result = await client.chat(
            messages=[{"role": "user", "content": "Que horas são? Use a ferramenta."}],
            tools=registry.get_schemas(),
        )
    assert result["tool_calls"], f"esperado tool_call, veio: {result!r}"
    tc = result["tool_calls"][0]
    assert tc["function"]["name"] == "get_datetime"
    assert tc["id"], "tool_call sem id"
    args = tc["function"]["arguments"]
    args = json.loads(args) if isinstance(args, str) else args
    assert isinstance(args, dict)


async def test_orchestrator_dual_e2e(server_ok: str, tmp_path: Path) -> None:
    """Pipeline dual completo: STT (realtime) → Executor (chat+tools) → TTS."""
    wav = await synth_wav("Que horas são?", tmp_path / "q.wav")
    samples, rate = wav_to_i16_mono(wav)
    samples16 = resample_i16(samples, rate, 16000)

    registry = ToolRegistry()
    registry.register("get_datetime", get_datetime, get_datetime_schema())
    voice = LlamaCppRealtimeClient(server_ok)

    results = []
    async with LlamaCppChatClient(server_ok) as executor:
        orch = Orchestrator(
            voice_model=voice, executor_model=executor, tool_registry=registry, same_model=False
        )
        async for turn in orch.process_turn(samples16.tobytes()):
            results.append(turn)

    assert results, "nenhum turno retornado"
    last = results[-1]
    assert last.user_text.strip(), "STT não produziu texto"
    assert last.final_response.strip(), "executor não produziu resposta final"
    audio_bytes = sum(len(chunk) for chunk in last.audio_chunks)
    assert audio_bytes > 0, "TTS não produziu áudio"


async def test_realtime_voice_turn(server_ok: str, tmp_path: Path) -> None:
    """Turno de voz completo: áudio in → /v1/realtime → texto + áudio out."""
    wav = await synth_wav(QUESTION, tmp_path / "q.wav")
    samples, rate = wav_to_i16_mono(wav)
    events: list[str] = []

    async with RealtimeClient(server_ok, None, None, on_event=lambda e: events.append(e.get("type", "?"))) as rt:
        assert rt.model_name, "modelo não identificado na sessão"
        await rt.send_audio(samples, rate, realtime=False)
        await rt.create_response()
        turn = await rt.wait_response(timeout=120.0)

    assert turn.text.strip(), "resposta de texto vazia"
    assert "brasil" in turn.text.lower() or "brasília" in turn.text.lower(), (
        f"resposta inesperada: {turn.text!r}"
    )
    assert turn.audio.size > 0, "nenhum áudio de saída"
    assert turn.audio_seconds >= 0.5, f"áudio de saída curto demais: {turn.audio_seconds:.1f}s"
    assert turn.first_output_ms is not None and turn.first_output_ms < 5000
    assert "response.done" in events
    saved = turn.save_wav(tmp_path / "resposta.wav")
    assert saved is not None and saved.exists()
