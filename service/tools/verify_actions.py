#!/usr/bin/env python3
"""校验点击命令与卡片里的角色是否一一对上: 用每个格子后面的等级/共鸣链回查上下文。"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CASES = {
    "ww深塔": "abyss/abyss_card.html",
    "ww海墟": "abyss/slash_card.html",
    "ww矩阵": "abyss/matrix_detail_card.html",
    "ww全息": "abyss/challenge_card.html",
}

_CELL = re.compile(
    r'<div class="role-mini[^>]*?(?:data-ww-cmd="(?P<cmd>[^"]*)")?[^>]*>(?P<body>.*?)(?=<div class="role-mini|</div>\s*</div>\s*</div>)',
    re.S,
)


def local_user() -> str:
    """本机使用者标识, 从配置里取, 不写死。"""
    from rover.config import core_config

    masters = core_config.get_config("masters") or []
    return str(masters[0]) if masters else "local"


async def main() -> None:
    from rover import html_actions

    captured = []
    original = html_actions.annotate_html

    def spy(html, template_name, context):
        out = original(html, template_name, context)
        captured.append((template_name, context, out))
        return out

    html_actions.annotate_html = spy

    from rover.app_life import load_plugins
    from rover.handler import build_message, dispatch
    from rover.server import core_start_before_execute
    from rover.utils.database.base_models import init_database
    from rover.utils.database.startup import init_all

    await init_database()
    load_plugins()
    await init_all()
    await core_start_before_execute()

    # hooks 里的渲染函数按值抓过 annotate_html, 载入之后再把间谍塞进去
    import sys as _sys

    for module in list(_sys.modules.values()):
        if getattr(module, "annotate_html", None) is original:
            module.annotate_html = spy

    failures = 0
    for command, template in CASES.items():
        captured.clear()
        await dispatch(build_message(command, user_id=local_user()))
        hit = [c for c in captured if c[0] == template]
        if not hit:
            print(f"{command}: 未渲染 {template}")
            failures += 1
            continue
        _, context, html = hit[-1]
        roles = html_actions._EXTRACTORS[template](context)
        expect = [
            (html_actions._role_command(r), str(r.get("level") or ""), str(r.get("chain_name") or ""))
            for r in roles
        ]
        cells = [m.group(0) for m in html_actions._ROLE_TAG.finditer(html)]
        got_cmds = [
            (re.search(r'data-ww-cmd="([^"]+)"', c).group(1) if 'data-ww-cmd=' in c else None)
            for c in cells
        ]
        mismatch = []
        for i, (want, _lvl, _chain) in enumerate(expect):
            if i >= len(got_cmds):
                mismatch.append(f"#{i} 缺格子")
            elif got_cmds[i] != want:
                mismatch.append(f"#{i} 期望{want} 实得{got_cmds[i]}")
        extra = len(got_cmds) - len(expect)
        names = [c for c in got_cmds if c][:3]
        status = "对齐" if not mismatch and extra == 0 else "错位"
        if mismatch or extra:
            failures += 1
        print(f"{command}: 格子={len(got_cmds)} 上下文={len(expect)} {status} 示例={names}")
        for m in mismatch[:5]:
            print(f"    {m}")
        if extra:
            print(f"    多出 {extra} 个格子")

    print("\n结果:", "全部对齐" if failures == 0 else f"{failures} 项需修")


if __name__ == "__main__":
    asyncio.run(main())
