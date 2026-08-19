#!/usr/bin/env python3
"""只读数据访问 + 评分计算, 给脚本用。

用法:
    import sys; sys.path.insert(0, "<service>/tools")
    import wwdata as w
    w.uids()                     # 有数据的特征码
    w.roles(uid)                 # 角色一览(等级/命座/武器/声骸分)
    w.echoes(uid, sonata="沉日劫明")   # 按套装筛已装备声骸
    w.score(uid, "洛可可", echo)  # 把某个声骸放到某角色的评分模板下打分

写入一律只允许落在 SCRATCH 里, 本模块不提供任何改用户数据的接口。
命令行自检: python tools/wwdata.py
"""

import gzip
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

SERVICE = Path(__file__).resolve().parents[1]
DATA = SERVICE / "data"
WW = DATA / "XutheringWavesUID"
PLAYERS = WW / "players"
MAP = WW / "resource" / "map"
DB = DATA / "WavesData.db"
# 模拟数据、中间结果、脚本产物都写这里。放系统临时目录: 沙箱只放行临时目录和工作区,
# data 在两者之外写不进去; tempfile 跟随 TMPDIR/TEMP, Windows 下同样有效。
SCRATCH = Path(os.environ.get("WW_SCRATCH") or tempfile.gettempdir()) / "dsh-waves-scratch"

_booted = False
_cache: Dict[str, Any] = {}


# ── 基础读取 ────────────────────────────────────────────────────────────


