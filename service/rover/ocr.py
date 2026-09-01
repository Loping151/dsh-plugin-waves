"""图片卡片的本地 OCR 摘要: 评分/面板等 PIL 出图对纯文本模型不可见, 抽出文字随 summary 给模型。"""

import asyncio
import hashlib
from typing import Any, Dict, Optional

from rover.logger import logger

MIN_BYTES = 20 * 1024
MAX_SIDE = 2000
DIGEST_LIMIT = 800
_CACHE_KEEP = 64

_engine: Any = None
_engine_failed = False
_cache: Dict[str, str] = {}
_lock = asyncio.Lock()


def _get_engine():
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    try:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    except Exception as e:  # noqa: BLE001
        _engine_failed = True
        logger.warning(f"[OCR] rapidocr 不可用, 图片文字摘要关闭: {e}")
    return _engine


def _run(raw: bytes) -> str:
    import cv2
    import numpy as np

    engine = _get_engine()
    if engine is None:
        return ""
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return ""
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    result, _ = engine(img)
    lines = [str(item[1]).strip() for item in result or [] if item and item[1]]
    text = " ".join(x for x in lines if x)
    return text[:DIGEST_LIMIT] + " …" if len(text) > DIGEST_LIMIT else text


async def image_digest(raw: Optional[bytes]) -> str:
    """一张卡片图 → 单行文字摘要; 太小的图(头像等)与识别失败返回空串。"""
    if not raw or len(raw) < MIN_BYTES:
        return ""
    key = hashlib.sha1(raw).hexdigest()
    if key in _cache:
        return _cache[key]
    # 串行跑: OCR 吃 CPU, 并发多张反而互相拖慢
    async with _lock:
        if key in _cache:
            return _cache[key]
        try:
            text = await asyncio.to_thread(_run, raw)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[OCR] 识别失败: {e}")
            text = ""
        if len(_cache) >= _CACHE_KEEP:
            _cache.pop(next(iter(_cache)))
        _cache[key] = text
        return text
