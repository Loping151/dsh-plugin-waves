"""游戏常识知识库: service/knowledge/ 下 jsonl 的加载、词法检索与世界书触发查询。

纯 stdlib、不依赖 rover 其它模块, wwdata 脚本可直接 import 复用。
存储粒度是"小节": {id: "<entry>#<n>", entry, title: "条目/小节", tags, source, triggers, content}
检索按小节返回; kb_get 传小节 id 取小节、传条目 id 取整条拼装。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SERVICE = Path(__file__).resolve().parents[1]
KB_DIR = SERVICE / "knowledge"
CHAR_ALIAS = SERVICE / "data" / "XutheringWavesUID" / "alias" / "char_alias.json"

_CJK = re.compile(r"[一-鿿]")
TRIGGER_MIN_LEN = 2
# 过泛词不做自动注入触发(检索不受影响)
BROAD_TRIGGERS = {"声骸", "资源", "补给", "头像", "武器", "角色", "攻略", "活动", "任务", "成就", "套装"}
# 只有这些层参与自动注入; event/article/story 只可检索
INJECT_TIERS = {"core", "guide"}
LOOKUP_MAX_HITS = 2
SNIPPET_LEN = 160
INJECT_CONTENT_LEN = 600

# tags → 触发优先级; 数值大者先注入
_PRIORITY_TAGS = [
    (10, ("共鸣者", "武器", "声骸", "合鸣效果")),
    (8, ("角色攻略", "游戏机制", "名词注释")),
    (7, ("游戏百科", "教程百科", "玩法攻略")),
]

_state: Optional[Dict[str, Any]] = None


def _canonical_chars() -> Set[str]:
    try:
        return set(json.loads(CHAR_ALIAS.read_text("utf-8")).keys())
    except (OSError, ValueError):
        return set()


def _priority(rec: dict) -> int:
    tags = set(rec.get("tags") or [])
    for score, keys in _PRIORITY_TAGS:
        if tags & set(keys):
            return score
    return 5


def _entry_title(sec: dict) -> str:
    return str(sec.get("entry_title") or "").strip() or str(sec.get("title") or "").rsplit("/", 1)[0]


def _load() -> Dict[str, Any]:
    global _state
    if _state is not None:
        return _state
    sections: Dict[str, dict] = {}
    entry_secs: Dict[str, List[str]] = {}
    for path in sorted(KB_DIR.rglob("*.jsonl")):
        source_kind = path.parent.name if path.parent != KB_DIR else path.stem
        for line in path.read_text("utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not rec.get("id") or not rec.get("content"):
                continue
            rec["_kind"] = source_kind
            sections[rec["id"]] = rec
            entry_secs.setdefault(rec.get("entry") or rec["id"], []).append(rec["id"])

    chars = _canonical_chars()
    # (触发词, 条目 id, 注入的小节 id, 优先级); 每条目同一词只登记最先声明它的小节
    triggers: List[Tuple[str, str, str, int]] = []
    for entry_id, sec_ids in entry_secs.items():
        first = sections[sec_ids[0]]
        if first.get("tier") and first["tier"] not in INJECT_TIERS:
            continue
        prio = int(first.get("priority") or _priority(first))
        title = _entry_title(first)
        word_sec: Dict[str, str] = {}
        for sid in sec_ids:
            for word in sections[sid].get("triggers") or []:
                word_sec.setdefault(str(word).strip(), sid)
        if title:
            word_sec.setdefault(title, sec_ids[0])
        # 标题里含角色正式名时(如"【WIKI】椿角色攻略"), 允许按角色名触发
        for char_name in chars:
            if char_name and char_name in title:
                word_sec.setdefault(char_name, sec_ids[0])
        for word, sid in word_sec.items():
            if not word or not _CJK.search(word) or word in BROAD_TRIGGERS:
                continue
            if len(word) < TRIGGER_MIN_LEN and word not in chars:
                continue
            triggers.append((word, entry_id, sid, prio))
    triggers.sort(key=lambda t: (-len(t[0]), -t[3]))
    _state = {"sections": sections, "entries": entry_secs, "triggers": triggers}
    return _state


def reload() -> int:
    global _state
    _state = None
    return len(_load()["sections"])


def get(kid: str) -> Optional[dict]:
    """小节 id → 小节记录; 条目 id → 全部小节拼装的整条。"""
    state = _load()
    if kid in state["sections"]:
        return {k: v for k, v in state["sections"][kid].items() if not k.startswith("_")}
    sec_ids = state["entries"].get(kid)
    if not sec_ids:
        return None
    first = state["sections"][sec_ids[0]]
    parts = []
    for sid in sec_ids:
        sec = state["sections"][sid]
        sec_name = str(sec.get("section_title") or "").strip() or str(sec.get("title") or "").rsplit("/", 1)[-1]
        parts.append(f"## {sec_name}\n{sec['content']}")
    return {
        "id": kid,
        "title": _entry_title(first),
        "tags": first.get("tags") or [],
        "source": first.get("source"),
        "sections": [
            {"id": sid, "title": state["sections"][sid].get("title")} for sid in sec_ids
        ],
        "content": "\n\n".join(parts),
    }


def lookup(text: str, exclude: Optional[Set[str]] = None,
           limit: int = LOOKUP_MAX_HITS) -> List[Dict[str, Any]]:
    """世界书触发: 在一段话里扫触发词, 长词优先, 注入声明该触发词的小节。

    exclude 是条目 id 集合; 已排除条目的同名条目一并跳过(多源同名词条只注入一次)。
    """
    text = (text or "").strip()
    if not text:
        return []
    exclude = exclude or set()
    state = _load()
    excluded_titles = set()
    for entry_id in exclude:
        sec_ids = state["entries"].get(entry_id)
        if sec_ids:
            excluded_titles.add(_entry_title(state["sections"][sec_ids[0]]))
    hits: List[Dict[str, Any]] = []
    seen_entries: Set[str] = set()
    taken_words: List[str] = []
    for word, entry_id, sec_id, _prio in state["triggers"]:
        if entry_id in exclude or entry_id in seen_entries or word not in text:
            continue
        sec = state["sections"][sec_id]
        if _entry_title(sec) in excluded_titles:
            continue
        if any(word in longer for longer in taken_words):
            continue
        content = sec["content"]
        if len(content) > INJECT_CONTENT_LEN:
            content = content[:INJECT_CONTENT_LEN] + f"…(截断, 整条 kb_get('{entry_id}'))"
        hits.append({"id": sec["id"], "entry": entry_id, "title": sec.get("title"),
                     "trigger": word, "tags": sec.get("tags") or [], "content": content})
        seen_entries.add(entry_id)
        taken_words.append(word)
        if len(hits) >= limit:
            break
    return hits


def _terms(q: str) -> List[str]:
    parts = [p for p in re.split(r"[\s,，、/]+", (q or "").strip()) if p]
    return parts or ([q.strip()] if q.strip() else [])


def search(q: str, source: Optional[str] = None, tags: Optional[List[str]] = None,
           limit: int = 5, full: bool = False) -> List[Dict[str, Any]]:
    """按小节词法检索: title/triggers/tags 命中权重高于 content, 多词全含加分。"""
    terms = _terms(q)
    if not terms:
        return []
    state = _load()
    want_tags = set(tags or [])
    scored: List[Tuple[float, dict]] = []
    for rec in state["sections"].values():
        if source and rec.get("_kind") != source:
            continue
        if want_tags and not (want_tags & set(rec.get("tags") or [])):
            continue
        title = str(rec.get("title") or "")
        trig = " ".join(rec.get("triggers") or [])
        tag_text = " ".join(rec.get("tags") or [])
        content = rec["content"]
        score = 0.0
        matched = 0
        for term in terms:
            hit = False
            if term == _entry_title(rec):
                score += 100; hit = True
            elif term in title:
                score += 30; hit = True
            if term in trig:
                score += 25; hit = True
            if term in tag_text:
                score += 15; hit = True
            occurrences = content.count(term)
            if occurrences:
                score += 5 * min(occurrences, 3); hit = True
            if hit:
                matched += 1
        if not matched:
            continue
        if matched == len(terms) and len(terms) > 1:
            score *= 1.5
        scored.append((score, rec))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, rec in scored[:limit]:
        item = {"id": rec["id"], "entry": rec.get("entry"), "title": rec.get("title"),
                "source": rec.get("source"), "kind": rec.get("_kind"),
                "tags": rec.get("tags") or [], "score": round(score, 1)}
        if full:
            item["content"] = rec["content"]
        else:
            pos = min((rec["content"].find(t) for t in terms
                       if rec["content"].find(t) >= 0), default=0)
            start = max(0, pos - 40)
            item["snippet"] = rec["content"][start:start + SNIPPET_LEN].replace("\n", " ")
        out.append(item)
    return out