def _json(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as file:
            return json.load(file)
    return json.loads(path.read_text("utf-8"))


def scratch(*parts: str) -> Path:
    """唯一可写目录, 返回其中的路径并建好父目录。"""
    path = SCRATCH.joinpath(*parts) if parts else SCRATCH
    (path.parent if parts else path).mkdir(parents=True, exist_ok=True)
    return path


def uids() -> List[str]:
    """本地有面板数据的特征码。"""
    if not PLAYERS.is_dir():
        return []
    return sorted(p.name for p in PLAYERS.iterdir() if p.is_dir() and (p / "rawData.json.gz").is_file())


def bound_uids() -> List[str]:
    """数据库里绑定过的特征码, 按绑定顺序; 第一个就是当前默认账号。"""
    if not DB.is_file():
        return []
    conn = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
    try:
        out: List[str] = []
        for (cell,) in conn.execute("SELECT uid FROM wavesbind WHERE uid IS NOT NULL"):
            for one in str(cell).split("_"):
                if one and one not in out:
                    out.append(one)
        return out
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def default_uid() -> str:
    found = bound_uids() or uids()
    if not found:
        raise RuntimeError("本地没有任何特征码数据, 先跑一次 ww查询 / ww刷新面板")
    return found[0]


def player_file(uid: str, name: str) -> Optional[Path]:
    path = PLAYERS / str(uid) / name
    return path if path.is_file() else None


def base_info(uid: str) -> dict:
    path = player_file(uid, "baseInfo.json")
    return _json(path) if path else {}


def raw_panel(uid: str) -> List[dict]:
    """rawData.json.gz 原样返回: 每项是一个角色的完整面板。"""
    path = player_file(uid, "rawData.json.gz")
    return _json(path) if path else []


def matrix(uid: str) -> dict:
    """终焉矩阵挑战结果。"""
    path = player_file(uid, "matrixData.json.gz")
    return _json(path) if path else {}


def slash(uid: str) -> dict:
    """冥歌海墟挑战结果。"""
    path = player_file(uid, "slashData.json.gz")
    return _json(path) if path else {}


def abyss(uid: str) -> dict:
    """深境区(深塔)挑战结果。"""
    path = player_file(uid, "rover.json.gz")
    return _json(path) if path else {}


def gacha(uid: str) -> dict:
    path = player_file(uid, "gacha_logs.json.gz")
    return {"logs": _json(path) if path else None, "stats": gacha_stats(uid)}


def gacha_stats(uid: str) -> dict:
    path = player_file(uid, "gachaStats.json")
    return _json(path) if path else {}


def char_scores(uid: str) -> Dict[str, float]:
    """角色 id → 声骸总分, 练度统计用的就是它。"""
    path = player_file(uid, "charListData.json")
    return _json(path) if path else {}


# ── 名字与别名 ──────────────────────────────────────────────────────────


def id2name() -> Dict[str, str]:
    if "id2name" not in _cache:
        data = _json(MAP / "CharId2Data.json")
        _cache["id2name"] = {k: v.get("name", "") for k, v in data.items()}
    return _cache["id2name"]


def name(char_id: Any) -> str:
    return id2name().get(str(char_id), str(char_id))


def _alias_map(file_name: str) -> Dict[str, str]:
    """别名 → 正式名。直接读别名表, 不依赖插件那套 import。"""
    key = f"alias:{file_name}"
    if key in _cache:
        return _cache[key]
    table: Dict[str, str] = {}
    path = WW / "alias" / file_name
    if path.is_file():
        for canonical, aliases in _json(path).items():
            table[str(canonical).lower()] = canonical
            for alias in aliases if isinstance(aliases, list) else [aliases]:
                table[str(alias).lower()] = canonical
    _cache[key] = table
    return table


def resolve(text: str) -> Optional[str]:
    """别名/简称 → 角色正式名。要精确匹配时用它, 别自己猜。"""
    found = _alias_map("char_alias.json").get(str(text).strip().lower())
    if found:
        return found
    try:
        convert = _mod("utils.name_convert")
    except Exception:
        return None
    resolved = convert.alias_to_char_name(text)
    return resolved if convert.is_valid_char_name(resolved) else None


def resolve_sonata(text: str) -> str:
    """别名/简称 → 套装正式名, 认不出就原样返回。"""
    found = _alias_map("sonata_alias.json").get(str(text).strip().lower())
    if found:
        return found
    try:
        return _mod("utils.name_convert").alias_to_sonata_name(text) or text
    except Exception:
        return text


def char_id(text: str) -> Optional[str]:
    return _mod("utils.name_convert").char_name_to_char_id(resolve(text) or text)


# ── 角色与声骸视图 ──────────────────────────────────────────────────────


def roles(uid: str) -> List[dict]:
    """角色一览。练度不一时先看 level / chain / weapon.reson / echo_score。"""
    scores = char_scores(uid)
    out = []
    for item in raw_panel(uid):
        role = item.get("role") or {}
        weapon = (item.get("weaponData") or {}).get("weapon") or {}
        chains = item.get("chainList") or []
        out.append(
            {
                "id": str(role.get("roleId", "")),
                "name": role.get("roleName", ""),
                "level": item.get("level") or role.get("level"),
                "attribute": role.get("attributeName", ""),
                "chain": sum(1 for c in chains if c.get("unlocked")),
                "weapon": {
                    "name": weapon.get("weaponName", ""),
                    "level": (item.get("weaponData") or {}).get("level"),
                    "reson": (item.get("weaponData") or {}).get("resonLevel"),
                },
                "skills": {s["skill"]["type"]: s["level"] for s in item.get("skillList") or [] if s.get("skill")},
                "echo_score": scores.get(str(role.get("roleId", "")), 0),
                "sonatas": sonatas_of(item),
            }
        )
    out.sort(key=lambda r: (-(r["echo_score"] or 0), r["name"]))
    return out


def roster(uid: str, limit: int = 0) -> List[str]:
    """持有角色的紧凑一行式, 只想知道"有谁、练到什么程度"时用它, 别拉整份 roles()。

    例: 卡提希娅 Lv90 0链 时和裂片5阶 声骸165.4
    """
    out = []
    for role in roles(uid):
        weapon = role["weapon"]
        out.append(
            f"{role['name']} Lv{role['level']} {role['chain']}链 "
            f"{weapon['name']}{weapon['reson']}阶 声骸{role['echo_score']:.1f}"
        )
    return out[:limit] if limit else out


def sonatas_of(panel_item: dict) -> Dict[str, int]:
    """一个角色身上各套装的件数。"""
    counts: Dict[str, int] = {}
    for echo in (panel_item.get("phantomData") or {}).get("equipPhantomList") or []:
        if not echo:
            continue
        key = (echo.get("fetterDetail") or {}).get("name") or ""
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def echoes(uid: str, sonata: Optional[str] = None, char: Optional[str] = None) -> List[dict]:
    """已装备声骸拉平成一张表, 可按套装名或角色名筛。

    每项: owner / owner_id / slot / cost / level / sonata / echo(声骸名) /
    main(主词条) / subs(副词条) / raw(原始 dict, 传给 score 用)
    """
    want = resolve_sonata(sonata) if sonata else None
    want_char = resolve(char) if char else None
    out = []
    for item in raw_panel(uid):
        role = item.get("role") or {}
        owner = role.get("roleName", "")
        if want_char and owner != want_char:
            continue
        for slot, echo in enumerate((item.get("phantomData") or {}).get("equipPhantomList") or []):
            if not echo:
                continue
            fetter = (echo.get("fetterDetail") or {}).get("name") or ""
            if want and fetter != want and (sonata or "") not in fetter:
                continue
            mains = echo.get("mainProps") or []
            out.append(
                {
                    "owner": owner,
                    "owner_id": str(role.get("roleId", "")),
                    "slot": slot,
                    "cost": echo.get("cost"),
                    "level": echo.get("level"),
                    "sonata": fetter,
                    "echo": (echo.get("phantomProp") or {}).get("name", ""),
                    "main": [(p.get("attributeName"), p.get("attributeValue")) for p in mains],
                    "subs": [(p.get("attributeName"), p.get("attributeValue")) for p in echo.get("subProps") or []],
                    "raw": echo,
                }
            )
    return out


def sonata_pool(uid: str, sonata: str) -> Dict[str, List[dict]]:
    """同一套装的声骸按当前佩戴者归拢, 换装推演的输入。"""
    pool: Dict[str, List[dict]] = {}
    for echo in echoes(uid, sonata=sonata):
        pool.setdefault(echo["owner"], []).append(echo)
    return pool


def matrix_summary(uid: str) -> dict:
    """矩阵战绩摘要: 每层用了谁、打过几个 boss、分数。角色 id 已换成名字。"""
    data = matrix(uid)
    detail = data.get("matrix_data") or {}
    modes = []
    for mode in detail.get("modeDetails") or []:
        teams = []
        for team in mode.get("teams") or []:
            teams.append(
                {
                    "roles": [name(r.get("roleId")) for r in team.get("roleList") or []],
                    "pass_boss": team.get("passBoss"),
                    "boss_count": team.get("bossCount"),
                    "buffs": [b.get("buffName") for b in team.get("buffs") or []],
                }
            )
        modes.append(
            {
                "mode_id": mode.get("modeId"),
                "rank": mode.get("rank"),
                "score": mode.get("score"),
                "pass_boss": mode.get("passBoss"),
                "boss_count": mode.get("bossCount"),
                "round": mode.get("round"),
                "teams": teams,
            }
        )
    return {
        "record_time": data.get("record_time"),
        "reward": detail.get("reward"),
        "total_reward": detail.get("totalReward"),
        "modes": modes,
        # "模式_层": [角色id] —— 各层实际匹配到的阵容
        "stage_roles": {
            k: [name(i) for i in v] for k, v in (data.get("matched_char_ids") or {}).items()
        },
    }


def cross_scores(uid: str, sonata: str, chars: Optional[List[str]] = None) -> List[dict]:
    """同套装每件声骸, 在每个候选角色模板下各打一次分。

    换装推演的原始证据: 看某件在别人模板下是不是明显更高。
    chars 不给就用这套装当前的佩戴者。
    """
    pool = sonata_pool(uid, sonata)
    targets = [resolve(c) or c for c in chars] if chars else list(pool)
    out = []
    for owner, items in pool.items():
        for echo in items:
            row = {t: score(uid, t, echo)["score"] for t in targets}
            best = max(row, key=row.get) if row else ""
            out.append(
                {
                    "owner": owner,
                    "echo": echo["echo"],
                    "cost": echo["cost"],
                    "slot": echo["slot"],
                    "main": echo["main"],
                    "scores": row,
                    "best_for": best,
                    "gain_vs_owner": round(row.get(best, 0) - row.get(owner, 0), 2) if best else 0,
                }
            )
    out.sort(key=lambda x: -x["gain_vs_owner"])
    return out


def swap_gains(uid: str, sonata: str, min_gain: float = 0.01) -> List[dict]:
    """同套装跨角色两两互换, 列出总分有净增益的换法(按增益排序)。

    只换 cost 相同的件, 因此总 cost 不变(仍在 12 以内); 同一角色身上同名声骸不能重复,
    会撞名的换法直接排除。分数是各自角色评分模板下的声骸分, 不含伤害模拟。
    """
    pool = sonata_pool(uid, sonata)
    owners = list(pool)
    cache: Dict[tuple, float] = {}
    equipped = {
        role["name"]: {
            (e.get("phantomProp") or {}).get("name", "")
            for e in (next(
                (i for i in raw_panel(uid) if (i.get("role") or {}).get("roleName") == role["name"]),
                {},
            ).get("phantomData") or {}).get("equipPhantomList") or []
            if e
        }
        for role in roles(uid)
    }

    def clashes(char: str, incoming: dict, outgoing: dict) -> bool:
        """换进来的声骸和这角色身上留着的重名就不行。"""
        keep = equipped.get(char, set()) - {outgoing["echo"]}
        return incoming["echo"] in keep

    def one(char: str, echo: dict) -> float:
        key = (char, echo["owner"], echo["slot"])
        if key not in cache:
            cache[key] = score(uid, char, echo)["score"]
        return cache[key]

    out = []
    for i, a in enumerate(owners):
        for b in owners[i + 1 :]:
            for ea in pool[a]:
                for eb in pool[b]:
                    if ea["cost"] != eb["cost"]:
                        continue
                    if clashes(a, eb, ea) or clashes(b, ea, eb):
                        continue
                    now = one(a, ea) + one(b, eb)
                    after = one(a, eb) + one(b, ea)
                    if after - now > min_gain:
                        out.append(
                            {
                                "gain": round(after - now, 2),
                                "from": {"char": a, "echo": ea["echo"], "cost": ea["cost"], "slot": ea["slot"]},
                                "to": {"char": b, "echo": eb["echo"], "cost": eb["cost"], "slot": eb["slot"]},
                                "before": round(now, 2),
                                "after": round(after, 2),
                            }
                        )
    out.sort(key=lambda x: -x["gain"])
    return out


# ── 评分 ────────────────────────────────────────────────────────────────


PKG = "plugins.XutheringWavesUID.XutheringWavesUID"


def boot() -> None:
    """装好 import 兼容层, 之后就能 import 插件里的模块。"""
    global _booted
    if _booted:
        return
    if str(SERVICE) not in sys.path:
        sys.path.insert(0, str(SERVICE))
    from rover import compat

    compat.install([str(SERVICE / "plugins")])
    _booted = True


def _mod(suffix: str):
    """按需取插件内的模块, 例 _mod("utils.name_convert")。"""
    import importlib

    boot()
    try:
        return importlib.import_module(f"{PKG}.{suffix}")
    except ImportError as e:
        py = SERVICE / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
            "python.exe" if os.name == "nt" else "python"
        )
        raise RuntimeError(
            f"载入插件模块 {suffix} 失败({e})。评分相关接口要用服务自己的解释器跑: {py}"
        ) from e


