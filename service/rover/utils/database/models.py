from typing import List, Union, Optional

from sqlmodel import Field, Index

from rover.logger import logger
from rover.models import Message
from rover.message_models import ButtonType

from .base_models import BaseModel


class Subscribe(BaseModel, table=True):
    __table_args__ = (
        Index(
            "ix_subscribe_task_name_uid",
            "task_name",
            "uid",
        ),
        {"extend_existing": True},
    )

    WS_BOT_ID: Optional[str] = Field(title="WS机器人ID", default=None)
    group_id: Optional[str] = Field(title="群ID", default=None, index=True)
    task_name: str = Field(title="任务名称", default=None, index=True)
    bot_self_id: str = Field(title="机器人自身ID", default=None)
    user_type: str = Field(title="发送类型", default=None)
    extra_message: Optional[str] = Field(title="额外消息", default=None)
    uid: Optional[str] = Field(title="账户ID", default=None, index=True)
    extra_data: Optional[str] = Field(title="额外消息2", default=None)
    msg_id: Optional[str] = Field(title="消息ID", default=None)

    async def send(
        self,
        reply: Optional[
            Union[
                Message,
                List[Message],
                List[str],
                str,
                bytes,
            ]
        ] = None,
        option_list: Optional[ButtonType] = None,
        unsuported_platform: bool = False,
        sep: str = "\n",
        command_tips: str = "请输入以下命令之一:",
        command_start_text: str = "",
        force_direct: bool = False,
    ):
        from rover.gss import gss

        if reply is None:
            return -1

        user_type = "direct" if force_direct else self.user_type
        target_id = self.group_id if user_type == "group" else self.user_id

        bot = None
        if self.WS_BOT_ID:
            bot = gss.active_bot.get(self.WS_BOT_ID)
        if bot is None:
            for _bot in gss.active_bot.values():
                if getattr(_bot, "bot_id", None) == self.bot_id:
                    bot = _bot
                    break
        if bot is None:
            bot = next(iter(gss.active_bot.values()), None)

        if bot is None:
            logger.error(f"[订阅] 无可用连接, 该消息无法发送! task_name={self.task_name}")
            return -1

        await bot.target_send(
            reply,
            user_type,
            target_id,
            self.bot_id,
            self.bot_self_id,
            "",
        )
