"""Registry de ferramentas nativas."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


class ToolRegistry:
    """Registry de ferramentas executáveis nativamente pelo App."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._dangerous: dict[str, str] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        schema: dict[str, Any],
        *,
        dangerous: bool = False,
        confirmation_key: str | None = None,
    ) -> None:
        """Registra uma ferramenta com seu schema JSON."""
        if dangerous and not confirmation_key:
            raise ValueError("dangerous tools require an i18n confirmation key")
        self._tools[name] = func
        self._schemas[name] = schema
        if dangerous:
            self._dangerous[name] = confirmation_key
        else:
            self._dangerous.pop(name, None)

    def get(self, name: str) -> Callable[..., Any] | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict[str, Any]]:
        """Retorna schemas no formato OpenAI function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema.get("description", ""),
                    "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for name, schema in self._schemas.items()
        ]

    def confirmation_key(self, name: str) -> str | None:
        """Return the confirmation translation key for a destructive tool."""
        return self._dangerous.get(name)

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Executa uma ferramenta e retorna resultado como string."""
        func = self._tools.get(name)
        if not func:
            return f"Erro: ferramenta '{name}' não encontrada"

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
            return str(result)
        except Exception as exc:
            return f"Erro ao executar '{name}': {type(exc).__name__}: {exc}"

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())


def create_tool_schema(
    name: str,
    description: str,
    parameters: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """Helper para criar schema de ferramenta."""
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": parameters,
            "required": required or [],
        },
    }
