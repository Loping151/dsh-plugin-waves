#!/usr/bin/env python3
"""跑一批命令, 汇总命中与回复形态。默认打到本机服务。

只跑只读命令: 删除/清理/压缩/上传类会改动素材与数据库, 一律拦下。
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

COMMANDS = [
    "ww帮助", "ww查询", "ww体力", "ww探索", "ww库洛币", "ww积分", "ww日历", "ww签到日历",
    "ww深塔", "ww海墟", "ww矩阵", "ww全息",
    "ww练度", "ww声骸", "ww星声",
    "ww椿面板", "ww椿伤害", "ww椿权重", "ww椿优化", "ww椿总排行", "ww椿声骸总排行",
    "ww椿攻略", "ww椿图鉴", "ww椿养成", "ww武器列表", "ww套装列表",
    "ww练度总排行", "ww无尽总排行", "ww矩阵总排行",
    "ww抽卡记录", "ww抽卡帮助", "ww兑换码", "ww卡池倒计时",
    "ww持有率", "ww深塔出场率", "ww矩阵配队",
    "ww签到", "ww签到帮助", "ww分析帮助", "ww综合评分说明",
    "ww查看特征码", "ww更新记录", "ww别名列表", "ww公告",
]


# 会改动素材/数据库的命令, 不允许出现在自检里
DESTRUCTIVE = ("删除", "清理", "清除", "压缩", "上传", "重新计算", "强制下载", "导入")


def guard(commands: list) -> list:
    blocked = [c for c in commands if any(word in c for word in DESTRUCTIVE)]
    if blocked:
        sys.exit("这些命令有副作用, 不能用于自检: " + " ".join(blocked))
    return commands


def run(base: str, command: str, timeout: int) -> dict:
    body = json.dumps({"command": command}).encode()
    req = urllib.request.Request(
        f"{base}/api/chat", data=body, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "summary": f"HTTP {e.code}", "segments": [], "matched": []}
    except Exception as e:
        return {"ok": False, "summary": f"{type(e).__name__}: {e}", "segments": [], "matched": []}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:9777")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("commands", nargs="*")
    args = parser.parse_args()

    commands = guard(args.commands or COMMANDS)
    stats = {"html": 0, "image": 0, "text": 0, "node": 0, "other": 0}
    unmatched, failed = [], []

    for command in commands:
        data = run(args.base, command, args.timeout)
        segs = data.get("segments") or []
        kinds = [s.get("type") for s in segs]
        for kind in kinds:
            stats[kind if kind in stats else "other"] += 1
        summary = (data.get("summary") or "").replace("\n", " ")[:70]
        flag = "√" if data.get("ok") else "×"
        if not data.get("ok"):
            unmatched.append(command)
        elif not kinds:
            failed.append(command)
        print(f"{flag} {command:<16} {','.join(kinds) or '-':<22} {summary}")

    print(f"\n段统计: {stats}")
    if unmatched:
        print(f"未命中/失败 ({len(unmatched)}): {' '.join(unmatched)}")
    if failed:
        print(f"命中但无回复 ({len(failed)}): {' '.join(failed)}")
    print(f"总计 {len(commands)} 条, 正常 {len(commands) - len(unmatched) - len(failed)} 条")
    sys.exit(1 if unmatched or failed else 0)


if __name__ == "__main__":
    main()
