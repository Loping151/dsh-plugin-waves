"""消息段 → 前端 JSON。图片/HTML 落盘走 /api/media, 避免把 MB 级 base64 塞进响应。"""

import base64
import html as html_lib
import re
from typing import Any, Dict, List

import msgspec

from rover.logger import logger
from rover.media import media_url, save_media
from rover.models import Message

_IMAGE_MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG": "png",
    b"GIF8": "gif",
    b"RIFF": "webp",
}


def _guess_ext(data: bytes) -> str:
    for magic, ext in _IMAGE_MAGIC.items():
        if data.startswith(magic):
            return ext
    return "jpg"


_DROP_TAGS = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
# 头像格上挂着角色名, 摊平成文字时按原位置补进去
_NAMED_TAG = re.compile(r'<[^>]*data-ww-name="([^"]*)"[^>]*>')
_TAGS = re.compile(r"<[^>]+>")
_BLANK = re.compile(r"[ \t ]+")
# 卡片里的数值也交给模型: 太长会挤占上下文, 截断即可
DIGEST_LIMIT = 1600


def html_digest(html: str) -> str:
    """把卡片里的可见文字抽出来, 让模型也能看到面板上的具体数值。"""
    text = _DROP_TAGS.sub(" ", html)
    text = _NAMED_TAG.sub(lambda m: m.group(0) + m.group(1) + " ", text)
    text = _TAGS.sub(" ", text)
    text = _BLANK.sub(" ", html_lib.unescape(text))
    words: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            words.append(line)
    joined = " ".join(words)
    return joined[:DIGEST_LIMIT] + " …" if len(joined) > DIGEST_LIMIT else joined


def _image_segment(data: Any) -> Dict[str, Any]:
    if isinstance(data, str):
        if data.startswith("link://"):
            return {"type": "image", "url": data[len("link://") :]}
        if data.startswith("base64://"):
            raw = base64.b64decode(data[len("base64://") :])
        else:
            return {"type": "image", "url": data}
    elif isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
    else:
        return {"type": "text", "text": str(data)}
    name = save_media(raw, _guess_ext(raw))
    return {"type": "image", "url": media_url(name), "bytes": len(raw)}


async def render_segments(segments: List[Message]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for seg in segments:
        stype = seg.type or "text"
        data = seg.data
        try:
            if stype == "text":
                text = "" if data is None else str(data)
                if text.strip():
                    out.append({"type": "text", "text": text})
            elif stype == "image":
                out.append(_image_segment(data))
            elif stype == "html":
                html = data if isinstance(data, str) else str(data)
                name = save_media(html.encode("utf-8"), "html")
                out.append(
                    {
                        "type": "html",
                        "url": media_url(name),
                        "bytes": len(html),
                        "digest": html_digest(html),
                    }
                )
            elif stype == "node":
                items = data if isinstance(data, list) else []
                children = await render_segments(
                    [i if isinstance(i, Message) else Message(**i) for i in items]
                )
                out.append({"type": "node", "items": children})
            elif stype == "file":
                raw = str(data or "")
                file_name, _, payload = raw.partition("|")
                if payload.startswith("link://"):
                    out.append(
                        {"type": "file", "name": file_name, "url": payload[len("link://") :]}
                    )
                else:
                    ext = file_name.rsplit(".", 1)[-1] if "." in file_name else "bin"
                    name = save_media(base64.b64decode(payload), ext)
                    out.append({"type": "file", "name": file_name, "url": media_url(name)})
            elif stype == "buttons":
                out.append({"type": "buttons", "buttons": msgspec.to_builtins(data)})
            elif stype == "at":
                out.append({"type": "at", "target": str(data)})
            else:
                out.append({"type": "text", "text": f"[{stype}]"})
        except Exception as e:
            logger.warning(f"消息段渲染失败 type={stype}: {e}")
            out.append({"type": "text", "text": f"[{stype} 渲染失败]"})
    return out


def summarize(rendered: List[Dict[str, Any]]) -> str:
    """给模型看的纯文本摘要（图片/HTML 只留占位, 不塞内容）。"""
    parts: List[str] = []
    for seg in rendered:
        stype = seg.get("type")
        if stype == "text":
            parts.append(seg.get("text", ""))
        elif stype == "image":
            parts.append("[图片已在卡片中展示]")
        elif stype == "html":
            digest = seg.get("digest") or ""
            parts.append(
                f"[图文卡片已在界面中展示]\n卡片内容: {digest}" if digest
                else "[图文卡片已在界面中展示]"
            )
        elif stype == "node":
            parts.append(summarize(seg.get("items", [])))
        elif stype == "file":
            parts.append(f"[文件 {seg.get('name')}]")
        elif stype == "buttons":
            labels = []
            for row in seg.get("buttons") or []:
                for btn in row if isinstance(row, list) else [row]:
                    if isinstance(btn, dict) and btn.get("text"):
                        labels.append(str(btn["text"]))
            if labels:
                parts.append("可用快捷指令: " + " / ".join(labels))
    return "\n".join(p for p in parts if p)
