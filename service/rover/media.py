"""媒体落盘与 HTML 载体。渲染产物存文件、对外给 /api/media/<id> 链接。"""

import asyncio
import hashlib
import os
import time
from pathlib import Path
from stat import S_ISREG
from typing import Dict, List, Optional, Tuple

from rover.data_store import get_res_path
from rover.logger import logger

MEDIA_DIR: Path = get_res_path() / "media"

# 刚落盘的产物在此秒数内不参与超限淘汰, 避免删掉前端正在加载的卡片
GRACE_SECONDS = 300
# 超限淘汰的目标水位
TARGET_RATIO = 0.8
# 累计写入量达到此值才做一次目录扫描清理
CHECK_BYTES = 32 * 1024 * 1024
# 访问时刷新 mtime 的最小间隔
TOUCH_INTERVAL = 60

_written_bytes = 0


def _max_bytes() -> int:
    from rover.config import core_config

    try:
        return int(core_config.get_config("media_max_mb") or 0) * 1024 * 1024
    except Exception:
        return 512 * 1024 * 1024


class HtmlBytes(bytes):
    """HTML 渲染产物。是 bytes 子类, 因此能穿透插件内所有 `if img_bytes:` 判断。"""

    html: str
    template_name: str

    def __new__(cls, html: str, template_name: str = ""):
        obj = super().__new__(cls, html.encode("utf-8"))
        obj.html = html
        obj.template_name = template_name
        return obj


def save_media(data: bytes, ext: str = "jpg") -> str:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(data).hexdigest()[:20]
    name = f"{digest}.{ext}"
    path = MEDIA_DIR / name
    if path.exists():
        _touch(path)
    else:
        path.write_bytes(data)
        _on_written(len(data))
    return name


async def render_png(name: str) -> Optional[Path]:
    """把存好的 HTML 卡片用无头浏览器拍成 PNG, 按原始设计宽度出图, 结果缓存复用。"""
    source = media_path(name)
    if source is None or source.suffix != ".html":
        return None
    target = source.with_suffix(".png")
    if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
        _touch(target)
        return target

    from playwright.async_api import async_playwright

    async with async_playwright() as driver:
        browser = await driver.chromium.launch(args=["--disable-gpu"])
        try:
            page = await browser.new_page(viewport={"width": 1600, "height": 1200})
            await page.goto(source.as_uri(), wait_until="load")
            # 桥接脚本没收到宿主宽度时不缩放, 量到的就是设计尺寸
            await page.wait_for_timeout(600)
            size = await page.evaluate(
                "() => { const el = document.querySelector('.container') || document.body;"
                " return { w: Math.ceil(el.scrollWidth), h: Math.ceil(el.scrollHeight) }; }"
            )
            width = max(1, min(int(size["w"]), 4000))
            height = max(1, min(int(size["h"]), 30000))
            await page.set_viewport_size({"width": width, "height": min(height, 2000)})
            await page.wait_for_timeout(400)
            data = await page.screenshot(
                full_page=True, clip={"x": 0, "y": 0, "width": width, "height": height}
            )
        finally:
            await browser.close()

    target.write_bytes(data)
    _on_written(len(data))
    logger.info(f"[媒体] 卡片截图 {name} → {width}x{height} {len(data) // 1024}KB")
    return target


def media_url(name: str) -> str:
    return f"/api/media/{name}"


def media_path(name: str) -> Optional[Path]:
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    path = MEDIA_DIR / name
    if not path.is_file():
        return None
    _touch(path)
    return path


def _touch(path: Path) -> None:
    """刷新 mtime, 使淘汰顺序按最近使用时间。"""
    try:
        if time.time() - path.stat().st_mtime > TOUCH_INTERVAL:
            os.utime(path, None)
    except OSError:
        pass


def _on_written(size: int) -> None:
    global _written_bytes
    _written_bytes += size
    if _written_bytes < CHECK_BYTES:
        return
    _written_bytes = 0
    try:
        cleanup_media()
    except Exception as e:
        logger.warning(f"[媒体清理] 写入触发的清理失败: {e}")


def _scan() -> Tuple[List[Tuple[float, int, Path]], int]:
    entries: List[Tuple[float, int, Path]] = []
    total = 0
    try:
        it = list(MEDIA_DIR.iterdir())
    except OSError:
        return entries, total
    for path in it:
        try:
            st = path.stat()
        except OSError:
            continue
        if not S_ISREG(st.st_mode):
            continue
        entries.append((st.st_mtime, st.st_size, path))
        total += st.st_size
    return entries, total


def media_usage() -> Dict[str, float]:
    if not MEDIA_DIR.is_dir():
        return {"files": 0, "bytes": 0, "mb": 0.0}
    files = 0
    total = 0
    for path in MEDIA_DIR.iterdir():
        if path.is_file():
            files += 1
            total += path.stat().st_size
    return {"files": files, "bytes": total, "mb": total / 1024 / 1024}


def cleanup_media() -> Dict[str, int]:
    if not MEDIA_DIR.is_dir():
        return {"removed": 0, "freed": 0, "remain": 0}
    """超容量上限时按最久未使用淘汰到目标水位; 不按时间删, 历史卡片还引用着。"""
    now = time.time()
    limit = _max_bytes()
    entries, total = _scan()
    removed = 0
    freed = 0
    alive: List[Tuple[float, int, Path]] = list(entries)

    if limit > 0 and total > limit:
        target = int(limit * TARGET_RATIO)
        alive.sort(key=lambda item: item[0])
        for mtime, size, path in alive:
            if total <= target:
                break
            if now - mtime < GRACE_SECONDS:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
            freed += size
            total -= size

    if removed:
        logger.info(
            f"[媒体清理] 删除 {removed} 个, 释放 {freed / 1048576:.1f}MB, "
            f"剩余 {total / 1048576:.1f}MB / 上限 {limit / 1048576:.0f}MB"
        )
    return {
        "removed": removed,
        "freed_bytes": freed,
        "remaining_bytes": total,
        "limit_bytes": limit,
    }


async def _scheduled_cleanup() -> None:
    await asyncio.to_thread(cleanup_media)


def register_cleanup_job() -> None:
    """注册周期清理, 由 app_life 在调度器启动前调用。"""
    from rover.aps import scheduler

    scheduler.add_job(
        _scheduled_cleanup,
        "interval",
        minutes=30,
        id="media_cleanup",
        replace_existing=True,
    )
