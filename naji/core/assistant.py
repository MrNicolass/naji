"""Conversation and tool-calling loop for the assistant."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from naji.config import Config
from naji.core.models import LlamaCppChatClient
from naji.core.text import clean_spoken_text
from naji.core.tools import ToolRegistry
from naji.core.tools.app_control import (
    app_close,
    app_open,
    get_app_close_schema,
    get_app_open_schema,
)
from naji.core.tools.datetime import get_datetime, get_datetime_schema
from naji.core.tools.file_control import (
    create_folder,
    delete_path,
    get_create_folder_schema,
    get_delete_path_schema,
    get_open_path_schema,
    open_path,
)
from naji.core.tools.media_control import get_media_control_schema, media_control
from naji.core.tools.notification import get_notify_schema, notify
from naji.core.tools.power import (
    get_lock_screen_schema,
    get_restart_pc_schema,
    get_shutdown_pc_schema,
    get_sleep_pc_schema,
    lock_screen,
    restart_pc,
    shutdown_pc,
    sleep_pc,
)
from naji.core.tools.screenshot import get_screenshot_schema, take_screenshot
from naji.core.tools.timer import (
    cancel_timer,
    get_cancel_timer_schema,
    get_list_timers_schema,
    get_set_timer_schema,
    list_timers,
    set_timer,
)
from naji.core.tools.volume_control import get_volume_control_schema, volume_control
from naji.core.tools.weather import get_weather, get_weather_schema
from naji.core.tools.web_search import get_web_search_schema, web_search
from naji.core.tools.window_control import (
    get_window_close_schema,
    get_window_focus_schema,
    get_window_minimize_schema,
    window_close,
    window_focus,
    window_minimize,
)

log = logging.getLogger(__name__)

ToolCallback = Callable[[str], None]
ToolConfirmationCallback = Callable[[str, dict[str, Any], str], Awaitable[bool]]


def build_tool_registry(config: Config) -> ToolRegistry:
    """Register the tools enabled in configuration."""
    registry = ToolRegistry()
    for name in config.tools.enabled:
        if name == "datetime":
            registry.register("get_datetime", get_datetime, get_datetime_schema())
        elif name == "weather":

            async def weather(
                latitude: float | None = None,
                longitude: float | None = None,
                unit: str | None = None,
            ) -> str:
                return await get_weather(
                    latitude,
                    longitude,
                    unit or config.tools.weather_unit,
                )

            registry.register("get_weather", weather, get_weather_schema())
        elif name == "media_control":
            registry.register("media_control", media_control, get_media_control_schema())
        elif name == "volume_control":
            registry.register("volume_control", volume_control, get_volume_control_schema())
        elif name == "notification":
            registry.register("notify", notify, get_notify_schema())
        elif name == "web_search":

            async def search(query: str, max_results: int | None = None) -> str:
                return await web_search(
                    query,
                    max_results or config.tools.web_search_max_results,
                )

            registry.register("web_search", search, get_web_search_schema())
        elif name == "screenshot":
            registry.register("take_screenshot", take_screenshot, get_screenshot_schema())
        elif name == "timer_control":
            registry.register("set_timer", set_timer, get_set_timer_schema())
            registry.register("list_timers", list_timers, get_list_timers_schema())
            registry.register("cancel_timer", cancel_timer, get_cancel_timer_schema())
        elif name == "app_control":
            registry.register("app_open", app_open, get_app_open_schema())
            registry.register(
                "app_close",
                app_close,
                get_app_close_schema(),
                dangerous=True,
                confirmation_key="bar.confirming.close_app",
            )
        elif name == "power_control":
            registry.register(
                "lock_screen",
                lock_screen,
                get_lock_screen_schema(),
                dangerous=True,
                confirmation_key="bar.confirming.lock",
            )
            registry.register(
                "sleep_pc",
                sleep_pc,
                get_sleep_pc_schema(),
                dangerous=True,
                confirmation_key="bar.confirming.sleep",
            )
            registry.register(
                "shutdown_pc",
                shutdown_pc,
                get_shutdown_pc_schema(),
                dangerous=True,
                confirmation_key="bar.confirming.shutdown",
            )
            registry.register(
                "restart_pc",
                restart_pc,
                get_restart_pc_schema(),
                dangerous=True,
                confirmation_key="bar.confirming.restart",
            )
        elif name == "window_control":
            registry.register("window_focus", window_focus, get_window_focus_schema())
            registry.register(
                "window_minimize", window_minimize, get_window_minimize_schema()
            )
            registry.register(
                "window_close",
                window_close,
                get_window_close_schema(),
                dangerous=True,
                confirmation_key="bar.confirming.close_window",
            )
        elif name == "file_control":
            registry.register("open_path", open_path, get_open_path_schema())
            registry.register("create_folder", create_folder, get_create_folder_schema())
            registry.register(
                "delete_path",
                delete_path,
                get_delete_path_schema(),
                dangerous=True,
                confirmation_key="bar.confirming.delete_path",
            )
        else:
            log.warning("Unknown tool in configuration: %s", name)
    return registry


class Assistant:
    """Owns conversation history and the tool-calling loop."""

    def __init__(
        self,
        config: Config,
        *,
        registry: ToolRegistry | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._config = config
        self._registry = registry or build_tool_registry(config)
        self._client_factory = client_factory or self._default_client
        self._history: list[dict[str, Any]] = []

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def reset(self) -> None:
        self._history.clear()

    def _default_client(self) -> LlamaCppChatClient:
        dual = self._config.models.mode == "dual"
        endpoint = (
            self._config.server.executor_endpoint
            if dual
            else self._config.server.voice_endpoint
        )
        model = (
            self._config.models.executor_model
            if dual
            else self._config.models.voice_model
        )
        return LlamaCppChatClient(
            endpoint,
            self._config.server.api_key,
            model,
            timeout=max(60.0, self._config.server.request_timeout_s),
        )

    async def reply(
        self,
        user_text: str,
        on_tool: ToolCallback | None = None,
        on_confirmation: ToolConfirmationCallback | None = None,
    ) -> str:
        """Return the assistant answer, executing tools as requested."""
        text = user_text.strip()
        if not text:
            return ""

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._config.models.instructions},
            *self._history,
            {"role": "user", "content": text},
        ]
        tools = self._registry.get_schemas()
        final = ""

        async with self._client_factory() as client:
            for _ in range(self._config.tools.tool_loop_limit):
                response = await client.chat(messages, tools=tools or None)
                calls = list(response.get("tool_calls") or [])
                content = (response.get("final_response") or "").strip()

                if not calls:
                    calls = self._recover_text_tool_calls(content)
                    if calls:
                        content = ""
                if not calls:
                    final = content
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": calls,
                    }
                )
                for index, call in enumerate(calls):
                    function = call.get("function") or {}
                    name = function.get("name") or ""
                    arguments = self._parse_arguments(function.get("arguments"))
                    call_id = call.get("id") or f"call_{index}"
                    confirmation_key = self._registry.confirmation_key(name)
                    if confirmation_key:
                        allowed = (
                            await on_confirmation(name, arguments, confirmation_key)
                            if on_confirmation is not None
                            else False
                        )
                        if not allowed:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "name": name,
                                    "content": "The user declined this action.",
                                }
                            )
                            continue
                    if on_tool is not None:
                        on_tool(name)
                    log.info("Executing tool: %s", name)
                    result = await self._registry.execute(name, arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": name,
                            "content": result,
                        }
                    )
                final = content
            else:
                response = await client.chat(messages, tools=None)
                final = (response.get("final_response") or "").strip()

        final = clean_spoken_text(final)
        if final:
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": final})
        return final

    def _recover_text_tool_calls(self, content: str) -> list[dict[str, Any]]:
        """Recover tool calls the model emitted as plain text.

        Some llama.cpp builds serialize the function call into the message
        content instead of the ``tool_calls`` field — as a single object, an
        array of objects, inside a fenced code block, or with argument keys
        spelled ``parameters``/``args``. Without this guard the raw JSON (with
        function names and arguments) would be shown as the answer.
        """
        text = content.strip()
        opens = [index for index in (text.find("{"), text.find("[")) if index != -1]
        closes = [index for index in (text.rfind("}"), text.rfind("]")) if index != -1]
        if not opens or not closes:
            return []
        start = min(opens)
        end = max(closes)
        if end <= start:
            return []
        try:
            value = json.loads(text[start : end + 1])
        except (TypeError, json.JSONDecodeError):
            return []
        candidates = value if isinstance(value, list) else [value]
        calls: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            call = self._coerce_text_tool_call(candidate, index)
            if call is not None:
                calls.append(call)
        return calls

    def _coerce_text_tool_call(self, value: Any, index: int) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        function = value.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            name = function["name"]
            arguments = function.get(
                "arguments", function.get("parameters", function.get("args"))
            )
        elif isinstance(value.get("name"), str) and any(
            key in value for key in ("arguments", "parameters", "args")
        ):
            name = value["name"]
            arguments = value.get("arguments", value.get("parameters", value.get("args")))
        else:
            return None
        if self._registry.get(name) is None:
            return None
        return {"id": f"call_text_{index}", "function": {"name": name, "arguments": arguments}}

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}
