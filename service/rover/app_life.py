"""服务生命周期。启动顺序: 建库 → 载插件 → 建表迁移 → 启动钩子与调度器。"""

import asyncio
import importlib
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rover.logger import logger

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"

# 目录名 → 内层包名(上游插件都是同名双层目录)
PLUGIN_PACKAGES = ["XutheringWavesUID", "RoverSign", "ScoreEcho"]

# 面向原框架自带模型的模块, dsh 有自己的模型, 不加载
SKIP_MODULES = {"wutheringwaves_ai_rag"}

# 运行时的硬性前提: 出图走本地 HTML, 没有远端渲染器。这两项在设置页里也不展示
CONFIG_FORCED = {
    "XutheringWavesUID": {
        "UseHtmlRender": True,
        "RemoteRenderEnable": False,
        # 推送不绑 dsh 会话, 会落到全局收件箱并出现在每张卡片上, 本地关掉
        "WavesAnnOpen": False,
    },
}

# 初值: 只在插件第一次装载时写一次, 之后以用户在设置页里的选择为准
CONFIG_SEED = {
    "XutheringWavesUID": {
        "RankActiveFilterGroup": False,
        "ActiveUserDays": 0,
    },
    "RoverSign": {
        "UserWavesSignin": True,
        "UserPGRSignin": True,
        "UserBBSSchedSignin": True,
        "SigninMaster": True,
        "SignActiveUserOnly": False,
        "SigninMasterSkipInactive": False,
        "ActiveUserDays": 0,
    },
}

_plugins_loaded = False


def _inner_package(name: str) -> str:
    return f"plugins.{name}.{name}"


def load_plugins() -> None:
    """按上游的双层包结构加载, 加载前后各施加一次本地改造。"""
    global _plugins_loaded
    if _plugins_loaded:
        return
    _plugins_loaded = True

    from rover import compat, hooks

    compat.install([str(PLUGINS_DIR)])
    # 帮助表在插件 import 时就定型, 扩展模块清单得先按目录里实际有哪些插件对齐
    hooks.align_help_modules(
        {p.name for p in PLUGINS_DIR.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))}
    )

    missing = compat.missing_imports(PLUGINS_DIR)
    if missing:
        logger.warning(f"[加载] 运行时缺少上游用到的模块: {missing}")

    for name in PLUGIN_PACKAGES:
        package_name = _inner_package(name)
        try:
            package = importlib.import_module(package_name)
        except Exception as e:
            logger.error(f"[加载] 插件 {name} 载入失败: {e}")
            logger.exception(e)
            continue

        hooks.patch_modules(name, package_name)

        loaded = 0
        for module in pkgutil.iter_modules(package.__path__):
            if not module.ispkg or module.name.startswith("_") or module.name == "utils":
                continue
            if module.name in SKIP_MODULES:
                continue
            try:
                importlib.import_module(f"{package_name}.{module.name}")
                loaded += 1
            except Exception as e:
                logger.error(f"[加载] 模块 {name}.{module.name} 载入失败: {e}")
                logger.exception(e)
        logger.success(f"[加载] {name} 已载入 {loaded} 个功能模块")

    importlib.import_module("rover.builtin")
    hooks.apply_defaults(CONFIG_FORCED)
    hooks.seed_defaults(CONFIG_SEED)
    hooks.align_local_urls()
    hooks.drop_commands()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from rover.aps import start_scheduler, stop_scheduler
    from rover.media import register_cleanup_job
    from rover.server import core_shutdown_execute, core_start_before_execute, core_start_execute
    from rover.utils.database.base_models import init_database
    from rover.utils.database.startup import init_all

    await init_database()
    load_plugins()
    await init_all()
    await core_start_before_execute()
    asyncio.create_task(core_start_execute())
    register_cleanup_job()
    await start_scheduler()
    logger.success("[服务] 启动完成")
    try:
        yield
    finally:
        await stop_scheduler()
        await core_shutdown_execute()
        logger.info("[服务] 已停止")


app = FastAPI(title="鸣潮服务", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
