"""Testes offline do core (pipeline de áudio + tool registry), sem servidor."""

from __future__ import annotations

import re

import numpy as np

from naji.core.realtime_client import (
    b64_pcm,
    pcm_f32_to_i16,
    resample_i16,
    wav_to_i16_mono,
    write_wav,
)
from naji.core.tools import ToolRegistry, create_tool_schema
from naji.core.tools.datetime import get_datetime, get_datetime_schema


def test_resample_identity() -> None:
    samples = np.arange(1000, dtype=np.int16)
    out = resample_i16(samples, 16000, 16000)
    assert out.dtype == np.int16
    np.testing.assert_array_equal(out, samples)


def test_resample_downsample() -> None:
    samples = np.zeros(16000, dtype=np.int16)
    out = resample_i16(samples, 16000, 24000)
    assert out.size == 24000
    out2 = resample_i16(np.zeros(24000, dtype=np.int16), 24000, 16000)
    assert out2.size == 16000


def test_pcm_f32_to_i16() -> None:
    data = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype="<f4").tobytes()
    out = pcm_f32_to_i16(data)
    assert out.dtype == np.int16
    assert out[0] == 0
    assert out[1] > 16000
    assert out[2] < -16000
    assert out[3] == 32767
    assert out[4] in (-32768, -32767)


def test_wav_roundtrip(tmp_path) -> None:
    samples = (np.sin(np.linspace(0, 8 * np.pi, 8000)) * 10000).astype(np.int16)
    path = write_wav(tmp_path / "roundtrip.wav", samples, 16000)
    loaded, rate = wav_to_i16_mono(path)
    assert rate == 16000
    np.testing.assert_array_equal(loaded, samples)


def test_b64_pcm_roundtrip() -> None:
    samples = np.array([1, -2, 3], dtype="<i2")
    import base64

    decoded = np.frombuffer(base64.b64decode(b64_pcm(samples)), dtype="<i2")
    np.testing.assert_array_equal(decoded, samples)


def test_tool_registry_execute_datetime() -> None:
    import asyncio

    registry = ToolRegistry()
    registry.register("get_datetime", get_datetime, get_datetime_schema())
    result = asyncio.run(registry.execute("get_datetime", {}))
    assert not result.startswith("Erro")
    assert re.search(r"\d{2} de [A-Z][a-zç]+ de \d{4}, \d{2}:\d{2}", result), result


def test_tool_registry_unknown_tool() -> None:
    import asyncio

    registry = ToolRegistry()
    result = asyncio.run(registry.execute("nao_existe", {}))
    assert "não encontrada" in result


def test_tool_registry_schema_format() -> None:
    schema = create_tool_schema(
        name="demo",
        description="ferramenta de teste",
        parameters={"x": {"type": "number"}},
        required=["x"],
    )
    registry = ToolRegistry()
    registry.register("demo", lambda x: x, schema)
    schemas = registry.get_schemas()
    assert len(schemas) == 1
    entry = schemas[0]
    assert entry["type"] == "function"
    assert entry["function"]["name"] == "demo"
    assert entry["function"]["parameters"]["required"] == ["x"]
    assert registry.list_tools() == ["demo"]
