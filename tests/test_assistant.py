"""Assistant tool-loop tests with a fake chat client."""

from __future__ import annotations

from typing import Any

from naji.config import Config
from naji.core.assistant import Assistant, build_tool_registry
from naji.core.tools import ToolRegistry, create_tool_schema


class FakeClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[dict[str, Any]], Any]] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((messages, tools))
        return self.responses.pop(0)


def test_build_tool_registry_names() -> None:
    registry = build_tool_registry(Config())
    assert registry.list_tools() == [
        "media_control",
        "volume_control",
        "notify",
        "set_timer",
        "list_timers",
        "cancel_timer",
        "get_weather",
        "get_datetime",
        "web_search",
        "take_screenshot",
        "app_open",
        "app_close",
        "lock_screen",
        "sleep_pc",
        "shutdown_pc",
        "restart_pc",
        "window_focus",
        "window_minimize",
        "window_close",
        "open_path",
        "create_folder",
        "delete_path",
    ]
    names = [schema["function"]["name"] for schema in registry.get_schemas()]
    assert names == [
        "media_control",
        "volume_control",
        "notify",
        "set_timer",
        "list_timers",
        "cancel_timer",
        "get_weather",
        "get_datetime",
        "web_search",
        "take_screenshot",
        "app_open",
        "app_close",
        "lock_screen",
        "sleep_pc",
        "shutdown_pc",
        "restart_pc",
        "window_focus",
        "window_minimize",
        "window_close",
        "open_path",
        "create_folder",
        "delete_path",
    ]
    assert registry.confirmation_key("app_close") == "bar.confirming.close_app"
    assert registry.confirmation_key("app_open") is None
    assert registry.confirmation_key("shutdown_pc") == "bar.confirming.shutdown"
    assert registry.confirmation_key("restart_pc") == "bar.confirming.restart"
    assert registry.confirmation_key("lock_screen") == "bar.confirming.lock"
    assert registry.confirmation_key("sleep_pc") == "bar.confirming.sleep"
    assert registry.confirmation_key("window_close") == "bar.confirming.close_window"
    assert registry.confirmation_key("window_focus") is None
    assert registry.confirmation_key("window_minimize") is None
    assert registry.confirmation_key("delete_path") == "bar.confirming.delete_path"
    assert registry.confirmation_key("open_path") is None
    assert registry.confirmation_key("create_folder") is None


async def test_simple_reply_and_history() -> None:
    client = FakeClient([{"tool_calls": [], "final_response": " Olá "}])
    assistant = Assistant(Config(), client_factory=lambda: client)

    assert await assistant.reply("Oi") == "Olá"
    assert [item["role"] for item in assistant.history] == ["user", "assistant"]
    assert client.calls[0][1] is not None

    assistant.reset()
    assert assistant.history == []


