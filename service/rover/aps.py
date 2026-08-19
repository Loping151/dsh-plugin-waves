"""定时任务调度器。插件通过 `@scheduler.scheduled_job` / `scheduler.add_job` 注册。"""

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from rover.logger import logger

# default 执行器保持 AsyncIOExecutor（协程任务必须在主事件循环跑），
# 阻塞型任务显式 add_job(..., executor="threadpool")
executor = ThreadPoolExecutor(10)
def _misfire_grace_time() -> int:
    from rover.config import core_config

    try:
        return int(core_config.get_config("misfire_grace_time") or 90)
    except Exception:
        return 90


job_defaults = {"misfire_grace_time": _misfire_grace_time(), "coalesce": True}
options = {
    "executors": {"threadpool": executor},
    "job_defaults": job_defaults,
    "timezone": "Asia/Shanghai",
}


class _Scheduler(AsyncIOScheduler):
    def scheduled_job(self, *args, **kwargs):
        kwargs.pop("replace_existing", None)
        return super().scheduled_job(*args, **kwargs)


scheduler = _Scheduler()
scheduler.configure(**options)


async def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("[调度器] 启动完成")


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[调度器] 已关闭定时任务")
