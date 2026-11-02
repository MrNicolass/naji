from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import core

WEB_DIR = Path(__file__).resolve().parent / "web"

CONFIG: dict[str, Any] = {
    "server": core.DEFAULT_URL,
    "api_key": None,
    "model": core.DEFAULT_MODEL,
    "instructions": core.DEFAULT_INSTRUCTIONS,
    "voice": core.DEFAULT_VOICE,
    "lang": core.DEFAULT_LANG,
    "modalities": list(core.DEFAULT_MODALITIES),
    "debug": False,
}

app = FastAPI(title="Naji", docs_url=None, redoc_url=None)


class TtsBody(BaseModel):
    input: str
    voice: str | None = None
    lang: str | None = None
    response_format: str = "wav"
    stream: bool = True
    server: str | None = None


class TranscribeBody(BaseModel):
    audio: str
    rate: int = 16000
    language: str | None = None
    server: str | None = None
    model: str | None = None


def validate_server(value: str | None) -> str:
    if not value:
        return CONFIG["server"]
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise HTTPException(status_code=400, detail="endpoint deve ser http://host:porta[/v1]")
    return core.normalize_server_url(value)


def log(message: str) -> None:
    print(f"[naji] {message}", flush=True)


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    return {
        "server": CONFIG["server"],
        "model": CONFIG["model"],
        "instructions": CONFIG["instructions"],
        "voice": CONFIG["voice"],
        "lang": CONFIG["lang"],
        "modalities": CONFIG["modalities"],
        "has_api_key": bool(core.auth_headers(CONFIG["api_key"])),
        "defaults": {
            "server": core.DEFAULT_URL,
            "instructions": core.DEFAULT_INSTRUCTIONS,
            "modalities": core.DEFAULT_MODALITIES,
            "voice": core.DEFAULT_VOICE,
            "lang": core.DEFAULT_LANG,
        },
        "min_build": core.MIN_BUILD_NAME,
    }


@app.get("/api/check")
async def api_check(server: str | None = None, tts: bool = True, wait: float = 20.0, model: str | None = None) -> dict[str, Any]:
    base = validate_server(server)
    result = await core.preflight(base, CONFIG["api_key"], model or CONFIG["model"], wait_seconds=wait)
    if tts and result.get("ok"):
        started = time.perf_counter()
        try:
            payload, content_type = await core.request_tts(
                base,
                CONFIG["api_key"],
                text="Teste de voz.",
                voice=CONFIG["voice"],
                lang=CONFIG["lang"],
                response_format="pcm",
                stream=True,
            )
            rate = core.rate_from_content_type(content_type)
            samples = core.pcm_f32_to_i16(payload)
            result["tts"] = {
                "ok": True,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "rate": rate,
                "seconds": round(samples.size / rate, 2),
                "bytes": len(payload),
            }
        except Exception as exc:
            result["tts"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return result


@app.post("/api/tts")
async def api_tts(body: TtsBody):
    base = validate_server(body.server)
    payload: dict[str, Any] = {
        "input": body.input,
        "stream": bool(body.stream),
        "response_format": body.response_format,
    }
    if body.voice:
        payload["voice"] = body.voice
    if body.lang:
        payload["lang"] = body.lang

    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0, read=300.0))
    request = client.build_request(
        "POST",
        core.tts_url(base),
        json=payload,
        headers=core.auth_headers(CONFIG["api_key"]),
    )
    try:
        response = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"falha ao conectar no llama-server: {exc}") from exc
    if response.status_code >= 400:
        detail = (await response.aread()).decode("utf-8", "replace")[:400]
        await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=response.status_code, detail=detail or "erro em /tts")

    async def iterator():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    media_type = response.headers.get("content-type", "application/octet-stream")
    return StreamingResponse(iterator(), media_type=media_type)


@app.post("/api/transcribe")
async def api_transcribe(body: TranscribeBody) -> dict[str, Any]:
    base = validate_server(body.server)
    try:
        samples = np.frombuffer(base64.b64decode(body.audio), dtype="<i2").copy()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"áudio inválido: {exc}") from exc
    if samples.size == 0:
        return {"text": ""}
    try:
        text = await core.transcribe_audio(
            base,
            CONFIG["api_key"],
            body.model or CONFIG["model"],
            samples,
            body.rate,
            language=body.language,
        )
    except core.RealtimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"text": text}