def _role_detail(uid: str, char: str):
    RoleDetailData = _mod("utils.api.model").RoleDetailData

    want = resolve(char) or char
    for item in raw_panel(uid):
        if (item.get("role") or {}).get("roleName") == want:
            return RoleDetailData.model_validate(item)
    raise LookupError(f"{uid} 没有 {want} 的面板数据, 先跑 ww刷新面板")


def calc_temp(uid: str, char: str) -> dict:
    """某角色当前的评分模板(词条权重), 换装推演按它算分。"""
    key = f"temp:{uid}:{char}"
    if key in _cache:
        return _cache[key]
    WuWaCalc = _mod("utils.calc").WuWaCalc
    get_calc_map = _mod("utils.calculate").get_calc_map

    detail = _role_detail(uid, char)
    calc = WuWaCalc(detail)
    calc.phantom_pre = calc.prepare_phantom()
    calc.phantom_card = calc.enhance_summation_phantom_value(calc.phantom_pre)
    temp = get_calc_map(calc.phantom_card, detail.role.roleName, detail.role.roleId)
    _cache[key] = {"temp": temp, "role_id": detail.role.roleId, "name": temp.get("name", "")}
    return _cache[key]


def score(uid: str, char: str, echo: Any) -> dict:
    """把一个声骸放到 char 的评分模板下打分。

    echo 可以是 echoes() 的一项、它的 raw、或 make_echo() 造的字典。
    返回 {score, grade, template, char}
    """
    EquipPhantom = _mod("utils.api.model").EquipPhantom
    calc_phantom_score = _mod("utils.calculate").calc_phantom_score

    payload = echo.get("raw", echo) if isinstance(echo, dict) else echo
    model = payload if isinstance(payload, EquipPhantom) else EquipPhantom.model_validate(payload)
    ctx = calc_temp(uid, char)
    value, grade = calc_phantom_score(ctx["role_id"], model.get_props(), model.cost, ctx["temp"])
    return {
        "score": round(float(value), 2),
        "grade": grade,
        "template": ctx["name"],
        "char": resolve(char) or char,
    }


