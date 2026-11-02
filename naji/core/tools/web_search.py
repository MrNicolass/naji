"""Web search via DuckDuckGo (no separate summarizer model)."""

from __future__ import annotations

import asyncio

from ddgs import DDGS


def _search_sync(query: str, max_results: int) -> list[dict]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return raw results for the assistant to summarize."""
    try:
        results = await asyncio.to_thread(_search_sync, query, max_results)
        if not results:
            return "Nenhum resultado encontrado."

        return "\n".join(f"- {item.get('title', '')}: {item.get('body', '')}" for item in results)
    except Exception as exc:
        return f"Erro na pesquisa: {type(exc).__name__}: {exc}"


SUMMARIZATION_PROMPT = (
    "Resuma os seguintes resultados de busca em português do Brasil, "
    "em no máximo 3 parágrafos, tom direto e natural, sem markdown:\n\n{results}"
)


def get_web_search_schema() -> dict:
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="web_search",
        description="Pesquisa na web via DuckDuckGo e retorna resultados para sumarização.",
        parameters={
            "query": {"type": "string", "description": "Termo de busca"},
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 5,
                "description": "Máximo de resultados",
            },
        },
        required=["query"],
    )
