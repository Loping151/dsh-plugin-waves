import asyncio
from typing import Any, Dict, List, Literal, Optional, Tuple

from msgspec import Struct


class Message(Struct):
    type: Optional[str] = None
    data: Optional[Any] = None


class MessageReceive(Struct):
    bot_id: str = "Bot"
    bot_self_id: str = ""
    msg_id: str = ""
    user_type: Literal["group", "direct", "channel", "sub_channel"] = "group"
    group_id: Optional[str] = None
    user_id: str = ""
    sender: Dict[str, Any] = {}
    user_pm: int = 6
    content: List[Message] = []


class Event(MessageReceive):
    WS_BOT_ID: Optional[str] = None
    task_id: str = ""
    task_event: Optional[asyncio.Event] = None
    real_bot_id: str = ""
    raw_text: str = ""
    command: str = ""
    text: str = ""
    image: Optional[str] = None
    image_list: List[Any] = []
    image_id: Optional[str] = None
    image_id_list: List[str] = []
    audio_id: Optional[str] = None
    audio_id_list: List[str] = []
    at: Optional[str] = None
    at_list: List[Any] = []
    is_tome: bool = False
    reply: Optional[str] = None
    reply_id: Optional[str] = None
    node: Optional[List[Message]] = None
    file_name: Optional[str] = None
    file: Optional[str] = None
    file_type: Optional[Literal["url", "base64"]] = None
    regex_group: Tuple[str, ...] = ()
    regex_dict: Dict[str, str] = {}
    meta_event_type: Optional[str] = None
    meta_event_data: Dict[str, Any] = {}

    def __hash__(self) -> int:
        return hash(
            (
                self.WS_BOT_ID,
                self.bot_id,
                self.bot_self_id,
                self.user_id,
                self.group_id,
                self.user_type,
            )
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Event):
            return NotImplemented
        return (
            self.WS_BOT_ID,
            self.bot_id,
            self.bot_self_id,
            self.user_id,
            self.group_id,
            self.user_type,
        ) == (
            other.WS_BOT_ID,
            other.bot_id,
            other.bot_self_id,
            other.user_id,
            other.group_id,
            other.user_type,
        )

    @property
    def session_id(self) -> str:
        ws_bid = self.WS_BOT_ID or self.real_bot_id or self.bot_id or "0"
        bid = self.bot_id if self.bot_id else "0"
        bot_self_id = self.bot_self_id if self.bot_self_id else "0"
        if self.user_type != "direct":
            gid = self.group_id if self.group_id else "0"
            return f"{ws_bid}:{bid}:{bot_self_id}:group:{gid}"
        uid = self.user_id if self.user_id else "0"
        return f"{ws_bid}:{bid}:{bot_self_id}:private:{uid}"
