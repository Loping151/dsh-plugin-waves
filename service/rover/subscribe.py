from typing import Dict, Literal, Optional, Sequence, Union

from rover.models import Event
from rover.utils.database.models import Subscribe


class RoverSubscribeManager:
    async def add_subscribe(
        self,
        subscribe_type: Literal["session", "single"],
        task_name: str,
        event: Event,
        extra_message: Optional[str] = None,
        uid: Optional[str] = None,
        extra_data: Optional[str] = None,
    ):
        """📝简单介绍:

            该方法允许向数据库添加一个订阅信息的持久化保存

            注意`subscribe_type`参数必须为`session`或`single`

            `session`模式下, 订阅都将在每个有效的session(group或direct)内独立存在 (公告推送)

            `single`模式下, 同个session(group)可能同时存在多个订阅 (签到任务)

        🌱参数:

            🔹subscribe_type (`Literal['session', 'single']`):
                    'session'模式: 同个group/user下只存在一条订阅
                    'single'模式: 同个group下存在多条订阅, 同个user只存在一条订阅

            🔹task_name (`str`):
                    订阅名称

            🔹event (`Event`):
                    事件Event

            🔹extra_message (`Optional[str]`, 默认是 `None`):
                    额外想要保存的信息, 例如推送信息或者数值阈值

        🚀使用范例:

            `await gs_subscribe.add_subscribe('single', '签到', event)`
        """
        opt: Dict[str, Union[str, int, None]] = {
            "bot_id": event.bot_id,
            "task_name": task_name,
            "uid": uid,
            "WS_BOT_ID": event.WS_BOT_ID,
        }
        if subscribe_type == "session" and event.user_type == "group":
            opt["group_id"] = event.group_id
            opt["user_type"] = event.user_type
        else:
            opt["user_id"] = event.user_id

        condi = await Subscribe.data_exist(
            **opt,
        )

        if not condi:
            await Subscribe.full_insert_data(
                user_id=event.user_id,
                bot_id=event.bot_id,
                group_id=event.group_id,
                task_name=task_name,
                bot_self_id=event.bot_self_id,
                user_type=event.user_type,
                extra_message=extra_message,
                WS_BOT_ID=event.WS_BOT_ID,
                uid=uid,
                extra_data=extra_data,
                msg_id=event.msg_id,
            )
        else:
            upd = {}
            for i in [
                "user_id",
                "bot_id",
                "group_id",
                "bot_self_id",
                "user_type",
                "WS_BOT_ID",
                "msg_id",
            ]:
                if i not in opt:
                    upd[i] = event.__getattribute__(i)

            upd["extra_message"] = extra_message
            upd["extra_data"] = extra_data

            await Subscribe.update_data_by_data(
                opt,
                upd,
            )

    async def get_subscribe(
        self,
        task_name: str,
        user_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        user_type: Optional[str] = None,
        uid: Optional[str] = None,
        WS_BOT_ID: Optional[str] = None,
    ):
        params = {
            "task_name": task_name,
        }

        if user_id and bot_id and user_type:
            params["user_id"] = user_id
            params["bot_id"] = bot_id
            params["user_type"] = user_type

        if uid:
            params["uid"] = uid

        if WS_BOT_ID:
            params["WS_BOT_ID"] = WS_BOT_ID

        all_data: Optional[Sequence[Subscribe]] = await Subscribe.select_rows(distinct=False, **params)
        return all_data

    async def delete_subscribe(
        self,
        subscribe_type: Literal["session", "single"],
        task_name: str,
        event: Event,
        uid: Optional[str] = None,
        WS_BOT_ID: Optional[str] = None,
    ):
        params = {
            "task_name": task_name,
        }
        if uid:
            params["uid"] = uid

        if WS_BOT_ID:
            params["WS_BOT_ID"] = WS_BOT_ID

        if subscribe_type == "session" and event.user_type == "group":
            await Subscribe.delete_row(group_id=event.group_id, **params)
        else:
            await Subscribe.delete_row(user_id=event.user_id, **params)


gs_subscribe = RoverSubscribeManager()
