"""消息段构造与归一化。语义对齐上游插件的既有预期, 尤其 List[str] → node。"""

from base64 import b64encode
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Union

import msgspec
from PIL import Image

from rover.media import HtmlBytes
from rover.message_models import Button
from rover.models import Message


def process_buttons(
    buttons: Union[List[Button], List[List[Button]]],
) -> List[List[Button]]:
    if not buttons:
        return []
    if isinstance(buttons[0], list):
        return buttons  # type: ignore[return-value]
    rows: List[List[Button]] = []
    row: List[Button] = []
    for btn in buttons:  # type: ignore[assignment]
        row.append(btn)  # type: ignore[arg-type]
        if len(row) >= 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


class MessageSegment:
    def __add__(self, other):
        return [self, other]

    @staticmethod
    def image(img: Union[str, Image.Image, bytes, Path]) -> Message:
        if isinstance(img, HtmlBytes):
            return Message(type="html", data=img.html)
        if isinstance(img, Image.Image):
            img = img.convert("RGB")
            result_buffer = BytesIO()
            img.save(result_buffer, format="PNG", subsampling=0)
            img = result_buffer.getvalue()
        elif isinstance(img, bytes):
            pass
        elif isinstance(img, Path):
            img = img.read_bytes()
        elif isinstance(img, (bytearray, memoryview)):
            img = bytes(img)
        else:
            if img.startswith("http"):
                return Message(type="image", data=f"link://{img}")
            if img.startswith("base64://"):
                return Message(type="image", data=img)
            with open(img, "rb") as fp:
                img = fp.read()

        return Message(type="image", data=f"base64://{b64encode(img).decode()}")

    @staticmethod
    def text(content: str) -> Message:
        return Message(type="text", data=content)

    @staticmethod
    def buttons(
        buttons: Optional[Union[List[Button], List[List[Button]]]] = None,
    ) -> Message:
        if buttons:
            buttons = process_buttons(buttons)
        return Message(type="buttons", data=msgspec.to_builtins(buttons))

    @staticmethod
    def at(user: str) -> Message:
        return Message(type="at", data=user)

    @staticmethod
    def node(
        content_list: Union[List[Message], List[str], List[bytes]],
    ) -> Message:
        msg_list: List[Message] = []
        for msg in content_list:
            if isinstance(msg, Message):
                msg_list.append(msg)
            elif isinstance(msg, (bytes, bytearray, memoryview)):
                msg_list.append(MessageSegment.image(bytes(msg)))
            else:
                if msg.startswith("base64://"):
                    msg_list.append(Message(type="image", data=msg))
                elif msg.startswith("http"):
                    msg_list.append(Message(type="image", data=f"link://{msg}"))
                else:
                    msg_list.append(MessageSegment.text(msg))
        return Message(type="node", data=msg_list)

    @staticmethod
    def file(content: Union[Path, str, bytes], file_name: str) -> Message:
        if isinstance(content, Path):
            file = content.read_bytes()
        elif isinstance(content, bytes):
            file = content
        elif isinstance(content, (bytearray, memoryview)):
            file = bytes(content)
        else:
            if content.startswith("http"):
                return Message(type="file", data=f"{file_name}|link://{content}")
            with open(content, "rb") as fp:
                file = fp.read()
        return Message(type="file", data=f"{file_name}|{b64encode(file).decode()}")


async def _convert_one(message: Union[Message, str, bytes]) -> List[Message]:
    if isinstance(message, Message):
        if message.type == "node" and isinstance(message.data, list):
            return [MessageSegment.node(message.data)]
        return [message]
    if isinstance(message, HtmlBytes):
        return [Message(type="html", data=message.html)]
    if isinstance(message, str):
        if message.startswith("base64://"):
            return [Message(type="image", data=message)]
        return [Message(type="text", data=message)]
    if isinstance(message, (bytes, bytearray, memoryview)):
        return [MessageSegment.image(bytes(message))]
    return [Message(type="text", data=str(message))]


async def convert_message(
    message: Union[Message, List[Message], List[str], str, bytes],
    bot_id: str = "",
    bot_self_id: str = "",
) -> List[Message]:
    if isinstance(message, list):
        if message and all(isinstance(x, str) for x in message):
            return [MessageSegment.node(message)]
        _message: List[Message] = []
        for i in message:
            _message.extend(await _convert_one(i))
        return _message
    return await _convert_one(message)
