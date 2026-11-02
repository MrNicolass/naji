"""Data e hora local formatada PT-BR."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


async def get_datetime(timezone: str | None = None) -> str:
    """
    Retorna data e hora atual formatada em PT-BR.

    Args:
        timezone: IANA timezone (ex.: "America/Sao_Paulo"). Se None, usa local.

    Returns:
        String formatada: "Sábado, 01 de Novembro de 2026, 14:30"
    """
    try:
        tz = ZoneInfo(timezone) if timezone else datetime.now().astimezone().tzinfo
        now = datetime.now(tz)

        meses = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        dias_semana = [
            "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
            "Sexta-feira", "Sábado", "Domingo"
        ]

        dia_semana = dias_semana[now.weekday()]
        mes = meses[now.month - 1]

        return f"{dia_semana}, {now.day:02d} de {mes} de {now.year}, {now.strftime('%H:%M')}"

    except Exception as exc:
        return f"Erro ao obter data/hora: {type(exc).__name__}: {exc}"


def get_datetime_schema() -> dict:
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="get_datetime",
        description="Retorna data e hora atual formatada em português do Brasil.",
        parameters={
            "timezone": {
                "type": "string",
                "description": "Timezone IANA (ex.: America/Sao_Paulo). Opcional.",
            }
        },
        required=[],
    )
