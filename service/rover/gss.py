"""连接注册表。定时推送与订阅回发都从这里取发送端。"""

from typing import Dict

from rover.bot import PushBot

DEFAULT_BOT_ID = "dsh"


class ServerState:
    def __init__(self):
        self.active_bot: Dict[str, PushBot] = {DEFAULT_BOT_ID: PushBot(DEFAULT_BOT_ID, DEFAULT_BOT_ID)}
        self.bot_users: Dict[str, list] = {}

    def get_bot(self, bot_id: str = DEFAULT_BOT_ID) -> PushBot:
        return self.active_bot.get(bot_id) or self.active_bot[DEFAULT_BOT_ID]


gss = ServerState()
