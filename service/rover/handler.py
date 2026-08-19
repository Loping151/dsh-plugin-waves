"""命令分发。一条文本经触发器匹配后依次执行命中的 handler, 回复段按序收集。"""

import asyncio
import time
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional

from rover.bot import Bot
from rover.config import core_config
from rover.logger import logger
from rover.models import Event, Message, MessageReceive
from rover.sv import SL, SV, all_prefixes
from rover.trigger import Trigger

DEFAULT_BOT_ID = "dsh"


def get_user_pm(user_id: str, fallback: int = 6) -> int:
    masters = core_config.get_config("masters") or []
    if user_id in masters:
        return 0
    return fallback if fallback >= 1 else 2


def _sv_authorized(_sv: SV, event: Event, user_pm: int) -> bool:
    _plugins = _sv.plugins
    if not _plugins.enabled:
        return False
    if user_pm > _plugins.pm:
        return False
    if event.group_id in _plugins.black_list or event.user_id in _plugins.black_list:
        return False
    # 只有本机一个使用者, 群聊/私聊之分没有意义: 限定场景的命令(如 获取ck)照样能直接下
    if _plugins.white_list and _plugins.white_list != [""]:
        if event.user_id not in _plugins.white_list and event.group_id not in _plugins.white_list:
            return False
    if not _sv.enabled:
        return False
    if user_pm > _sv.pm:
        return False
    if event.group_id in _sv.black_list or event.user_id in _sv.black_list:
        return False
    if _sv.white_list and _sv.white_list != [""]:
        if event.user_id not in _sv.white_list and event.group_id not in _sv.white_list:
            return False
    return True


def msg_process(msg: MessageReceive) -> Event:
    bot_id = msg.bot_id.split(":")[0] if ":" in msg.bot_id else msg.bot_id
    event = Event(
        bot_id,
        msg.bot_self_id,
        msg.msg_id,
        msg.user_type,
        msg.group_id,
        msg.user_id,
        msg.sender,
        msg.user_pm,
        real_bot_id=msg.bot_id,
    )
    event.WS_BOT_ID = msg.bot_id
    if msg.user_type == "direct":
        event.is_tome = True

    content: List[Message] = []
    for _msg in msg.content:
        if _msg.type == "text":
            if not _msg.data:
                continue
            text_part = str(_msg.data).strip()
            event.raw_text += text_part
            event.text += text_part
        elif _msg.type == "at":
            if str(_msg.data) == str(event.bot_self_id):
                event.is_tome = True
                continue
            event.at = str(_msg.data)
            event.at_list.append(str(_msg.data))
        elif _msg.type == "image":
            event.image = _msg.data
            if _msg.data:
                event.image_list.append(_msg.data)
        elif _msg.type == "reply":
            event.reply = _msg.data
        elif _msg.type == "reply_id" and _msg.data is not None:
            event.reply_id = str(_msg.data)
        elif _msg.type == "file" and _msg.data:
            data = str(_msg.data).split("|")
            event.file_name = data[0]
            event.file = data[1] if len(data) > 1 else ""
            event.file_type = "url" if str(event.file).startswith("http") else "base64"
        content.append(_msg)
    event.content = content
    return event


def normalize_command(text: str) -> str:
    """无前缀时补一个默认前缀, 让前端/模型不必记住 ww。"""
    text = text.strip()
    if not text:
        return text
    for prefix in all_prefixes():
        if text.startswith(prefix):
            return text
    default = all_prefixes()
    return f"{default[0]}{text}" if default else text


def collect_triggers(event: Event) -> List[Trigger]:
    valid: Dict[Trigger, int] = {}
    for sv in SL.lst.values():
        if not _sv_authorized(sv, event, event.user_pm):
            continue
        for triggers in sv.TL.values():
            for trigger in triggers.values():
                if trigger.check_command(event):
                    valid[trigger] = sv.priority
    return [t for t, _ in sorted(valid.items(), key=lambda x: (not x[0].prefix, x[1]))]


async def dispatch(msg: MessageReceive, timeout: Optional[float] = None) -> Dict[str, Any]:
    started = time.perf_counter()
    if timeout is None:
        timeout = float(core_config.get_config("command_timeout") or 300)
    event = msg_process(msg)
    event.user_pm = get_user_pm(event.user_id, msg.user_pm)
    event.task_id = uuid.uuid4().hex

    triggers = collect_triggers(event)
    sink: List[Message] = []
    matched: List[str] = []

    if not triggers:
        return {
            "matched": [],
            "segments": sink,
            "elapsed": time.perf_counter() - started,
            "unmatched": True,
        }

    for trigger in triggers:
        _event = deepcopy(event)
        await trigger.get_command(_event)
        bot = Bot(_event, sink)
        matched.append(f"{trigger.type}:{trigger.prefix}{trigger.keyword}")
        try:
            await asyncio.wait_for(trigger.func(bot, _event), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"命令执行超时: {trigger.keyword}")
            sink.append(Message("text", f"[执行超时] {trigger.keyword}"))
        except Exception as e:
            logger.exception(e)
            sink.append(Message("text", f"[执行出错] {e}"))
        if trigger.block:
            break

    return {
        "matched": matched,
        "segments": sink,
        "elapsed": time.perf_counter() - started,
        "unmatched": False,
    }


def build_message(
    text: str,
    user_id: str,
    group_id: Optional[str] = "dsh",
    user_type: str = "group",
    images: Optional[List[str]] = None,
    file_name: Optional[str] = None,
    file_data: Optional[str] = None,
) -> MessageReceive:
    content: List[Message] = [Message("text", text)]
    for img in images or []:
        content.append(Message("image", img))
    if file_name and file_data:
        content.append(Message("file", f"{file_name}|{file_data}"))
    return MessageReceive(
        bot_id=DEFAULT_BOT_ID,
        bot_self_id=DEFAULT_BOT_ID,
        msg_id=uuid.uuid4().hex[:12],
        user_type=user_type,  # type: ignore[arg-type]
        group_id=group_id if user_type == "group" else None,
        user_id=user_id,
        sender={"nickname": "漫游者"},
        user_pm=6,
        content=content,
    )
