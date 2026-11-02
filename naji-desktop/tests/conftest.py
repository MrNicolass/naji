"""Fixtures compartilhadas dos testes do Naji desktop."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SERVER_URL = "http://xserver:9931/v1"


def _root(base: str) -> str:
    base = base.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


@pytest.fixture(scope="session")
def server_url() -> str:
    return SERVER_URL


@pytest.fixture(scope="session")
def server_ok(server_url: str) -> str:
    """Pula os testes de integração se o xserver estiver fora do ar."""
    try:
        response = httpx.get(_root(server_url) + "/health", timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"xserver indisponível em {server_url}: {type(exc).__name__}: {exc}")
    return server_url


async def synth_wav(text: str, out: Path) -> Path:
    """Sintetiza `text` em WAV PCM16 via /tts e grava em `out`."""
    from naji.core.realtime_client import request_tts

    data, _ = await request_tts(SERVER_URL, None, text=text, response_format="wav", stream=False)
    out.write_bytes(data)
    return out
