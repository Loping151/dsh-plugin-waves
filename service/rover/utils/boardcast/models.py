"""广播消息结构。"""

from typing import Dict, List, TypedDict

from rover.models import Message


class BoardCastMsg(TypedDict):
    bot_id: str
    messages: List[Message]


class BoardCastMsgDict(TypedDict):
    private_msg_dict: Dict[str, List[BoardCastMsg]]
    group_msg_dict: Dict[str, BoardCastMsg]
