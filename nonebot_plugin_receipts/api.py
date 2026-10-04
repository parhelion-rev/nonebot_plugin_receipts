"""公开入口：给**别的插件/代码**调用，而不是去 import 本包的内部模块。

``/ticket`` 命令与外部调用方（例如 ``nonebot-plugin-milock`` 打门锁事件小票）
都走这里，于是"消息 → ESC/POS → receipts-spooler"只有一份实现。

之所以要有这个模块：渲染与投递的实现散在 ``renderer`` / ``spooler`` /
``template`` 里，直接 import 它们等于把本包的内部结构当成契约，本包一重构
调用方就静默坏掉。**对外承诺的只有本模块**，其余子模块属于内部实现。

用法::

    from nonebot_plugin_receipts.api import ReceiptTemplateContext, print_text

    await print_text(
        "!! 门铃 !!\n有人按门铃",
        context=ReceiptTemplateContext(sender_name="门锁", sender_id="1021313131"),
    )

``config`` / ``context`` 都可以省略：省略时 ``config`` 从 NoneBot 运行时读，
``context`` 用空上下文。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config import Config
from .renderer import render_receipt
from .spooler import SpoolerClient
from .template import ReceiptTemplateContext

# Config / ReceiptTemplateContext 是上面那些函数签名的一部分，属于公开面，
# 所以在这里再导出——调用方于是只需要 import 本模块。
_PUBLIC_TYPES = (Config, ReceiptTemplateContext)

if TYPE_CHECKING:  # pragma: no cover
    from nonebot.adapters.onebot.v11 import Message

__all__ = [
    "Config",
    "ReceiptTemplateContext",
    "build_text_message",
    "get_runtime_config",
    "print_message",
    "print_text",
    "render_message",
    "render_text",
]


def get_runtime_config() -> Config:
    """从当前 NoneBot 运行时读取本插件配置。"""
    from nonebot import get_plugin_config

    return get_plugin_config(Config)


def build_text_message(text: str) -> Message:
    """把纯文本包成 OneBot 消息——渲染层接受的是消息。"""
    from nonebot.adapters.onebot.v11 import Message

    return Message(text)


def _resolve(
    config: Config | None,
    context: ReceiptTemplateContext | None,
) -> tuple[Config, ReceiptTemplateContext]:
    return (
        config if config is not None else get_runtime_config(),
        context if context is not None else ReceiptTemplateContext(),
    )


async def render_message(
    message: Message,
    *,
    config: Config | None = None,
    context: ReceiptTemplateContext | None = None,
) -> bytes:
    """把一条消息渲染成 ESC/POS 原始字节（**不投递**）。

    需要先看效果、或想把字节交给别的队列时用这个。
    """
    resolved_config, resolved_context = _resolve(config, context)
    return await render_receipt(message, resolved_config, resolved_context)


async def print_message(
    message: Message,
    *,
    config: Config | None = None,
    context: ReceiptTemplateContext | None = None,
) -> dict[str, Any]:
    """渲染并投递给 receipts-spooler，返回 spooler 的响应。"""
    resolved_config, resolved_context = _resolve(config, context)
    payload = await render_receipt(message, resolved_config, resolved_context)
    return await SpoolerClient(resolved_config).push_raw(payload)


async def render_text(
    text: str,
    *,
    config: Config | None = None,
    context: ReceiptTemplateContext | None = None,
) -> bytes:
    """纯文本版本的 :func:`render_message`。"""
    return await render_message(
        build_text_message(text), config=config, context=context
    )


async def print_text(
    text: str,
    *,
    config: Config | None = None,
    context: ReceiptTemplateContext | None = None,
) -> dict[str, Any]:
    """纯文本版本的 :func:`print_message`——"我想打一段字"就用这个。"""
    return await print_message(build_text_message(text), config=config, context=context)
