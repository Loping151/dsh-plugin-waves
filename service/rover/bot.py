"""会话对象。插件调用 bot.send 产出的消息段被收集起来, 由上层一次性返回前端。"""

from typing import Any, Dict, List, Optional, Union

import msgspec

from rover.logger import logger
from rover.message_models import Button
from rover.models import Event, Message
from rover.segment import MessageSegment, convert_message

msgjson = msgspec.json


class _AsyncLogger:
    """插件里以 `await bot.logger.info(...)` 形式使用。"""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    async def _log(self, level: str, message: Any, *args: Any) -> None:
        getattr(logger, level)(f"{self.prefix}{message}", *args)

    async def info(self, message: Any, *args: Any) -> None:
        await self._log("info", message, *args)

    async def debug(self, message: Any, *args: Any) -> None:
        await self._log("debug", message, *args)

    async def trace(self, message: Any, *args: Any) -> None:
        await self._log("trace", message, *args)

    async def success(self, message: Any, *args: Any) -> None:
        await self._log("success", message, *args)

    async def warning(self, message: Any, *args: Any) -> None:
        await self._log("warning", message, *args)

    async def error(self, message: Any, *args: Any) -> None:
        await self._log("error", message, *args)

    async def exception(self, message: Any, *args: Any) -> None:
        logger.exception(message)


def _log_dropped_push(segments, target_type, target_id) -> None:
    """主动推送在本地没有去处: 只有一个使用者, 也没有群会话。记一行日志就够了。"""
    from rover.logger import logger

    text = " ".join(str(s.data) for s in segments if getattr(s, "type", "") == "text")
    logger.info(f"[推送] 丢弃一条 {target_type}/{target_id or '-'} 的主动推送: {text[:80]}")


class Bot:
    def __init__(self, ev: Event, sink: Optional[List[Message]] = None):
        self.ev = ev
        self.bot_id = ev.bot_id
        self.bot_self_id = ev.bot_self_id
        self.logger = _AsyncLogger()
        self.sink: List[Message] = sink if sink is not None else []

    async def send(
        self,
        message: Union[Message, List[Message], List[str], str, bytes, None],
        at_sender: bool = False,
        extra_metadata: Optional[Dict] = None,
        wait_recall: bool = False,
    ) -> None:
        if message is None:
            return None
        segments = await convert_message(message, self.bot_id, self.bot_self_id)
        self.sink.extend(segments)
        return None

    async def send_option(
        self,
        reply: Union[Message, List[Message], List[str], str, bytes, None],
        option_list: Optional[Union[List[Button], List[List[Button]]]] = None,
        unsuported_platform: bool = False,
        is_mutiply: bool = False,
        timeout: int = 60,
    ) -> None:
        await self.send(reply)
        if option_list:
            self.sink.append(MessageSegment.buttons(option_list))
        return None

    async def target_send(
        self,
        message: Union[Message, List[Message], List[str], str, bytes],
        target_type: str,
        target_id: Optional[str],
        bot_id: str = "",
        bot_self_id: str = "",
        msg_id: str = "",
        at_sender: bool = False,
        sender_id: str = "",
        group_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        segments = await convert_message(message, bot_id or self.bot_id, bot_self_id)
        _log_dropped_push(segments, target_type, target_id)
        return None


class PushBot:
    """给定时任务/订阅推送用的发送端, 语义与 Bot.target_send 一致。"""

    def __init__(self, bot_id: str = "dsh", bot_self_id: str = "dsh"):
        self.bot_id = bot_id
        self.bot_self_id = bot_self_id
        self.logger = _AsyncLogger()

    async def target_send(
        self,
        message: Union[Message, List[Message], List[str], str, bytes],
        target_type: str,
        target_id: Optional[str],
        bot_id: str = "",
        bot_self_id: str = "",
        msg_id: str = "",
        at_sender: bool = False,
        sender_id: str = "",
        group_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        segments = await convert_message(message, bot_id or self.bot_id, bot_self_id)
        _log_dropped_push(segments, target_type, target_id)
        return None

    async def send(self, message: Any, *args: Any, **kwargs: Any) -> None:
        await self.target_send(message, "group", "dsh")
        return None
