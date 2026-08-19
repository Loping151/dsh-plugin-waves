#!/usr/bin/env python3
"""拉取/更新上游插件。

插件目录保持上游原样(带 .git), 更新就是 git pull。本地差异全在 rover/hooks.py,
不改插件源码, 所以更新不会冲突。
GitHub 不可达时自动改走 cnb.cool 镜像。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"

REPOS = {
    "XutheringWavesUID": {
        "github": "https://github.com/Loping151/XutheringWavesUID.git",
        "cnb": "https://cnb.cool/gscore-mirror/XutheringWavesUID.git",
    },
    "RoverSign": {
        "github": "https://github.com/Loping151/RoverSign.git",
        "cnb": "https://cnb.cool/gscore-mirror/RoverSign.git",
    },
    "ScoreEcho": {
        "github": "https://github.com/Loping151/ScoreEcho.git",
        "cnb": "https://cnb.cool/gscore-mirror/ScoreEcho.git",
    },
}

# clone/pull 卡住太久也算不可达, 好切镜像
CLONE_TIMEOUT = 90
PULL_TIMEOUT = 60

_UNREACHABLE = (
    "could not resolve host",
    "failed to connect",
    "connection timed out",
    "operation timed out",
    "network is unreachable",
    "no route to host",
    "unable to access",
    "connection reset",
    "connection refused",
    "the remote end hung up unexpectedly",
    "early eof",
    "rpc failed",
    "gnutlsrecv error",
    "openssl ssl_connect",
    "ssl_connect",
    "tls connect error",
    "couldn't connect to server",
    "empty reply from server",
    "proxy connect aborted",
    "failed to connect to github.com",
)


def run(args, cwd=None, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return subprocess.CompletedProcess(
            args, 124, out, (err + "\nconnection timed out").strip()
        )


def is_unreachable(result: subprocess.CompletedProcess) -> bool:
    if result.returncode == 0:
        return False
    text = f"{result.stderr} {result.stdout}".lower()
    return any(token in text for token in _UNREACHABLE)


def _rm_incomplete(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)


def clone_with_fallback(name: str, dest: Path, github: str, cnb: str) -> str:
    result = run(["git", "clone", "--depth", "1", github, str(dest)], timeout=CLONE_TIMEOUT)
    source = "github"
    if result.returncode:
        _rm_incomplete(dest)
        if not is_unreachable(result):
            return f"{name}: 克隆失败 {result.stderr.strip()[:160]}"
        print(f"{name}: GitHub 不可达, 改用 cnb {cnb}")
        result = run(["git", "clone", "--depth", "1", cnb, str(dest)], timeout=CLONE_TIMEOUT)
        source = "cnb"
        if result.returncode:
            _rm_incomplete(dest)
            return f"{name}: cnb 克隆也失败 {result.stderr.strip()[:160]}"
    head = run(["git", "log", "--oneline", "-1"], cwd=dest).stdout.strip()
    return f"{name}: 已克隆 ({source}) {head}"


def pull_with_fallback(name: str, dest: Path, cnb: str) -> Optional[str]:
    """origin 是 GitHub 且不可达时, 把 origin 改成 cnb 再拉一次。失败返回错误文案。"""
    result = run(["git", "pull", "--ff-only"], cwd=dest, timeout=PULL_TIMEOUT)
    if result.returncode == 0:
        return None
    origin = run(["git", "remote", "get-url", "origin"], cwd=dest).stdout.strip()
    if not is_unreachable(result) or "github.com" not in origin:
        return f"{name}: 拉取失败 {result.stderr.strip()[:160]}"
    print(f"{name}: GitHub 不可达, origin 改为 cnb")
    setu = run(["git", "remote", "set-url", "origin", cnb], cwd=dest)
    if setu.returncode:
        return f"{name}: 无法改 origin {setu.stderr.strip()[:120]}"
    result = run(["git", "pull", "--ff-only"], cwd=dest, timeout=PULL_TIMEOUT)
    if result.returncode:
        return f"{name}: cnb 拉取也失败 {result.stderr.strip()[:160]}"
    return None


def sync_one(name: str, urls: dict) -> str:
    dest = PLUGINS_DIR / name
    github, cnb = urls["github"], urls["cnb"]
    if not (dest / ".git").is_dir():
        if dest.exists():
            return f"{name}: 目录已存在但不是 git 仓库, 请手工处理 {dest}"
        return clone_with_fallback(name, dest, github, cnb)

    dirty = run(["git", "status", "--porcelain"], cwd=dest).stdout
    local_edits = [ln for ln in dirty.splitlines() if not ln.startswith("??")]
    if local_edits:
        return f"{name}: 有本地改动, 已跳过(本地差异应写进 rover/hooks.py):\n    " + "\n    ".join(
            local_edits[:5]
        )

    before = run(["git", "rev-parse", "--short", "HEAD"], cwd=dest).stdout.strip()
    err = pull_with_fallback(name, dest, cnb)
    if err:
        return err
    after = run(["git", "rev-parse", "--short", "HEAD"], cwd=dest).stdout.strip()
    if before == after:
        return f"{name}: 已是最新 {after}"
    log = run(["git", "log", "--oneline", f"{before}..{after}"], cwd=dest).stdout.strip()
    return f"{name}: {before} → {after}\n    " + "\n    ".join(log.splitlines()[:8])


def check_compat() -> int:
    """更新后自检: 上游有没有用到本运行时还没提供的模块。"""
    sys.path.insert(0, str(PLUGINS_DIR.parent))
    from rover import compat

    missing = compat.missing_imports(PLUGINS_DIR)
    if missing:
        print("\n运行时缺少这些上游模块, 需要在 rover/compat.py 补映射:")
        for name in missing:
            print(f"  {name}")
        return 1
    print("\n兼容层自检通过")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="只做兼容层自检, 不拉取")
    args = parser.parse_args()

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    (PLUGINS_DIR / "__init__.py").touch()

    if not args.check_only:
        for name, urls in REPOS.items():
            print(sync_one(name, urls))

    code = check_compat()
    if not args.check_only:
        print("\n更新后请重启服务, 并跑 tools/regression.py 自检。")
    sys.exit(code)


if __name__ == "__main__":
    main()
