"""知识条目 → HTML 卡片。条目正文是受限 markdown(标题/列表/图片/竖线行), 渲成深色图文卡。"""

import html as html_lib
import re
from typing import List

_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_HEAD = re.compile(r"^(#{1,4})\s+(.*)$")

_CSS = """
body{margin:0;padding:0;background:transparent;font-family:'PingFang SC','Microsoft YaHei',sans-serif}
.container{width:860px;box-sizing:border-box;padding:26px 30px;color:#e8eaf0;
  background:linear-gradient(160deg,#1b1f27 0%,#12151b 100%);border-radius:14px}
.kb-head{display:flex;align-items:baseline;gap:12px;border-bottom:1px solid rgba(212,177,99,.35);
  padding-bottom:12px;margin-bottom:14px}
.kb-title{font-size:24px;font-weight:800;background:linear-gradient(180deg,#f4e3b4,#d4b163);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.kb-tags{font-size:12px;color:#8b93a7}
.kb-src{margin-top:16px;font-size:11px;color:#5c6478}
h2{font-size:19px;color:#f4e3b4;margin:20px 0 8px;border-left:3px solid #d4b163;padding-left:9px}
h3{font-size:16px;color:#e8d9ae;margin:16px 0 6px}
h4{font-size:14px;color:#c9bd93;margin:12px 0 4px}
p{font-size:14px;line-height:1.75;margin:7px 0}
ul{margin:6px 0;padding-left:22px}
li{font-size:14px;line-height:1.7}
img{max-width:100%;border-radius:8px;margin:6px 0;display:block}
.kb-row{font-size:14px;line-height:1.8;color:#cfd5e2}
"""


def _inline(text: str) -> str:
    """转义后还原图片为 <img>; 其余按纯文本。"""
    parts: List[str] = []
    pos = 0
    for m in _IMG.finditer(text):
        parts.append(html_lib.escape(text[pos:m.start()]))
        alt = html_lib.escape(m.group(1))
        src = m.group(2)
        if src.startswith(("http://", "https://", "//")):
            parts.append(f'<img src="{html_lib.escape(src)}" alt="{alt}" loading="lazy">')
        pos = m.end()
    parts.append(html_lib.escape(text[pos:]))
    return "".join(parts)


def md_to_html(text: str) -> str:
    out: List[str] = []
    in_list = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if in_list and not stripped.startswith("- "):
            out.append("</ul>")
            in_list = False
        if not stripped:
            continue
        head = _HEAD.match(stripped)
        if head:
            level = min(len(head.group(1)) + 1, 4)
            out.append(f"<h{level}>{_inline(head.group(2))}</h{level}>")
        elif stripped.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(stripped[2:])}</li>")
        elif " | " in stripped:
            out.append(f'<div class="kb-row">{_inline(stripped)}</div>')
        else:
            out.append(f"<p>{_inline(stripped)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def render_entry_html(rec: dict) -> str:
    title = html_lib.escape(str(rec.get("title") or ""))
    tags = html_lib.escape(" · ".join(rec.get("tags") or []))
    source = html_lib.escape(str(rec.get("source") or ""))
    body = md_to_html(rec.get("content") or "")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body><div class="container">
<div class="kb-head"><span class="kb-title">{title}</span><span class="kb-tags">{tags}</span></div>
{body}
<div class="kb-src">内置知识库 · {source} · id {html_lib.escape(str(rec.get("id") or ""))}</div>
</div></body></html>"""