def total_score(uid: str, char: str, echo_list: List[Any]) -> float:
    """一整套(通常 5 件)在某角色模板下的总分。"""
    return round(sum(score(uid, char, e)["score"] for e in echo_list), 2)


def make_echo(cost: int, sonata: str, echo_name: str, main: list, subs: list, level: int = 25) -> dict:
    """按截图/文本转录出来的声骸, 造成可以打分的形状。

    main / subs 是 [(词条名, 值字符串)], 值带 % 就照抄, 例: ("暴击伤害", "21.0%")
    """
    def props(pairs):
        return [{"attributeName": str(n), "attributeValue": str(v)} for n, v in pairs]

    return {
        "phantomProp": {"phantomId": 0, "name": echo_name, "quality": 5, "cost": cost, "iconUrl": ""},
        "cost": int(cost),
        "quality": 5,
        "level": int(level),
        "fetterDetail": {"groupId": 0, "name": sonata, "num": 5},
        "mainProps": props(main),
        "subProps": props(subs),
    }


# ── 自检 ────────────────────────────────────────────────────────────────


def _selftest() -> None:
    uid = default_uid()
    info = base_info(uid)
    print(f"uid={uid} {info.get('name','')} Lv.{info.get('level','')} 角色={len(raw_panel(uid))}")
    print("练度前三:", roster(uid, 3))
    pool = sonata_pool(uid, "沉日劫明")
    print("沉日劫明持有者:", {k: len(v) for k, v in pool.items()})
    if pool:
        owner = next(iter(pool))
        echo = pool[owner][0]
        print(f"样例声骸 {echo['echo']}({echo['cost']}c) 现属 {owner}:", score(uid, owner, echo))
    print("矩阵:", "有" if matrix(uid) else "无", "| 深塔:", "有" if abyss(uid) else "无")
    print("别名: 洛可可 ->", resolve("洛可可"), "| 千咲 ->", resolve("千咲"))


if __name__ == "__main__":
    _selftest()
