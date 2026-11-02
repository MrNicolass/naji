"""Clima via Open-Meteo + IP-API (sem chave)."""

from __future__ import annotations

import httpx


async def get_weather(latitude: float | None = None, longitude: float | None = None, unit: str = "celsius") -> str:
    """
    Obtém clima atual. Se lat/lon não fornecidos, usa geolocalização por IP.

    Args:
        latitude: Latitude (opcional)
        longitude: Longitude (opcional)
        unit: "celsius" ou "fahrenheit"

    Returns:
        String formatada com clima atual em PT-BR.
    """
    # Geolocalização por IP se necessário
    if latitude is None or longitude is None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("http://ip-api.com/json/")
                resp.raise_for_status()
                data = resp.json()
                latitude = data.get("lat")
                longitude = data.get("lon")
                city = data.get("city", "localização atual")
        except Exception as exc:
            return f"Erro ao obter localização: {type(exc).__name__}: {exc}"
    else:
        city = "localização informada"

    if latitude is None or longitude is None:
        return "Erro: não foi possível determinar localização"

    # Open-Meteo
    try:
        temp_unit = "celsius" if unit == "celsius" else "fahrenheit"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "temperature_unit": temp_unit,
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            resp.raise_for_status()
            data = resp.json()

        cw = data.get("current_weather", {})
        temp = cw.get("temperature")
        wind = cw.get("windspeed")
        code = cw.get("weathercode")

        # Mapear código WMO para descrição PT-BR
        weather_codes = {
            0: "Céu limpo",
            1: "Principalmente limpo",
            2: "Parcialmente nublado",
            3: "Nublado",
            45: "Nevoeiro",
            48: "Nevoeiro com deposição de geada",
            51: "Chuvisco leve",
            53: "Chuvisco moderado",
            55: "Chuvisco intenso",
            61: "Chuva leve",
            63: "Chuva moderada",
            65: "Chuva forte",
            71: "Neve leve",
            73: "Neve moderada",
            75: "Neve forte",
            80: "Pancadas de chuva leves",
            81: "Pancadas de chuva moderadas",
            82: "Pancadas de chuva fortes",
            95: "Tempestade",
            96: "Tempestade com granizo leve",
            99: "Tempestade com granizo forte",
        }

        desc = weather_codes.get(code, f"Código {code}")
        unit_sym = "°C" if unit == "celsius" else "°F"

        return f"Clima em {city}: {desc}, {temp}{unit_sym}, vento {wind} km/h"

    except Exception as exc:
        return f"Erro ao obter clima: {type(exc).__name__}: {exc}"


def get_weather_schema() -> dict:
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="get_weather",
        description="Obtém clima atual para uma localização (usa IP se não informado).",
        parameters={
            "latitude": {"type": "number", "description": "Latitude (opcional)"},
            "longitude": {"type": "number", "description": "Longitude (opcional)"},
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Unidade de temperatura",
                "default": "celsius",
            },
        },
        required=[],
    )