@app.websocket("/ws/realtime")
async def realtime_proxy(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        base = validate_server(websocket.query_params.get("server"))
    except HTTPException as exc:
        await websocket.send_text(json.dumps({"type": "error", "error": {"message": str(exc.detail)}}))
        await websocket.close()
        return

    model = websocket.query_params.get("model") or CONFIG["model"]
    uri = core.realtime_url(base, model)
    log(f"abrindo sessão em {uri}")
    try:
        upstream = await core.ws_open(uri, core.auth_headers(CONFIG["api_key"]), 20)
    except Exception as exc:
        message = f"falha ao conectar em {uri}: {type(exc).__name__}: {exc}"
        log(message)
        await websocket.send_text(json.dumps({"type": "error", "error": {"message": message}}))
        await websocket.close()
        return

    async with upstream as up:
        async def client_to_server() -> None:
            try:
                while True:
                    message = await websocket.receive_text()
                    if CONFIG["debug"]:
                        try:
                            log("-> " + json.loads(message).get("type", "?"))
                        except Exception:
                            log("-> mensagem inválida")
                    await up.send(message)
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                if CONFIG["debug"]:
                    log(f"cliente encerrou: {type(exc).__name__}")
            finally:
                await up.close()

        async def server_to_client() -> None:
            try:
                async for message in up:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8", "replace")
                    if CONFIG["debug"]:
                        try:
                            event = json.loads(message)
                            kind = event.get("type", "?")
                            size = len(event.get("delta", "")) if isinstance(event.get("delta"), str) else 0
                            log(f"<- {kind}" + (f" ({size} b64)" if size else ""))
                        except Exception:
                            log("<- mensagem inválida")
                    await websocket.send_text(message)
            except Exception as exc:
                if CONFIG["debug"]:
                    log(f"servidor encerrou: {type(exc).__name__}")

        await asyncio.gather(client_to_server(), server_to_client())

    try:
        await websocket.close()
    except Exception:
        pass


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interface web para testar voz em tempo real no llama-server (LFM3-Omni).")
    parser.add_argument("--url", default=core.DEFAULT_URL, help=f"endpoint do llama-server (default: {core.DEFAULT_URL})")
    parser.add_argument("--api-key", default=None, help="API key do llama-server")
    parser.add_argument("--model", default=core.DEFAULT_MODEL, help="nome do modelo (router mode)")
    parser.add_argument("--host", default="127.0.0.1", help="host local da interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="porta local da interface (default: 8765)")
    parser.add_argument("--voice", default=core.DEFAULT_VOICE, choices=["female", "male"], help="voz padrão do TTS")
    parser.add_argument("--lang", default=core.DEFAULT_LANG, help="idioma padrão do TTS")
    parser.add_argument("--instructions", default=core.DEFAULT_INSTRUCTIONS, help="system prompt padrão da conversa")
    parser.add_argument("--modalities", default="text,audio", help="text, audio ou text,audio")
    parser.add_argument("--no-browser", action="store_true", help="não abrir o navegador automaticamente")
    parser.add_argument("--debug", action="store_true", help="mostrar todos os eventos do WebSocket no console")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    CONFIG["server"] = core.normalize_server_url(args.url)
    CONFIG["api_key"] = args.api_key
    CONFIG["model"] = args.model
    CONFIG["voice"] = args.voice
    CONFIG["lang"] = args.lang
    CONFIG["instructions"] = args.instructions
    CONFIG["modalities"] = [item.strip() for item in args.modalities.split(",") if item.strip()]
    CONFIG["debug"] = args.debug

    url = f"http://{args.host}:{args.port}"
    log(f"interface em {url}")
    log(f"llama-server em {CONFIG['server']}")
    if not CONFIG["api_key"]:
        log("sem API key (use --api-key se o servidor exigir)")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info" if args.debug else "warning")


if __name__ == "__main__":
    main()
