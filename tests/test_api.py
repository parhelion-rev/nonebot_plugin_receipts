"""公开入口 ``nonebot_plugin_receipts.api`` 的契约。

别的插件（例如 nonebot-plugin-milock）只依赖这个模块，所以这里把它的行为
钉住：纯文本能不能渲染、能不能投递、config/context 省略时怎么解析。
"""

from __future__ import annotations

import unittest
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

from nonebot_plugin_receipts.api import (
    build_text_message,
    print_message,
    print_text,
    render_message,
    render_text,
)
from nonebot_plugin_receipts.config import Config
from nonebot_plugin_receipts.template import ReceiptTemplateContext

if TYPE_CHECKING:
    from typing import Any


def make_config() -> Config:
    return Config(receipt_render_mode="raster")


class BuildTextMessageTestCase(unittest.TestCase):
    def test_wraps_plain_text(self) -> None:
        message = build_text_message("!! 门铃 !!\n有人按门铃")
        assert message.extract_plain_text().startswith("!! 门铃 !!")

    def test_empty_text_is_still_a_message(self) -> None:
        assert build_text_message("").extract_plain_text() == ""


class RenderTextTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_returns_escpos_bytes(self) -> None:
        data = await render_text(
            "!! 门铃 !!\n有人按门铃",
            config=make_config(),
            context=ReceiptTemplateContext(sender_name="门锁", sender_id="1"),
        )
        assert isinstance(data, bytes)
        assert data, "应该渲染出内容"
        assert data[:2] == b"\x1b@", "ESC/POS 初始化指令应在开头"

    async def test_explicit_config_skips_runtime_lookup(self) -> None:
        """给了 config 就不该再去读 NoneBot 运行时。"""
        with patch(
            "nonebot_plugin_receipts.api.get_runtime_config",
            side_effect=AssertionError("不应调用 get_runtime_config"),
        ):
            await render_text("hi", config=make_config())

    async def test_omitted_config_uses_runtime_lookup(self) -> None:
        with patch(
            "nonebot_plugin_receipts.api.get_runtime_config",
            return_value=make_config(),
        ) as lookup:
            await render_text("hi")
        lookup.assert_called_once()

    async def test_render_message_matches_render_text(self) -> None:
        config = make_config()
        context = ReceiptTemplateContext(sender_name="门锁", sender_id="1")
        from_text = await render_text("相同的文本", config=config, context=context)
        from_message = await render_message(
            build_text_message("相同的文本"), config=config, context=context
        )
        assert from_text == from_message


class PrintTextTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_pushes_rendered_bytes_to_spooler(self) -> None:
        pushed: list[bytes] = []

        class FakeSpooler:
            def __init__(self, _config: Config) -> None:
                pass

            async def push_raw(self, payload: bytes) -> dict[str, Any]:
                pushed.append(payload)
                return {"queue_size": 1}

        with patch("nonebot_plugin_receipts.api.SpoolerClient", FakeSpooler):
            result = await print_text("!! 门铃 !!", config=make_config())

        assert result == {"queue_size": 1}
        assert len(pushed) == 1
        assert pushed[0][:2] == b"\x1b@"

    async def test_spooler_receives_the_configured_config(self) -> None:
        seen: list[Config] = []
        config = make_config()

        class FakeSpooler:
            def __init__(self, passed_config: Config) -> None:
                seen.append(passed_config)

            async def push_raw(self, _payload: bytes) -> dict[str, Any]:
                return {}

        with patch("nonebot_plugin_receipts.api.SpoolerClient", FakeSpooler):
            await print_text("hi", config=config)

        assert seen == [config]

    async def test_print_message_delegates(self) -> None:
        class FakeSpooler:
            def __init__(self, _config: Config) -> None:
                pass

            async def push_raw(self, _payload: bytes) -> dict[str, Any]:
                return {"ok": True}

        with patch("nonebot_plugin_receipts.api.SpoolerClient", FakeSpooler):
            result = await print_message(build_text_message("hi"), config=make_config())
        assert result == {"ok": True}


class ApiSurfaceTestCase(unittest.TestCase):
    def test_can_import_types_from_api_alone(self) -> None:
        """调用方不该为了拿 context 类型再去 import 内部模块。"""
        from nonebot_plugin_receipts.api import Config as ApiConfig
        from nonebot_plugin_receipts.api import (
            ReceiptTemplateContext as ApiContext,
        )

        assert ApiConfig().receipt_render_mode in ("raster", "hybrid")
        assert ApiContext(sender_name="x").sender_name == "x"

    def test_all_is_declared(self) -> None:
        from nonebot_plugin_receipts import api

        assert api.__all__ == [
            "Config",
            "ReceiptTemplateContext",
            "build_text_message",
            "get_runtime_config",
            "print_message",
            "print_text",
            "render_message",
            "render_text",
        ]

    def test_public_names_exist(self) -> None:
        from nonebot_plugin_receipts import api

        for name in api.__all__:
            assert hasattr(api, name), name


class CommandHandlerUsesPublicApiTestCase(unittest.TestCase):
    def test_submit_print_job_goes_through_api(self) -> None:
        """自带命令与外部调用方必须共用同一条实现路径。"""
        from nonebot_plugin_receipts import command_handlers

        assert hasattr(command_handlers, "print_message")
        with (
            patch(
                "nonebot_plugin_receipts.command_handlers.print_message",
                new=AsyncMock(return_value={"queue_size": 3}),
            ) as fake,
            patch(
                "nonebot_plugin_receipts.command_handlers.get_runtime_config",
                return_value=make_config(),
            ),
        ):
            import asyncio

            event = cast("Any", type("E", (), {"user_id": "1"})())
            message = cast("Any", build_text_message("hi"))
            text = asyncio.run(command_handlers.submit_print_job(event, message))
        fake.assert_awaited_once()
        assert "3" in text
