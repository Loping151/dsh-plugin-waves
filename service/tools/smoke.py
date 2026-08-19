#!/usr/bin/env python3
"""不起 HTTP 服务, 直接跑一遍启动流程与若干命令。"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def local_user() -> str:
    """本机使用者标识, 从配置里取, 不写死。"""
    from rover.config import core_config

    masters = core_config.get_config("masters") or []
    return str(masters[0]) if masters else "local"


async def boot():
    from rover.app_life import load_plugins
    from rover.server import core_start_before_execute
    from rover.utils.database.base_models import init_database
    from rover.utils.database.startup import init_all

    await init_database()
    load_plugins()
    await init_all()
    await core_start_before_execute()


async def run_commands(commands):
    from rover.api_render import render_segments, summarize
    from rover.handler import build_message, dispatch, normalize_command
    from rover.sv import SL

    print(f"\n注册: 插件={list(SL.plugins.keys())} SV={len(SL.lst)} "
          f"触发器={sum(len(t) for sv in SL.lst.values() for t in sv.TL.values())}")

    for raw in commands:
        command = normalize_command(raw)
        result = await dispatch(build_message(command, user_id=local_user()))
        rendered = await render_segments(result["segments"])
        kinds = [s["type"] for s in rendered]
        print(f"\n[{command}] 命中={result['matched']} 段={kinds} 用时={result['elapsed']:.2f}s")
        text = summarize(rendered)
        if text:
            print("  " + text.replace("\n", "\n  ")[:600])


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("commands", nargs="*", default=[])
    args = parser.parse_args()
    await boot()
    if args.commands:
        await run_commands(args.commands)
    else:
        await run_commands([])


if __name__ == "__main__":
    asyncio.run(main())
