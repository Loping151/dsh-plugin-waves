"""本机自带的运维命令: 更新插件、重启服务、查看状态。"""

import asyncio
import sys
from pathlib import Path
from typing import List, Tuple

from rover.bot import Bot
from rover.logger import logger
from rover.models import Event
from rover.sv import SV, Plugins

PLUGIN_NAME = "本地"
SERVICE_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = SERVICE_ROOT / "plugins"

Plugins(name=PLUGIN_NAME, pm=0)

sv_update = SV("本地更新", pm=0, priority=1)
sv_restart = SV("本地重启", pm=0, priority=1)
sv_state = SV("本地状态", pm=0, priority=1)


# 本机自带的命令; 帮助图里单列一类
OPS_COMMANDS = [
    ("更新插件", "拉取上游更新并做兼容自检"),
    ("重启服务", "让更新或配置改动生效"),
    ("服务状态", "查看各插件版本、命令数与缓存占用"),
]


def ops_help_entries() -> list:
    """按帮助数据的条目格式给出, 由帮助渲染并入图中。"""
    return [
        {"name": name, "desc": desc, "eg": name, "need_admin": False}
        for name, desc in OPS_COMMANDS
    ]


def adapt_guide(missing: List[str]) -> str:
    """上游用了本运行时没有的接口时, 把适配步骤交给模型去做。"""
    rover_dir = SERVICE_ROOT / "rover"
    return "\n".join(
        [
            "上游更新用到了本插件运行时尚未提供的接口, 需要适配后才能正常加载。",
            "请你(AI)按下面的步骤改好, 不要只是转述给用户:",
            "",
            "缺失的模块:",
            *(f"  {name}" for name in missing),
            "",
            f"1. 逐个查看上游怎么用它: grep -rn '{missing[0]}' {PLUGINS_DIR}",
            "2. 到原框架源码里读它的真实实现(若本机有 gsuid_core 源码树), 或据调用方式推断契约。",
            f"3. 在 {rover_dir} 下实现同名模块与同签名的函数/类, 语义要对齐, 不能只给空壳,",
            "   除非调用方本来就容忍失败。",
            f"4. 在 {rover_dir}/compat.py 的 MODULE_MAP 里加一行映射(上游路径 → rover 路径);",
            "   若上游沿用了带 Gs 前缀的类名, 在 CONFIG_CLASS_ALIASES 或 SYMBOL_ALIASES 里加别名。",
            f"5. 自检: cd {SERVICE_ROOT} && .venv/bin/python tools/update_plugins.py --check-only",
            "6. 起服务确认加载无报错, 再跑 tools/regression.py 回归, 最后让用户重启。",
        ]
    )


async def _run(args: List[str], cwd: Path) -> Tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", "replace").strip()


async def _update_one(name: str) -> str:
    repo = PLUGINS_DIR / name
    if not (repo / ".git").is_dir():
        return f"{name}: 不是 git 仓库, 跳过"

    code, dirty = await _run(["git", "status", "--porcelain"], repo)
    if code == 0 and any(not ln.startswith("??") for ln in dirty.splitlines()):
        return f"{name}: 有本地改动, 跳过"

    _, before = await _run(["git", "rev-parse", "--short", "HEAD"], repo)
    code, out = await _run(["git", "pull", "--ff-only"], repo)
    if code != 0:
        return f"{name}: 拉取失败 {out.splitlines()[-1][:80] if out else ''}"
    _, after = await _run(["git", "rev-parse", "--short", "HEAD"], repo)
    if before == after:
        return f"{name}: 已是最新 {after}"
    _, log = await _run(["git", "log", "--oneline", f"{before}..{after}"], repo)
    lines = log.splitlines()[:5]
    return f"{name}: {before} → {after}\n" + "\n".join(f"  {ln}" for ln in lines)


@sv_update.on_fullmatch(("更新插件", "插件更新", "检查更新"), block=True)
async def update_plugins(bot: Bot, ev: Event):
    await bot.send("正在检查插件更新...")
    from rover import compat

    results = []
    for name in ("XutheringWavesUID", "RoverSign", "ScoreEcho"):
        try:
            results.append(await _update_one(name))
        except Exception as e:
            results.append(f"{name}: 出错 {e}")

    from rover.sv import get_plugin_available_prefix

    try:
        prefix = get_plugin_available_prefix(PLUGIN_NAME)
    except ValueError:
        prefix = ""

    missing = compat.missing_imports(PLUGINS_DIR)
    tail = "\n全部已是最新, 无需重启。"
    if any("→" in r for r in results):
        tail = f"\n更新完成, 发送【{prefix}重启服务】后生效。"
    await bot.send("\n".join(results) + tail)

    if missing:
        await bot.send(adapt_guide(missing))


@sv_restart.on_fullmatch(("重启服务", "重启"), block=True)
async def restart(bot: Bot, ev: Event):
    from rover.restart import restart_service

    await bot.send("正在重启服务, 约十几秒后恢复...")
    logger.info("[运维] 收到重启命令")
    asyncio.get_running_loop().call_later(1, lambda: asyncio.ensure_future(restart_service()))


@sv_state.on_fullmatch(("服务状态", "运行状态"), block=True)
async def service_state(bot: Bot, ev: Event):
    from rover.media import media_usage
    from rover.sv import SL

    lines = [f"Python {sys.version.split()[0]}"]
    for name in ("XutheringWavesUID", "RoverSign", "ScoreEcho"):
        repo = PLUGINS_DIR / name
        if (repo / ".git").is_dir():
            _, head = await _run(["git", "log", "-1", "--format=%h %cd", "--date=short"], repo)
            lines.append(f"{name}: {head}")
    lines.append(
        f"命令: {sum(len(t) for sv in SL.lst.values() for t in sv.TL.values())} 条 / {len(SL.lst)} 项功能"
    )
    try:
        usage = media_usage()
        lines.append(f"渲染缓存: {usage['files']} 个 / {usage['mb']:.1f}MB")
    except Exception:
        pass
    await bot.send("\n".join(lines))
