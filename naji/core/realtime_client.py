"""Cliente assíncrono de /v1/realtime (migrado do MVP core.py)."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import numpy as np

DEFAULT_URL = "http://xserver:9931/v1"
DEFAULT_MODEL = "default"
DEFAULT_VOICE = "female"
DEFAULT_LANG = "pt"
DEFAULT_MODALITIES = ["text", "audio"]
DEFAULT_INSTRUCTIONS = (
    "Você é um assistente pessoal que conversa por voz em português do Brasil. "
    "Fale de forma curta, natural e direta, sem listas, sem markdown e sem emojis."
)
MIN_BUILD = 11941
MIN_BUILD_NAME = "b11941 (v0.8.0)"

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def normalize_server_url(url: str | None) -> str:
    value = (url or DEFAULT_URL).strip()
    if not value:
        raise ValueError("URL do servidor vazia")
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    parts = urlsplit(value)
    if not parts.netloc:
        raise ValueError(f"URL inválida: {url}")
    value = value.rstrip("/")
    if not value.endswith("/v1"):
        value += "/v1"
    return value


def server_root(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def http_to_ws(url: str) -> str:
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url


def auth_headers(api_key: str | None) -> dict[str, str]:
    key = (api_key or "").strip()
    if not key or key.lower() in {"none", "no-key", "sk-no-key-required"}:
        return {}
    return {"Authorization": f"Bearer {key}"}


def realtime_url(base_url: str, model: str | None = None) -> str:
    url = http_to_ws(base_url.rstrip("/")) + "/realtime"
    name = (model or "").strip()
    if name and name.lower() != DEFAULT_MODEL:
        url += "?model=" + quote(name, safe="")
    return url


def tts_url(base_url: str) -> str:
    return server_root(base_url) + "/tts"


def ws_open(uri: str, headers: dict[str, str] | None = None, open_timeout: float = 20.0):
    import websockets

    kwargs: dict[str, Any] = {
        "open_timeout": open_timeout,
        "ping_interval": 20,
        "max_size": 32 * 1024 * 1024,
    }
    try:
        return websockets.connect(uri, additional_headers=headers or None, **kwargs)
    except TypeError:
        return websockets.connect(uri, extra_headers=headers or None, **kwargs)


def _status_of(exc: Exception) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


async def probe_realtime(
    base_url: str, api_key: str | None, model: str | None, timeout: float = 20.0
) -> dict[str, Any]:
    uri = realtime_url(base_url, model)
    started = time.perf_counter()
    try:
        async with ws_open(uri, auth_headers(api_key), open_timeout=timeout) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    except Exception as exc:
        status = _status_of(exc)
        hint = ""
        if status in (404, 405, 426):
            hint = (
                f"o servidor não expõe /v1/realtime (HTTP {status}); "
                f"atualize o llama.cpp para {MIN_BUILD_NAME} ou mais novo"
            )
        return {
            "ok": False,
            "url": uri,
            "error": f"{type(exc).__name__}: {exc}",
            "hint": hint,
            "ms": round((time.perf_counter() - started) * 1000, 1),
        }
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "url": uri, "error": "resposta do WebSocket não é JSON", "hint": ""}
    if event.get("type") == "error":
        message = (event.get("error") or {}).get("message") or "erro na sessão"
        return {"ok": False, "url": uri, "error": message, "hint": "", "event": event}
    session = event.get("session") or {}
    audio = session.get("audio") or {}
    return {
        "ok": True,
        "url": uri,
        "ms": round((time.perf_counter() - started) * 1000, 1),
        "type": event.get("type"),
        "model": session.get("model"),
        "in_rate": ((audio.get("input") or {}).get("format") or {}).get("rate"),
        "out_rate": ((audio.get("output") or {}).get("format") or {}).get("rate"),
        "session": session,
    }


def _trim_props(props: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "model_path",
        "model_alias",
        "build_info",
        "version",
        "n_ctx",
        "total_slots",
        "modalities",
        "input_modalities",
        "output_modalities",
        "is_sleeping",
    )
    trimmed = {key: props[key] for key in keys if key in props}
    gen = props.get("default_generation_settings")
    if isinstance(gen, dict):
        for key in ("n_ctx", "n_predict", "temperature"):
            if key in gen:
                trimmed.setdefault(key, gen[key])
    return trimmed


def extract_model(models: dict[str, Any]) -> dict[str, Any]:
    data = models.get("data") or []
    if not data:
        return {}
    entry = data[0]
    architecture = entry.get("architecture") or entry.get("meta") or {}
    return {
        "id": entry.get("id"),
        "owned_by": entry.get("owned_by"),
        "input_modalities": architecture.get("input_modalities"),
        "output_modalities": architecture.get("output_modalities"),
    }


async def preflight(
    base_url: str,
    api_key: str | None = None,
    model: str | None = None,
    wait_seconds: float = 20.0,
    timeout: float = 15.0,
) -> dict[str, Any]:
    base = normalize_server_url(base_url)
    root = server_root(base)
    headers = auth_headers(api_key)
    result: dict[str, Any] = {
        "ok": False,
        "server": base,
        "root": root,
        "health": None,
        "props": None,
        "model": None,
        "realtime": None,
        "warnings": [],
        "errors": [],
    }
    deadline = time.perf_counter() + max(wait_seconds, 0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            try:
                response = await client.get(root + "/health", headers=headers)
                body: Any
                try:
                    body = response.json()
                except ValueError:
                    body = response.text
                result["health"] = {"status": response.status_code, "body": body}
                if response.status_code == 200:
                    break
                if response.status_code not in (503, 500):
                    result["errors"].append(f"/health respondeu HTTP {response.status_code}")
                    break
            except httpx.HTTPError as exc:
                result["health"] = {"status": None, "error": f"{type(exc).__name__}: {exc}"}
            if time.perf_counter() >= deadline:
                result["errors"].append("modelo não ficou pronto dentro do tempo de espera")
                break
            await asyncio.sleep(1.0)

        try:
            response = await client.get(root + "/props", headers=headers)
            if response.status_code == 200:
                result["props"] = _trim_props(response.json())
            else:
                result["warnings"].append(f"/props respondeu HTTP {response.status_code}")
        except (httpx.HTTPError, ValueError) as exc:
            result["warnings"].append(f"/props indisponível: {type(exc).__name__}")

        try:
            response = await client.get(base + "/models", headers=headers)
            if response.status_code == 200:
                result["model"] = extract_model(response.json())
            else:
                result["warnings"].append(f"/v1/models respondeu HTTP {response.status_code}")
        except (httpx.HTTPError, ValueError) as exc:
            result["warnings"].append(f"/v1/models indisponível: {type(exc).__name__}")

    build = (result.get("props") or {}).get("build_info") or (result.get("props") or {}).get("version") or ""
    numbers = [int(n) for n in re.findall(r"b(\d{4,})", str(build))]
    if numbers and max(numbers) < MIN_BUILD:
        result["warnings"].append(
            f"build {build} é anterior a {MIN_BUILD_NAME}; /v1/realtime e /tts podem não existir"
        )

    result["realtime"] = await probe_realtime(base, api_key, model)
    if result["realtime"].get("hint"):
        result["errors"].append(result["realtime"]["hint"])

    modalities = (result.get("model") or {}).get("output_modalities") or []
    if result["realtime"].get("ok") and modalities and "audio" not in modalities:
        result["warnings"].append("o modelo não anuncia saída de áudio em /v1/models")

    result["ok"] = bool(
        result["health"] and result["health"].get("status") == 200 and result["realtime"].get("ok")
    )
    return result


async def request_tts(
    base_url: str,
    api_key: str | None = None,
    *,
    text: str,
    voice: str | None = DEFAULT_VOICE,
    lang: str | None = DEFAULT_LANG,
    response_format: str = "wav",
    stream: bool = False,
    timeout: float = 300.0,
) -> tuple[bytes, str]:
    payload: dict[str, Any] = {
        "input": text,
        "stream": bool(stream),
        "response_format": response_format,
    }
    if voice:
        payload["voice"] = voice
    if lang:
        payload["lang"] = lang
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(tts_url(base_url), json=payload, headers=auth_headers(api_key))
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")


def rate_from_content_type(content_type: str | None, default: int = 24000) -> int:
    match = re.search(r"rate=(\d+)", content_type or "")
    return int(match.group(1)) if match else default


def pcm_f32_to_i16(data: bytes) -> np.ndarray:
    return np.clip(np.frombuffer(data, dtype="<f4") * 32767.0, -32768, 32767).astype(np.int16)


def wav_to_i16_mono(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise ValueError("o WAV precisa ser PCM16")
        rate = handle.getframerate()
        channels = handle.getnchannels()
        raw = handle.readframes(handle.getnframes())
    samples = np.frombuffer(raw, dtype="<i2")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return samples.copy(), rate


def resample_i16(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.int16, copy=False)
    count = int(round(samples.size * dst_rate / src_rate))
    if count <= 0:
        return np.zeros(0, dtype=np.int16)
    positions = np.arange(count) * (src_rate / dst_rate)
    values = np.interp(positions, np.arange(samples.size), samples.astype(np.float32))
    return np.clip(values, -32768, 32767).astype(np.int16)


def write_wav(path: str | Path, samples: np.ndarray, rate: int) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return target


def b64_pcm(samples: np.ndarray) -> str:
    return base64.b64encode(np.asarray(samples, dtype="<i2").tobytes()).decode()


def play_wav(path: str | Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return True
    except Exception:
        return False


class RealtimeError(RuntimeError):
    pass


@dataclass
class RealtimeTurn:
    text: str = ""
    audio: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int16))
    in_rate: int = 0
    out_rate: int = 0
    first_output_ms: float | None = None

    @property
    def audio_seconds(self) -> float:
        return self.audio.size / self.out_rate if self.out_rate else 0.0

    def save_wav(self, path: str | Path) -> Path | None:
        if self.audio.size == 0 or not self.out_rate:
            return None
        return write_wav(path, self.audio, self.out_rate)


class RealtimeClient:
    """Cliente assíncrono de /v1/realtime com callbacks, reutilizável pelo CLI e pelo desktop."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str | None = None,
        *,
        instructions: str = DEFAULT_INSTRUCTIONS,
        modalities: list[str] | None = None,
        chunk_ms: int = 100,
        open_timeout: float = 20.0,
        response_timeout: float = 180.0,
        on_text: Callable[[str], None] | None = None,
        on_audio: Callable[[np.ndarray], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.base_url = normalize_server_url(base_url)
        self.api_key = api_key
        self.model = model
        self.instructions = instructions
        self.modalities = list(modalities or DEFAULT_MODALITIES)
        self.chunk_ms = max(1, int(chunk_ms))
        self.open_timeout = open_timeout
        self.response_timeout = response_timeout
        self.on_text = on_text
        self.on_audio = on_audio
        self.on_error = on_error
        self.on_event = on_event
        self.uri = realtime_url(self.base_url, self.model)
        self.session: dict[str, Any] = {}
        self.model_name: str | None = None
        self.in_rate = 16000
        self.out_rate = 24000
        self._ws: Any = None
        self._cm: Any = None
        self._receiver: asyncio.Task[None] | None = None
        self._session_created = asyncio.Event()
        self._session_updated = asyncio.Event()
        self._response_done = asyncio.Event()
        self._error: str | None = None
        self._response_active = False
        self._turn_start: float | None = None
        self._text_parts: list[str] = []
        self._audio_parts: list[np.ndarray] = []
        self._first_output: float | None = None

    async def __aenter__(self) -> RealtimeClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> RealtimeClient:
        if self._ws is not None:
            return self
        self._session_created.clear()
        self._session_updated.clear()
        self._error = None
        try:
            self._cm = ws_open(self.uri, auth_headers(self.api_key), open_timeout=self.open_timeout)
            self._ws = await self._cm.__aenter__()
        except Exception as exc:
            raise RealtimeError(f"falha ao conectar em {self.uri}: {type(exc).__name__}: {exc}") from exc
        self._receiver = asyncio.create_task(self._receive_loop())
        await self._wait(self._session_created, self.open_timeout, "session.created")
        await self._send(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "instructions": self.instructions,
                    "output_modalities": self.modalities,
                },
            }
        )
        await self._wait(self._session_updated, self.open_timeout, "session.updated")
        return self

    async def close(self) -> None:
        if self._receiver is not None:
            self._receiver.cancel()
            try:
                await self._receiver
            except (asyncio.CancelledError, Exception):
                pass
            self._receiver = None
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._cm = None
        self._ws = None
        self._session_created.set()
        self._session_updated.set()
        self._response_done.set()

    async def send_audio(
        self,
        samples: np.ndarray,
        rate: int | None = None,
        *,
        chunk_ms: int | None = None,
        realtime: bool = True,
    ) -> int:
        if self._ws is None:
            raise RealtimeError("cliente não conectado")
        data = np.asarray(samples, dtype=np.int16)
        if rate and rate != self.in_rate:
            data = resample_i16(data, rate, self.in_rate)
        step = max(1, int(self.in_rate * (chunk_ms or self.chunk_ms) / 1000))
        chunks = 0
        for start in range(0, data.size, step):
            chunk = data[start : start + step]
            await self._send({"type": "input_audio_buffer.append", "audio": b64_pcm(chunk)})
            chunks += 1
            if realtime:
                await asyncio.sleep(len(chunk) / self.in_rate)
        return chunks

    async def create_response(self) -> None:
        self._reset_turn()
        self._turn_start = time.perf_counter()
        await self._send({"type": "response.create"})

    async def wait_response(self, timeout: float | None = None) -> RealtimeTurn:
        await self._wait(self._response_done, self.response_timeout if timeout is None else timeout, "response.done")
        return self.turn()

    def turn(self) -> RealtimeTurn:
        audio = np.concatenate(self._audio_parts) if self._audio_parts else np.zeros(0, dtype=np.int16)
        return RealtimeTurn(
            text="".join(self._text_parts),
            audio=audio,
            in_rate=self.in_rate,
            out_rate=self.out_rate,
            first_output_ms=self._first_output,
        )

    async def cancel(self) -> None:
        await self._send({"type": "response.cancel"})

    def _reset_turn(self) -> None:
        self._text_parts.clear()
        self._audio_parts.clear()
        self._first_output = None
        self._error = None
        self._response_active = False
        self._response_done.clear()

    def _mark_output(self) -> None:
        if self._first_output is None and self._turn_start is not None:
            self._first_output = (time.perf_counter() - self._turn_start) * 1000

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "session.created":
            self.session = event.get("session") or self.session
            audio = self.session.get("audio") or {}
            self.model_name = self.session.get("model") or self.model_name
            self.in_rate = ((audio.get("input") or {}).get("format") or {}).get("rate") or self.in_rate
            self.out_rate = ((audio.get("output") or {}).get("format") or {}).get("rate") or self.out_rate
            self._session_created.set()
        elif kind == "session.updated":
            self.session.update(event.get("session") or {})
            self._session_updated.set()
        elif kind == "response.created":
            self._response_active = True
        elif kind == "response.output_text.delta":
            self._response_active = True
            self._mark_output()
            delta = event.get("delta") or ""
            self._text_parts.append(delta)
            if self.on_text is not None:
                self.on_text(delta)
        elif kind == "response.output_audio.delta":
            self._response_active = True
            self._mark_output()
            try:
                chunk = np.frombuffer(base64.b64decode(event.get("delta") or ""), dtype="<i2").copy()
            except Exception:
                chunk = np.zeros(0, dtype=np.int16)
            if chunk.size:
                self._audio_parts.append(chunk)
            if self.on_audio is not None and chunk.size:
                self.on_audio(chunk)
        elif kind == "response.done":
            self._response_active = False
            self._response_done.set()
        elif kind == "error":
            message = (event.get("error") or {}).get("message") or "erro na sessão"
            self._error = message
            if self.on_error is not None:
                self.on_error(message)
            self._response_done.set()
            self._session_updated.set()
            self._session_created.set()
        if self.on_event is not None:
            self.on_event(event)

    async def _receive_loop(self) -> None:
        try:
            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "replace")
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    self._handle(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._error is None:
                self._error = f"conexão encerrada: {type(exc).__name__}: {exc}"
                if self.on_error is not None:
                    self.on_error(self._error)
        finally:
            self._session_created.set()
            self._session_updated.set()
            self._response_done.set()

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RealtimeError("cliente não conectado")
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as exc:
            raise RealtimeError(f"falha ao enviar {payload.get('type')}: {type(exc).__name__}: {exc}") from exc

    async def _wait(self, event: asyncio.Event, timeout: float, label: str) -> None:
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except TimeoutError as exc:
            raise RealtimeError(f"timeout aguardando {label}") from exc
        if self._error is not None:
            raise RealtimeError(self._error)


async def transcribe_audio(
    base_url: str,
    api_key: str | None,
    model: str | None,
    samples: np.ndarray,
    rate: int | None = None,
    *,
    language: str | None = None,
    timeout: float = 60.0,
) -> str:
    """Transcreve um turno de áudio usando uma sessão `/v1/realtime` do tipo `transcription`."""
    base_url = normalize_server_url(base_url)
    uri = realtime_url(base_url, model)
    data = np.asarray(samples, dtype=np.int16)
    if data.size == 0:
        return ""
    try:
        async with ws_open(uri, auth_headers(api_key), open_timeout=min(timeout, 20.0)) as ws:
            created = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if created.get("type") == "error":
                raise RealtimeError((created.get("error") or {}).get("message") or "erro ao abrir sessão")
            audio_in = ((created.get("session") or {}).get("audio") or {}).get("input") or {}
            in_rate = (audio_in.get("format") or {}).get("rate") or 16000
            if rate and rate != in_rate:
                data = resample_i16(data, rate, in_rate)

            session: dict[str, Any] = {"type": "transcription"}
            if language:
                session["audio"] = {"input": {"transcription": {"language": language}}}
            await ws.send(json.dumps({"type": "session.update", "session": session}))
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                kind = event.get("type")
                if kind == "session.updated":
                    break
                if kind == "error":
                    raise RealtimeError((event.get("error") or {}).get("message") or "erro ao configurar transcrição")

            step = max(1, in_rate // 10)
            for start in range(0, data.size, step):
                chunk = data[start : start + step]
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": b64_pcm(chunk)}))
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                kind = event.get("type")
                if kind == "conversation.item.input_audio_transcription.completed":
                    return (event.get("transcript") or "").strip()
                if kind == "error":
                    raise RealtimeError((event.get("error") or {}).get("message") or "erro na transcrição")
    except RealtimeError:
        raise
    except TimeoutError as exc:
        raise RealtimeError("timeout na transcrição") from exc
    except Exception as exc:
        raise RealtimeError(f"falha na transcrição: {type(exc).__name__}: {exc}") from exc
