from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import core


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=core.DEFAULT_URL, help=f"URL base do llama-server (default: {core.DEFAULT_URL})")
    parser.add_argument("--api-key", default=None, help="API key do llama-server (--api-key)")
    parser.add_argument("--model", default=core.DEFAULT_MODEL, help="nome do modelo (router mode)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Diagnóstico e testes de voz do llama-server (LFM3-Omni) sem interface.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="valida health, props, /v1/models, /v1/realtime e /tts")
    add_common(check)
    check.add_argument("--wait", type=float, default=20.0, help="segundos aguardando o modelo carregar")
    check.add_argument("--no-tts", action="store_true", help="não testar /tts")
    check.add_argument("--text", default="Olá, isto é um teste de síntese de voz.", help="texto do teste de /tts")
    check.add_argument("--out", default="tts_check.wav", help="arquivo WAV gerado pelo teste de /tts")
    check.add_argument("--json", action="store_true", help="imprimir o resultado completo em JSON")

    tts = sub.add_parser("tts", help="gera fala via POST /tts")
    add_common(tts)
    tts.add_argument("text", nargs="+", help="texto a sintetizar")
    tts.add_argument("--out", default="tts.wav", help="arquivo de saída")
    tts.add_argument("--voice", default=core.DEFAULT_VOICE, choices=["female", "male"], help="voz do LFM3")
    tts.add_argument("--lang", default=core.DEFAULT_LANG, help="código de idioma (pt, en, ...)")
    tts.add_argument("--format", default="wav", choices=["wav", "pcm"], help="formato retornado pelo servidor")
    tts.add_argument("--no-stream", action="store_true", help="pedir a resposta completa de uma vez")
    tts.add_argument("--play", action="store_true", help="tocar o WAV no Windows")

    file_cmd = sub.add_parser("file", help="envia um WAV como turno de conversa em /v1/realtime")
    add_common(file_cmd)
    file_cmd.add_argument("wav", help="arquivo PCM16 de entrada")
    file_cmd.add_argument("--instructions", default=core.DEFAULT_INSTRUCTIONS, help="system prompt da conversa")
    file_cmd.add_argument(
        "--modalities",
        default="text,audio",
        help="text, audio ou text,audio (default: text,audio)",
    )
    file_cmd.add_argument("--chunk-ms", type=int, default=100, help="tamanho do chunk enviado")
    file_cmd.add_argument("--no-realtime", action="store_true", help="enviar o arquivo o mais rápido possível")
    file_cmd.add_argument("--out", default="response.wav", help="onde salvar a fala gerada")
    return parser


def parse_modalities(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    allowed = {"text", "audio"}
    invalid = [item for item in items if item not in allowed]
    if invalid or not items:
        raise SystemExit(f"--modalities inválido: {value!r} (use text, audio ou text,audio)")
    return items


def print_summary(result: dict) -> None:
    health = result.get("health") or {}
    props = result.get("props") or {}
    model = result.get("model") or {}
    realtime = result.get("realtime") or {}

    def mark(ok: bool) -> str:
        return "OK  " if ok else "FALHA"

    print(f"Servidor: {result['server']}")
    print(f"[{mark(health.get('status') == 200)}] /health -> {health.get('status')} {health.get('body') if health.get('status') != 200 else ''}")
    if props:
        print(f"[{mark(True)}] /props -> build={props.get('build_info') or props.get('version') or '?'} modelo={props.get('model_path') or props.get('model_alias') or '?'}")
    else:
        print("[AVISO] /props indisponível")
    if model:
        print(f"[{mark(True)}] /v1/models -> {model.get('id')} entrada={model.get('input_modalities')} saida={model.get('output_modalities')}")
    else:
        print("[AVISO] /v1/models indisponível")
    if realtime.get("ok"):
        print(
            f"[OK   ] /v1/realtime -> modelo={realtime.get('model')} "
            f"entrada={realtime.get('in_rate')} Hz saida={realtime.get('out_rate')} Hz ({realtime.get('ms')} ms)"
        )
    else:
        print(f"[FALHA] /v1/realtime -> {realtime.get('error')}")
    for warning in result.get("warnings") or []:
        print(f"[AVISO] {warning}")
    for error in result.get("errors") or []:
        print(f"[ERRO ] {error}")


async def cmd_check(args: argparse.Namespace) -> int:
    result = await core.preflight(args.url, args.api_key, args.model, wait_seconds=args.wait)
    tts_info = None
    if not args.no_tts and result.get("ok"):
        started = time.perf_counter()
        try:
            payload, content_type = await core.request_tts(
                result["server"],
                args.api_key,
                text=args.text,
                voice=core.DEFAULT_VOICE,
                lang=core.DEFAULT_LANG,
                response_format="pcm",
                stream=True,
            )
            elapsed = (time.perf_counter() - started) * 1000
            rate = core.rate_from_content_type(content_type)
            samples = core.pcm_f32_to_i16(payload)
            path = core.write_wav(args.out, samples, rate)
            tts_info = {
                "ok": True,
                "ms": round(elapsed, 1),
                "bytes": len(payload),
                "rate": rate,
                "seconds": round(samples.size / rate, 2),
                "file": str(path),
            }
        except Exception as exc:
            tts_info = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    skipped_tts = args.no_tts or not result.get("ok")
    if args.json:
        result["tts"] = tts_info
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_summary(result)
        if tts_info and tts_info.get("ok"):
            print(f"[OK   ] /tts -> {tts_info['seconds']}s @ {tts_info['rate']} Hz em {tts_info['ms']:.0f} ms -> {tts_info['file']}")
        elif tts_info:
            print(f"[FALHA] /tts -> {tts_info['error']}")
        elif skipped_tts:
            print("[AVISO] /tts não testado")
    return 0 if result.get("ok") and (tts_info is None or tts_info.get("ok")) else 1


async def cmd_tts(args: argparse.Namespace) -> int:
    text = " ".join(args.text)
    payload, content_type = await core.request_tts(
        args.url,
        args.api_key,
        text=text,
        voice=args.voice,
        lang=args.lang,
        response_format=args.format,
        stream=not args.no_stream,
    )
    rate = core.rate_from_content_type(content_type)
    if args.format == "pcm":
        samples = core.pcm_f32_to_i16(payload)
        path = core.write_wav(args.out, samples, rate)
    else:
        path = Path(args.out)
        path.write_bytes(payload)
        samples = None
    seconds = f"{samples.size / rate:.2f}s" if samples is not None else f"{len(payload)} bytes"
    print(f"{seconds} @ {rate} Hz -> {path}")
    if args.play:
        print("tocando..." if core.play_wav(path) else "reprodução indisponível neste sistema")
    return 0


async def cmd_file(args: argparse.Namespace) -> int:
    base = core.normalize_server_url(args.url)
    samples, rate = core.wav_to_i16_mono(args.wav)
    modalities = parse_modalities(args.modalities)
    print(f"conectando em {core.realtime_url(base, args.model)}")
    async with core.RealtimeClient(
        base,
        args.api_key,
        args.model,
        instructions=args.instructions,
        modalities=modalities,
        chunk_ms=args.chunk_ms,
        on_text=lambda delta: print(delta, end="", flush=True),
    ) as client:
        print(f"sessao: modelo={client.model_name} entrada={client.in_rate} Hz saida={client.out_rate} Hz")
        chunks = await client.send_audio(samples, rate, realtime=not args.no_realtime)
        print(f"enviados {chunks} chunks ({samples.size / rate:.2f}s de audio)")
        await client.create_response()
        turn = await client.wait_response()
    print()
    if turn.text:
        print("texto:", turn.text)
    path = turn.save_wav(args.out)
    if path is not None:
        print(f"audio: {turn.audio_seconds:.2f}s -> {path}")
    if turn.first_output_ms is not None:
        delta_ms = turn.first_output_ms
        if delta_ms >= 0:
            print(f"primeiro output {delta_ms:.0f} ms apos o fim da entrada")
        else:
            print(f"output comecou {-delta_ms:.0f} ms antes do fim da entrada")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    handlers = {"check": cmd_check, "tts": cmd_tts, "file": cmd_file}
    try:
        return asyncio.run(handlers[args.command](args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"erro: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
