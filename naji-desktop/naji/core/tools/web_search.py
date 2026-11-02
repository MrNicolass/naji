"""Pesquisa web via DuckDuckGo + sumarização via ExecutorModel."""

from __future__ import annotations

from duckduckgo_search import AsyncDDGS


async def web_search(query: str, max_results: int = 5) -> str:
    """
    Pesquisa web e retorna resultados brutos (sumarização feita pelo ExecutorModel).

    Args:
        query: Termo de busca
        max_results: Máximo de resultados (1-10)

    Returns:
        String com resultados concatenados para sumarização.
    """
    try:
        results = []
        async with AsyncDDGS() as ddgs:
            async for r in ddgs.atext(query, max_results=max_results):
                results.append(f"- {r.get('title', '')}: {r.get('body', '')}")

        if not results:
            return "Nenhum resultado encontrado."

        return "\n".join(results)

    except Exception as exc:
        return f"Erro na pesquisa: {type(exc).__name__}: {exc}"


# Prompt de sumarização para o ExecutorModel
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
