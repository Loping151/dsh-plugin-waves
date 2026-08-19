"""进程重启。退出码 75 交给宿主(dsh)重新拉起, 不要 execv。

服务是 Node spawn 的 `python -m rover.main`。execv 用 sys.argv 会变成
`python rover/main.py`, sys.path 不对, 进程起不来。
"""

import os
import sys
from typing import Any, Optional

from rover.logger import logger

# 与 lib/host/service.js 约定: 75 = 主动重启, 宿主马上再拉起
RESTART_EXIT = 75


async def restart_service(event: Optional[Any] = None, is_send: bool = True) -> None:
    from rover.server import core_shutdown_execute

    logger.info(f"[重启] 准备重启当前进程 pid={os.getpid()}")
    if is_send and event is not None:
        logger.info("[重启] 重启由会话触发，重启后无法回执")

    try:
        await core_shutdown_execute()
    except Exception as e:
        logger.warning(f"[重启] 关闭钩子执行异常: {e}")

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    logger.info(f"[重启] 退出 {RESTART_EXIT}, 由宿主重新拉起")
    os._exit(RESTART_EXIT)