async def test_tool_loop_executes_and_returns_final() -> None:
    registry = ToolRegistry()
    seen: list[str] = []

    def echo(value: str) -> str:
        seen.append(value)
        return value.upper()

    registry.register(
        "echo",
        echo,
        create_tool_schema(
            name="echo",
            description="echo",
            parameters={"value": {"type": "string"}},
            required=["value"],
        ),
    )
    tool_call = {
        "id": "call_1",
        "function": {"name": "echo", "arguments": '{"value": "hi"}'},
    }
    client = FakeClient(
        [
            {"tool_calls": [tool_call], "final_response": ""},
            {"tool_calls": [], "final_response": "Pronto"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)
    tool_names: list[str] = []

    reply = await assistant.reply("teste", on_tool=tool_names.append)

    assert reply == "Pronto"
    assert seen == ["hi"]
    assert tool_names == ["echo"]
    assert len(client.calls) == 2
    assert client.calls[1][0][-1]["role"] == "tool"


async def test_tool_loop_limit_forces_text_answer() -> None:
    config = Config()
    config.tools.tool_loop_limit = 1
    registry = ToolRegistry()
    registry.register(
        "echo",
        lambda value: value,
        create_tool_schema(
            name="echo",
            description="echo",
            parameters={"value": {"type": "string"}},
            required=["value"],
        ),
    )
    tool_call = {
        "id": "call_1",
        "function": {"name": "echo", "arguments": '{"value": "hi"}'},
    }
    client = FakeClient(
        [
            {"tool_calls": [tool_call], "final_response": ""},
            {"tool_calls": [], "final_response": "Fim"},
        ]
    )
    assistant = Assistant(config, registry=registry, client_factory=lambda: client)

    assert await assistant.reply("teste") == "Fim"
    assert client.calls[-1][1] is None


async def test_tool_call_emitted_as_text_is_executed() -> None:
    registry = ToolRegistry()
    seen: list[str] = []
    registry.register(
        "echo",
        lambda value: seen.append(value) or value.upper(),
        create_tool_schema(
            name="echo",
            description="echo",
            parameters={"value": {"type": "string"}},
            required=["value"],
        ),
    )
    raw_call = '{"name": "echo", "arguments": {"value": "hi"}}'
    client = FakeClient(
        [
            {"tool_calls": [], "final_response": raw_call},
            {"tool_calls": [], "final_response": "Pronto"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)

    assert await assistant.reply("teste") == "Pronto"
    assert seen == ["hi"]
    assert len(client.calls) == 2
    follow_up = client.calls[1][0]
    assert follow_up[-1]["role"] == "tool"
    assert follow_up[-2]["role"] == "assistant"
    assert follow_up[-2]["tool_calls"][0]["function"]["name"] == "echo"


async def test_nested_tool_call_emitted_as_text_is_executed() -> None:
    registry = ToolRegistry()
    seen: list[str] = []
    registry.register(
        "echo",
        lambda value: seen.append(value) or value.upper(),
        create_tool_schema(
            name="echo",
            description="echo",
            parameters={"value": {"type": "string"}},
            required=["value"],
        ),
    )
    raw_call = 'Claro! {"function": {"name": "echo", "arguments": {"value": "oi"}}}'
    client = FakeClient(
        [
            {"tool_calls": [], "final_response": raw_call},
            {"tool_calls": [], "final_response": "Feito"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)

    assert await assistant.reply("teste") == "Feito"
    assert seen == ["oi"]


async def test_tool_call_array_emitted_as_text_is_executed() -> None:
    registry = ToolRegistry()
    seen: list[str] = []
    registry.register(
        "echo",
        lambda value: seen.append(value) or value.upper(),
        create_tool_schema(
            name="echo",
            description="echo",
            parameters={"value": {"type": "string"}},
            required=["value"],
        ),
    )
    raw_calls = (
        '[{"name": "echo", "arguments": {"value": "a"}},'
        ' {"name": "echo", "arguments": {"value": "b"}}]'
    )
    client = FakeClient(
        [
            {"tool_calls": [], "final_response": raw_calls},
            {"tool_calls": [], "final_response": "Pronto"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)

    assert await assistant.reply("teste") == "Pronto"
    assert seen == ["a", "b"]
    follow_up = client.calls[1][0]
    assert [item["role"] for item in follow_up[-2:]] == ["tool", "tool"]


async def test_fenced_tool_call_emitted_as_text_is_executed() -> None:
    registry = ToolRegistry()
    seen: list[str] = []
    registry.register(
        "echo",
        lambda value: seen.append(value) or value.upper(),
        create_tool_schema(
            name="echo",
            description="echo",
            parameters={"value": {"type": "string"}},
            required=["value"],
        ),
    )
    raw_call = '```json\n{"name": "echo", "arguments": {"value": "hi"}}\n```'
    client = FakeClient(
        [
            {"tool_calls": [], "final_response": raw_call},
            {"tool_calls": [], "final_response": "Feito"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)

    assert await assistant.reply("teste") == "Feito"
    assert seen == ["hi"]


async def test_args_key_tool_call_emitted_as_text_is_executed() -> None:
    registry = ToolRegistry()
    seen: list[str] = []
    registry.register(
        "echo",
        lambda value: seen.append(value) or value.upper(),
        create_tool_schema(
            name="echo",
            description="echo",
            parameters={"value": {"type": "string"}},
            required=["value"],
        ),
    )
    raw_call = '{"name": "echo", "args": {"value": "x"}}'
    client = FakeClient(
        [
            {"tool_calls": [], "final_response": raw_call},
            {"tool_calls": [], "final_response": "Ok"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)

    assert await assistant.reply("teste") == "Ok"
    assert seen == ["x"]


async def test_final_reply_markdown_is_cleaned() -> None:
    client = FakeClient(
        [
            {
                "tool_calls": [],
                "final_response": "## Clima\n\n**Hoje**: 30°C ☀️\n\n- Sol a tarde",
            }
        ]
    )
    assistant = Assistant(Config(), client_factory=lambda: client)

    reply = await assistant.reply("que tempo faz")

    assert reply == "Clima Hoje: 30°C Sol a tarde"
    assert assistant.history[-1]["content"] == "Clima Hoje: 30°C Sol a tarde"


async def test_unknown_text_tool_call_is_kept_as_answer() -> None:
    client = FakeClient(
        [
            {"tool_calls": [], "final_response": '{"name": "nao_existe", "arguments": {}}'},
        ]
    )
    assistant = Assistant(Config(), client_factory=lambda: client)

    reply = await assistant.reply("teste")
    assert reply == '{"name": "nao_existe", "arguments": {}}'
    assert len(client.calls) == 1


async def test_empty_reply_does_not_enter_history() -> None:
    client = FakeClient([{"tool_calls": [], "final_response": ""}])
    assistant = Assistant(Config(), client_factory=lambda: client)

    assert await assistant.reply("Oi") == ""
    assert assistant.history == []


async def test_dangerous_tool_requires_confirmation() -> None:
    registry = ToolRegistry()
    executed: list[str] = []
    registry.register(
        "shutdown",
        lambda: executed.append("shutdown") or "done",
        create_tool_schema("shutdown", "shutdown", {}),
        dangerous=True,
        confirmation_key="bar.confirming.shutdown",
    )
    tool_call = {"id": "call_1", "function": {"name": "shutdown", "arguments": "{}"}}
    client = FakeClient(
        [
            {"tool_calls": [tool_call], "final_response": ""},
            {"tool_calls": [], "final_response": "Cancelled"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)
    confirmations: list[tuple[str, dict[str, Any], str]] = []

    async def decline(name: str, arguments: dict[str, Any], key: str) -> bool:
        confirmations.append((name, arguments, key))
        return False

    assert await assistant.reply("Turn off", on_confirmation=decline) == "Cancelled"
    assert confirmations == [("shutdown", {}, "bar.confirming.shutdown")]
    assert executed == []
    assert client.calls[1][0][-1]["content"] == "The user declined this action."


async def test_dangerous_tool_executes_after_confirmation() -> None:
    registry = ToolRegistry()
    executed: list[str] = []
    registry.register(
        "shutdown",
        lambda: executed.append("shutdown") or "done",
        create_tool_schema("shutdown", "shutdown", {}),
        dangerous=True,
        confirmation_key="bar.confirming.shutdown",
    )
    tool_call = {"id": "call_1", "function": {"name": "shutdown", "arguments": "{}"}}
    client = FakeClient(
        [
            {"tool_calls": [tool_call], "final_response": ""},
            {"tool_calls": [], "final_response": "Completed"},
        ]
    )
    assistant = Assistant(Config(), registry=registry, client_factory=lambda: client)

    async def allow(_name: str, _arguments: dict[str, Any], _key: str) -> bool:
        return True

    assert await assistant.reply("Turn off", on_confirmation=allow) == "Completed"
    assert executed == ["shutdown"]
