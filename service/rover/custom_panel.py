"""AI 自定义面板: 按传入 ctx 重组角色声骸后渲完整面板。

只渲染: 不写 players/、不进上传队列(总排行)、不改任何用户数据。
"""

import copy
from typing import Any, Dict, List, Optional, Tuple

from rover.bot import Bot
from rover.handler import build_message, msg_process
from rover.logger import logger
from rover.models import Message

VALID_COSTS = {1, 3, 4}
MAX_TOTAL_COST = 12


def _props(pairs: Any) -> List[Dict[str, Any]]:
    """[["攻击","18.0%"], ...] 或 [{"attributeName":...}] → Props 列表。"""
    out: List[Dict[str, Any]] = []
    for item in pairs or []:
        if isinstance(item, dict):
            name = item.get("attributeName") or item.get("name")
            value = item.get("attributeValue") or item.get("value")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            name, value = item[0], item[1]
        else:
            raise ValueError(f"词条格式不对: {item!r}")
        if not name or value is None:
            raise ValueError(f"词条缺名字或数值: {item!r}")
        out.append({"attributeName": str(name), "attributeValue": str(value)})
    return out


def _build_custom_echo(spec: Dict[str, Any]) -> Dict[str, Any]:
    from plugins.XutheringWavesUID.XutheringWavesUID.utils.name_convert import (
        alias_to_echo_name,
        alias_to_sonata_name,
        echo_name_to_echo_id,
    )

    raw_name = str(spec.get("name") or "").strip()
    if not raw_name:
        raise ValueError("自定义声骸缺 name")
    cost = int(spec.get("cost") or 0)
    if cost not in VALID_COSTS:
        raise ValueError(f"声骸 cost 只能是 1/3/4: {raw_name} cost={cost}")

    echo_name = alias_to_echo_name(raw_name) or raw_name
    echo_id = echo_name_to_echo_id(echo_name)
    sonata = alias_to_sonata_name(str(spec.get("sonata") or "")) or str(
        spec.get("sonata") or ""
    )
    quality = int(spec.get("quality") or 5)
    main = _props(spec.get("main"))
    subs = _props(spec.get("subs"))
    if not main:
        raise ValueError(f"声骸 {echo_name} 缺主词条 main")

    return {
        "phantomProp": {
            "phantomPropId": 0,
            "name": echo_name,
            "phantomId": int(echo_id) if echo_id else 0,
            "quality": quality,
            "cost": cost,
            "iconUrl": "",
            "skillDescription": "",
        },
        "cost": cost,
        "quality": quality,
        "level": int(spec.get("level") or 25),
        "fetterDetail": {"groupId": 0, "name": sonata, "num": int(spec.get("num") or 5)},
        "mainProps": main,
        "subProps": subs,
    }


async def _ref_echo(uid: str, ref: Dict[str, Any]):
    """{"char": "洛可可", "slot": 2, "uid": 可选} → 那个角色身上装着的那件。"""
    from plugins.XutheringWavesUID.XutheringWavesUID.utils.char_info_utils import (
        get_char_detail_for_id,
    )
    from plugins.XutheringWavesUID.XutheringWavesUID.utils.name_convert import (
        alias_to_char_name,
        char_name_to_char_id,
    )

    char = str(ref.get("char") or "").strip()
    slot = int(ref.get("slot") or 0)
    if not char or slot < 1 or slot > 5:
        raise ValueError(f"引用格式不对(需要 char + slot 1-5): {ref!r}")
    char_name = alias_to_char_name(char)
    char_id = char_name_to_char_id(char_name)
    if not char_id:
        raise ValueError(f"引用的角色不认识: {char}")
    detail = await get_char_detail_for_id(str(ref.get("uid") or uid), char_id)
    if detail is None:
        raise ValueError(f"{char_name} 没有本地面板数据, 先 ww刷新{char_name}面板")
    lst = detail.phantomData.equipPhantomList if detail.phantomData else None
    echo = lst[slot - 1] if lst and len(lst) >= slot else None
    if echo is None:
        raise ValueError(f"{char_name} 的 {slot} 号位没有声骸")
    return copy.deepcopy(echo)


