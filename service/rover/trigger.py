import re
from typing import Any, Awaitable, Callable, Literal

from rover.models import Event

TriggerType = Literal[
    "prefix",
    "suffix",
    "keyword",
    "fullmatch",
    "command",
    "file",
    "regex",
    "message",
    "meta",
]


class Trigger:
    def __init__(
        self,
        type: TriggerType,
        keyword: str,
        func: Callable,
        prefix: str = "",
        block: bool = False,
        to_me: bool = False,
    ):
        self.type = type
        self.prefix = prefix
        self.keyword = keyword
        self.func: Callable[[Any, Event], Awaitable[Any]] = func
        self.block = block
        self.to_me = to_me

    def check_command(self, ev: Event) -> bool:
        msg = ev.raw_text
        if self.to_me and not ev.is_tome:
            return False
        if self.type == "file":
            return self._check_file(self.keyword, ev)
        if self.type == "meta":
            return self._check_meta(self.keyword, ev)
        return getattr(self, f"_check_{self.type}")(self.keyword, msg)

    def _check_prefix(self, prefix: str, msg: str) -> bool:
        return msg.startswith(self.prefix + prefix) and not self._check_fullmatch(prefix, msg)

    def _check_command(self, command: str, msg: str) -> bool:
        return msg.startswith(self.prefix + command)

    def _check_suffix(self, suffix: str, msg: str) -> bool:
        return (
            msg.startswith(self.prefix)
            and msg.endswith(suffix)
            and not self._check_fullmatch(suffix, msg)
        )

    def _check_keyword(self, keyword: str, msg: str) -> bool:
        return keyword in msg and msg.startswith(self.prefix)

    def _check_fullmatch(self, keyword: str, msg: str) -> bool:
        return msg == f"{self.prefix}{keyword}" and msg.startswith(self.prefix)

    def _check_file(self, file_type: str, ev: Event) -> bool:
        if ev.file and ev.file_name:
            return ev.file_name.split(".")[-1] == file_type
        return False

    def _check_meta(self, event_name: str, ev: Event) -> bool:
        return ev.meta_event_type == event_name

    def _check_regex(self, pattern: str, msg: str) -> bool:
        if msg.startswith(self.prefix):
            _msg = msg.replace(self.prefix, "", 1)
            return bool(re.findall(pattern, _msg))
        return False

    def _check_message(self, keyword: str, msg: str) -> bool:
        return True

    async def get_command(self, msg: Event) -> Event:
        if self.type != "regex":
            msg.command = self.keyword
            msg.text = msg.raw_text.replace(self.keyword, "", 1)
            if self.prefix:
                msg.text = msg.text.replace(self.prefix, "", 1)
        else:
            if self.prefix:
                msg.text = msg.text.replace(self.prefix, "", 1)
            command_group = re.search(self.keyword, msg.text)
            if command_group:
                msg.regex_dict = command_group.groupdict()
                msg.regex_group = command_group.groups()
                msg.command = "|".join([i if i is not None else "" for i in list(msg.regex_group)])
            text_list = re.split(self.keyword, msg.raw_text)
            msg.text = "|".join([i if i is not None else "" for i in text_list])
        return msg
