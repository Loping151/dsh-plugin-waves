import importlib
from typing import List

from sqlmodel import SQLModel
from sqlalchemy.sql import text

from rover.logger import logger

from . import base_models
from .base_models import init_database

CORE_DATABASE_MODEL_MODULES = ("rover.utils.database.models",)

# 插件在导入时 extend 本列表, 因此必须是模块级可变 list
exec_list: List[str] = [
    "ALTER TABLE Subscribe ADD COLUMN uid TEXT DEFAULT NULL;",
    "ALTER TABLE Subscribe ADD COLUMN WS_BOT_ID TEXT DEFAULT NULL;",
    "ALTER TABLE Subscribe ADD COLUMN extra_data TEXT DEFAULT NULL;",
    "ALTER TABLE Subscribe ADD COLUMN msg_id TEXT DEFAULT NULL;",
    "CREATE INDEX ix_subscribe_task_name ON Subscribe (task_name);",
    "CREATE INDEX ix_subscribe_uid ON Subscribe (uid);",
    "CREATE INDEX ix_subscribe_task_name_uid ON Subscribe (task_name, uid);",
]


def import_database_models() -> None:
    """导入表模型, 确保 create_all 能看到完整 metadata。"""
    for module_name in CORE_DATABASE_MODEL_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as e:
            logger.warning(f"[数据库] 导入模型模块失败: {module_name}, 跳过对应表创建: {e}")


async def create_core_tables() -> None:
    import_database_models()
    async with base_models.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("[数据库] 核心数据库表创建成功!")


async def trans_adapter() -> None:
    async with base_models.async_maker() as session:
        for _t in exec_list:
            try:
                await session.execute(text(_t))
                await session.commit()
            except Exception:  # noqa: E722
                pass


async def init_all() -> None:
    """建库建表并补齐历史列。

    插件模块在导入时会绑定 base_models.engine 并 extend exec_list,
    因此需要先 await init_database() 再导入插件, 最后调用本函数。
    """
    await init_database()
    await create_core_tables()
    await trans_adapter()