async def _apply_echoes(uid: str, role_detail, echoes: List[Dict[str, Any]]) -> None:
    from plugins.XutheringWavesUID.XutheringWavesUID.utils.api.model import (
        EquipPhantom,
        EquipPhantomData,
    )

    if role_detail.phantomData is None:
        role_detail.phantomData = EquipPhantomData(cost=0, equipPhantomList=None)
    current = list(role_detail.phantomData.equipPhantomList or [None] * 5)
    while len(current) < 5:
        current.append(None)

    for i, spec in enumerate(echoes):
        if not isinstance(spec, dict):
            raise ValueError(f"声骸项要是对象: {spec!r}")
        slot = int(spec.get("slot") or i + 1)
        if slot < 1 or slot > 5:
            raise ValueError(f"slot 只能是 1-5: {slot}")
        if spec.get("from"):
            current[slot - 1] = await _ref_echo(uid, spec["from"])
        else:
            current[slot - 1] = EquipPhantom(**_build_custom_echo(spec))

    total = sum(e.cost for e in current if e)
    if total > MAX_TOTAL_COST:
        raise ValueError(f"总 cost {total} 超过 {MAX_TOTAL_COST}, 检查各件 cost")
    role_detail.phantomData.cost = total
    role_detail.phantomData.equipPhantomList = current


async def render_custom_panel(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], List[Message]]:
    """(错误文案, 消息段)。成功时错误为 None。"""
    from plugins.XutheringWavesUID.XutheringWavesUID.utils.char_info_utils import (
        get_char_detail_for_id,
    )
    from plugins.XutheringWavesUID.XutheringWavesUID.utils.database.models import (
        WavesBind,
    )
    from plugins.XutheringWavesUID.XutheringWavesUID.utils.name_convert import (
        alias_to_char_name,
        char_name_to_char_id,
    )
    from plugins.XutheringWavesUID.XutheringWavesUID.wutheringwaves_charinfo.draw_char_card import (
        draw_char_detail_img,
    )

    char = str(payload.get("char") or "").strip()
    if not char:
        return "缺角色名 char", []
    char_name = alias_to_char_name(char)
    char_id = char_name_to_char_id(char_name)
    if not char_id or len(char_id) != 4 or not char_id.isdigit():
        return f"未找到角色: {char}", []

    from rover.config import core_config

    masters = core_config.get_config("masters") or []
    default_user = str(masters[0]) if masters else "dsh-user"
    ev = msg_process(build_message(f"{char_name}面板", user_id=default_user))
    ev.user_pm = 0

    uid = str(payload.get("uid") or "").strip()
    if not uid:
        uid = await WavesBind.get_uid_by_game(ev.user_id, ev.bot_id) or ""
    if not uid:
        return "没有可用 UID: 传 uid, 或先 ww绑定<特征码>", []

    base = await get_char_detail_for_id(uid, char_id)
    if base is None:
        return f"{char_name} 没有本地面板数据, 先跑一次 ww刷新{char_name}面板", []
    role_detail = copy.deepcopy(base)

    echoes = payload.get("echoes")
    if echoes:
        if not isinstance(echoes, list):
            return "echoes 要是数组", []
        try:
            await _apply_echoes(uid, role_detail, echoes)
        except ValueError as e:
            return str(e), []

    change = str(payload.get("change") or "").strip() or None

    bot = Bot(ev)
    try:
        im = await draw_char_detail_img(
            ev,
            uid,
            char_name,
            ev.user_id,
            change_list_regex=change,
            role_detail_override=role_detail,
        )
        # 账号上下文取不到时降级为无账号渲染
        if isinstance(im, str) and not change:
            im2 = await draw_char_detail_img(
                ev,
                uid,
                char_name,
                ev.user_id,
                is_limit_query=True,
                role_detail_override=role_detail,
            )
            if not isinstance(im2, str):
                im = im2
    except Exception as e:
        logger.exception(f"[自定义面板] 渲染失败 {char_name}: {e}")
        return f"渲染失败: {e}", []
    if isinstance(im, str):
        return im, []
    await bot.send(im)
    return None, bot.sink
