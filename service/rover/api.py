"""对外接口。前端与 dsh 侧都经这里下命令、取媒体与通知。"""

import base64
import binascii
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from msgspec import to_builtins
from pydantic import BaseModel

from rover.api_render import render_segments, summarize
from rover.app_life import app
from rover.config import CONFIG_DEFAULT, core_config
from rover.handler import build_message, dispatch, normalize_command
from rover.logger import logger
from rover.media import cleanup_media, media_path, render_png

DEFAULT_GROUP = "dsh"


def _default_user() -> str:
    masters = core_config.get_config("masters") or []
    return str(masters[0]) if masters else "dsh-user"


def _local_image_url(image: str) -> str:
    """插件按 URL 取图, 上传来的 base64 先落盘再给回本机地址。"""
    if not image.startswith("base64://"):
        return image
    import base64

    from rover.api_render import _guess_ext
    from rover.media import save_media

    raw = base64.b64decode(image[len("base64://") :])
    name = save_media(raw, _guess_ext(raw))
    host = core_config.get_config("HOST") or "127.0.0.1"
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    return f"http://{host}:{core_config.get_config('PORT')}/api/media/{name}"


class ChatRequest(BaseModel):
    command: str
    scene: str = "group"
    session_id: str = "dsh"
    user_id: Optional[str] = None
    images: Optional[List[str]] = None
    file_name: Optional[str] = None
    file_data: Optional[str] = None


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    from rover.sv import SL

    from rover.sv import all_prefixes

    return {
        "ok": True,
        "plugins": list(SL.plugins.keys()),
        "commands": sum(len(t) for sv in SL.lst.values() for t in sv.TL.values()),
        "prefixes": all_prefixes(),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest) -> Dict[str, Any]:
    command = normalize_command(req.command.strip())
    if not command:
        raise HTTPException(status_code=400, detail="命令为空")

    user_id = req.user_id or _default_user()
    user_type = "direct" if req.scene == "direct" else "group"
    message = build_message(
        command,
        user_id=user_id,
        group_id=DEFAULT_GROUP,
        user_type=user_type,
        images=[_local_image_url(i) for i in (req.images or [])],
        file_name=req.file_name,
        file_data=req.file_data,
    )
    logger.info(f"[命令] {command} (scene={user_type})")
    result = await dispatch(message)
    rendered = await render_segments(result["segments"])

    if result["unmatched"]:
        return {
            "ok": False,
            "summary": f"未匹配到命令: {command}。可用 ww帮助 查看全部命令。",
            "matched": [],
            "segments": [],
            "elapsed": result["elapsed"],
        }

    return {
        "ok": True,
        "summary": summarize(rendered) or "已执行",
        "matched": result["matched"],
        "segments": rendered,
        "elapsed": round(result["elapsed"], 3),
    }


@app.get("/api/config/media")
async def media_config() -> Dict[str, Any]:
    """前端渲染要用的少量取值, 单独给一个轻接口。"""
    return {
        "image_portrait_max_percent": core_config.get_config("image_portrait_max_percent") or 50,
        "image_landscape_max_percent": core_config.get_config("image_landscape_max_percent") or 75,
    }


_ALIAS_INDEX: Optional[List[tuple]] = None
# 单字别名(角/春)误命中太多; 只认两字起
ALIAS_MIN_LEN = 2
ALIAS_MAX_HITS = 8
_CJK = re.compile(r"[一-鿿]")


def _worth_matching(alias: str) -> bool:
    """纯英文/拼音缩写(bl、sh、cl)在正常英文里到处都是, 子串扫必然误报, 一律不收。"""
    return bool(_CJK.search(alias))


def _alias_index() -> List[tuple]:
    """(别名, 类别, 正式名) 一张表, 按别名长度倒序, 长的先命中。"""
    global _ALIAS_INDEX
    if _ALIAS_INDEX is not None:
        return _ALIAS_INDEX
    from rover.data_store import data_path

    kinds = {
        "char_alias.json": "角色",
        "sonata_alias.json": "套装",
        "echo_alias.json": "声骸",
        "weapon_alias.json": "武器",
    }
    entries: List[tuple] = []
    root = data_path / "XutheringWavesUID" / "alias"
    for file_name, kind in kinds.items():
        path = root / file_name
        if not path.is_file():
            continue
        try:
            table = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for canonical, aliases in table.items():
            for alias in aliases if isinstance(aliases, list) else [aliases]:
                alias = str(alias)
                if len(alias) < ALIAS_MIN_LEN or alias == canonical:
                    continue
                if not _worth_matching(alias):
                    continue
                entries.append((alias, kind, canonical))
    entries.sort(key=lambda e: -len(e[0]))
    _ALIAS_INDEX = entries
    return entries


@app.get("/api/alias/lookup")
async def alias_lookup(text: str = "") -> Dict[str, Any]:
    """在一段话里找本地别名。只报命中, 不做判断, 调用方自己决定信不信。"""
    lowered = (text or "").lower()
    if not lowered:
        return {"hits": []}
    hits: List[Dict[str, str]] = []
    seen_canonical = set()
    taken: List[str] = []
    for alias, kind, canonical in _alias_index():
        if canonical in seen_canonical or alias.lower() not in lowered:
            continue
        # 正式名已经在原话里了, 再报一遍别名是废话
        if canonical.lower() in lowered:
            continue
        # 已命中的更长别名包含了它, 就不再重复报
        if any(alias in longer for longer in taken):
            continue
        taken.append(alias)
        seen_canonical.add(canonical)
        hits.append({"alias": alias, "kind": kind, "name": canonical})
        if len(hits) >= ALIAS_MAX_HITS:
            break
    return {"hits": hits}


@app.get("/api/media/{name}/png")
async def media_png(name: str):
    """HTML 卡片的截图版, 按原始设计宽度渲染, 供前端"保存"按钮下载。"""
    try:
        path = await render_png(name)
    except Exception as e:
        logger.warning(f"[媒体] 截图失败 {name}: {e}")
        raise HTTPException(status_code=500, detail=f"截图失败: {e}")
    if path is None:
        raise HTTPException(status_code=404, detail="卡片不存在或不是 HTML")
    return FileResponse(path, media_type="image/png", filename=path.name)


@app.get("/api/media/{name}")
async def media(name: str):
    path = media_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="媒体不存在")
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    headers = {"Cache-Control": "public, max-age=3600"}
    if name.endswith(".html"):
        headers["Content-Security-Policy"] = "sandbox allow-scripts allow-same-origin"
    return FileResponse(path, media_type=media_type, headers=headers)


@app.get("/api/commands")
async def commands() -> Dict[str, Any]:
    from rover.sv import AI_COMMANDS, SL

    out = []
    for sv in SL.lst.values():
        for ttype, triggers in sv.TL.items():
            for key, trigger in triggers.items():
                out.append({"sv": sv.name, "type": ttype, "trigger": key, "block": trigger.block})
    return {"total": len(out), "commands": out, "ai": AI_COMMANDS}


@app.get("/api/status")
async def status() -> Dict[str, Any]:
    from rover.status.plugin_status import plugins_status

    data: Dict[str, Any] = {}
    for plugin_name, items in plugins_status.items():
        # register_status 存的是 {icon: PIL.Image, status: {标签: 协程}}
        # icon 不能进 JSON, 只跑指标函数
        metrics: Dict[str, Any] = {}
        raw = (items or {}).get("status") or {}
        if not isinstance(raw, dict):
            raw = {}
        for label, func in raw.items():
            try:
                value = await func() if callable(func) else func
            except Exception as e:
                value = f"错误: {e}"
            metrics[str(label)] = value
        data[plugin_name] = metrics
    return {"status": data}


@app.post("/api/cleanup")
async def cleanup() -> Dict[str, Any]:
    return {"removed": cleanup_media()}


CORE_GROUP = "服务配置"

# 服务自身配置没有 UI 元数据, 这里补类型与文案
CORE_META: Dict[str, tuple] = {
    "expose_to_model": ("BoolConfig", "AI 可使用鸣潮插件", "作为工具暴露给模型, 占少量额外上下文; 只用 /ww 命令时可关闭省上下文"),
    "avatar": ("StrConfig", "头像", "卡片头部的头像: 直接上传图片, 或填 http(s) 链接 / QQ 号 / 本地路径; 置空用插件自带的"),
    "HOST": ("StrConfig", "监听地址", "服务绑定的地址"),
    "PORT": ("StrConfig", "监听端口", "服务监听的端口"),
    "command_prefix": ("StrConfig", "命令前缀", "多个用逗号分隔; 置空则不需要前缀"),
    "image_portrait_max_percent": ("IntConfig", "竖图最大宽度(%)", "高大于宽的图片, 最多占会话区宽度的百分比"),
    "image_landscape_max_percent": ("IntConfig", "横图最大宽度(%)", "宽大于高的图片, 最多占会话区宽度的百分比"),
    "media_max_mb": ("IntConfig", "产物目录上限(MB)", "超出时按最旧优先淘汰, 0 表示不限"),
    "log_level": ("StrConfig", "日志级别", "日志同时写终端和 data/logs, 文件按 2MB 滚动、最多留 4 个"),
    "sv": ("DictConfig", "功能项覆盖", '如 {"功能名": {"enabled": false, "pm": 0}}'),
}

# 有固定取值的服务配置
CORE_OPTIONS: Dict[str, List] = {
    "log_level": ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"],
}

# 改了要重启才生效的服务配置
CORE_RESTART_KEYS = {"expose_to_model", "HOST", "PORT", "log_level"}

# 值是文件路径、设置页给上传入口的服务配置
CORE_UPLOAD_KEYS = {"avatar"}

# 有效但不适合放设置页的内部项(身份归属/超时细节/原始 JSON 覆盖)
CORE_HIDDEN = {"masters", "misfire_grace_time", "command_timeout", "sv", "seeded"}

# 整组隐藏: 本插件只用 SQLite, 数据库连接参数没有调整意义
HIDDEN_GROUPS = {"数据库配置"}

# 各插件里在本地场景无效/已被运行时接管的键, 不进设置页
PLUGIN_HIDDEN = {
    "XutheringWavesUID": {
        # 群排行已裁, 这些只被死路径读
        "WavesRankUseTokenGroup", "WavesRankNoLimitGroup", "RankUseToken",
        "GachaRankMin", "QQPicCache", "RankActiveFilterGroup",
        # 聊天平台语义, 浏览器里无意义
        "WavesTencentWord", "WavesQRLogin", "WavesLoginForward", "AtCheck",
        "WavesOnlySelfCk", "MaxBindNum", "WavesLoginUrlSelf",
        # 单用户无需请求限速
        "RefreshInterval", "RefreshSingleCharInterval",
        "RefreshIntervalNotify", "RefreshSingleCharIntervalNotify",
        "UseGlobalSemaphore",
        # 被运行时接管或强制
        "UseHtmlRender", "RemoteRenderEnable", "RemoteRenderUrl", "FontCssUrl",
        "HelpExtraModules",
        "ActiveUserDays", "AnnActiveGroupDays", "WavesAnnOpen",
        # 公告订阅已裁, 这两项只被公告推送读
        "WavesAnnBBSSub", "AnnMinuteCheck",
        # 上传审核已裁 / 上游注明暂无用
        "WavesUploadAudit", "WavesUploadAuditKeepLocal",
        "CaptchaProvider", "CaptchaAppKey", "WavesPanelEditGuestView",
    },
    "鸣潮展示配置": {
        # 与同名上传项重复: 页面模板一律走上传, 不再手填路径
        "LoginIndexHtmlPath", "LoginIndexEmailHtmlPath", "LoginIndexCloudHtmlPath",
        "LoginIndexTokenHtmlPath", "Login404HtmlPath",
        # 帮助已改为自绘 HTML, 列数不再生效
        "HelpColumn",
    },
    "RoverSign": {
        # 活跃筛选在本地无意义, 启动时固定关闭
        "ActiveUserDays", "SignActiveUserOnly", "SigninMasterSkipInactive",
        # 与查询侧同名重复, 由运行时统一读查询侧的值
        "KuroUrlProxyUrl", "LocalProxyUrl", "NeedProxyFunc", "HideUid",
        # 推送报告在本地无收发对象
        "PrivateSignReport", "GroupSignReport", "GroupSignReportPic",
    },
    "ScoreEcho": {
        # 与总排行同一个 token, 由运行时直接复用
        "xwtoken",
        # 别名文件内部路径
        "localalias",
    },
}

SECRET_KEY_RE = re.compile(r"token|password|passwd|secret|cookie|api_?key|密码|密钥", re.I)
# 形如 scheme://user:pass@host 的带账密代理地址
CREDENTIAL_URL_RE = re.compile(r"^\w+://[^/\s:@]+:[^/\s@]+@")
# 文件路径不是敏感值, 名字里带 token 也不打码
PATH_RE = re.compile(r"^(/|\./|\.\./|~|[A-Za-z]:[\\/])")


class ConfigSetRequest(BaseModel):
    group: str
    key: str
    value: Any = None


def _is_secret(key: str, title: str, flag: bool, value: Any) -> bool:
    """配置项自带 secret 标记, 或名字/值看着像凭据(开关与列表不算)。"""
    if flag:
        return True
    if not isinstance(value, str) or PATH_RE.match(value):
        return False
    if SECRET_KEY_RE.search(key) or SECRET_KEY_RE.search(title):
        return True
    return bool(CREDENTIAL_URL_RE.match(value))


def _mask(value: Any) -> str:
    if isinstance(value, str) and value:
        return f"{value[:3]}***{value[-3:]}" if len(value) > 12 else "已设置"
    return "已设置" if value else "未设置"


def _needs_restart(title: str, desc: str) -> bool:
    text = f"{title}{desc}"
    return "重启" in text or "重载" in text


def _view(
    key: str,
    itype: str,
    title: str,
    desc: str,
    value: Any,
    *,
    options: Optional[List] = None,
    secret_flag: bool = False,
    needs_restart: bool = False,
) -> Dict[str, Any]:
    secret = _is_secret(key, title, secret_flag, value)
    item: Dict[str, Any] = {
        "key": key,
        "type": itype,
        "title": title,
        "desc": desc,
        "value": _mask(value) if secret else value,
        "needs_restart": needs_restart,
    }
    if options:
        item["options"] = options
    if secret:
        item["secret"] = True
        item["is_set"] = bool(value)
    return item


def _coerce(itype: str, value: Any) -> Any:
    """把前端传来的值归一到配置项要求的 python 类型。"""
    if itype == "BoolConfig":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "on", "yes")
        return bool(value)
    if itype == "IntConfig":
        return int(value)
    if itype == "FloatConfig":
        return float(value)
    if itype in ("StrConfig", "ColorConfig"):
        return value if isinstance(value, str) else str(value)
    if itype in ("ListStrConfig", "ListConfig"):
        if isinstance(value, str):
            value = [p.strip() for p in value.split(",") if p.strip()]
        if not isinstance(value, list):
            raise ValueError("需要列表")
        return [int(v) for v in value] if itype == "ListConfig" else [str(v) for v in value]
    if itype == "DictConfig":
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("需要字典")
        return value
    return value


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BoolConfig"
    if isinstance(value, int):
        return "IntConfig"
    if isinstance(value, float):
        return "FloatConfig"
    if isinstance(value, list):
        return "ListStrConfig"
    if isinstance(value, dict):
        return "DictConfig"
    return "StrConfig"


def _core_meta(key: str, value: Any) -> tuple:
    """没写进 CORE_META 的新增服务配置按值形态兜底。"""
    return CORE_META.get(key) or (_infer_type(value), key, "")


def _core_view(key: str) -> Dict[str, Any]:
    value = core_config.get_config(key)
    itype, title, desc = _core_meta(key, value)
    item = _view(
        key,
        itype,
        title,
        desc,
        value,
        options=CORE_OPTIONS.get(key),
        needs_restart=key in CORE_RESTART_KEYS,
    )
    if key in CORE_UPLOAD_KEYS:
        # 既能填路径/链接/QQ号, 也能直接传图
        item["upload"] = {"suffix": "", "with_text": True, "exists": _looks_like_file(value)}
    return item


def _looks_like_file(value: Any) -> bool:
    return bool(value) and isinstance(value, str) and Path(value).is_file()


def _core_items() -> List[Dict[str, Any]]:
    return [_core_view(key) for key in CONFIG_DEFAULT if key not in CORE_HIDDEN]


# 值是落盘文件的配置项: 设置页给上传控件, 不让手填路径
UPLOAD_TYPES = {"ImageConfig", "FileUploadConfig"}


def _plugin_item(key: str, item: Any) -> Dict[str, Any]:
    title = getattr(item, "title", "") or key
    desc = getattr(item, "desc", "") or ""
    itype = type(item).__name__
    view = _view(
        key,
        itype,
        title,
        desc,
        to_builtins(getattr(item, "data", None)),
        options=list(getattr(item, "options", None) or []),
        secret_flag=bool(getattr(item, "secret", False)),
        needs_restart=_needs_restart(title, desc),
    )
    if itype in UPLOAD_TYPES:
        view["upload"] = {
            "suffix": getattr(item, "suffix", "") or "",
            "exists": Path(str(getattr(item, "data", "") or "")).is_file(),
        }
    return view


@app.get("/api/config")
async def get_config() -> Dict[str, Any]:
    from rover.utils.plugins_config.gs_config import all_config_list

    groups: List[Dict[str, Any]] = [{"name": CORE_GROUP, "items": _core_items()}]
    for name, inst in all_config_list.items():
        if name == CORE_GROUP or name in HIDDEN_GROUPS:
            continue
        hidden = PLUGIN_HIDDEN.get(name, set())
        items = [_plugin_item(k, v) for k, v in inst.config.items() if k not in hidden]
        groups.append({"name": name, "items": items})
    return {"groups": groups}


@app.post("/api/config")
async def set_config(req: ConfigSetRequest) -> Dict[str, Any]:
    from rover.utils.plugins_config.gs_config import all_config_list

    if req.group == CORE_GROUP:
        if req.key not in CONFIG_DEFAULT:
            raise HTTPException(status_code=404, detail=f"配置项不存在: {req.key}")
        itype, title, desc = _core_meta(req.key, core_config.get_config(req.key))
        try:
            value = _coerce(itype, req.value)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"值格式不正确: {e}")
        if not core_config.set_config(req.key, value):
            raise HTTPException(status_code=400, detail="写入失败")
        item = _core_view(req.key)
    else:
        inst = all_config_list.get(req.group)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"配置分组不存在: {req.group}")
        if req.key not in inst.config:
            raise HTTPException(status_code=404, detail=f"配置项不存在: {req.key}")
        current = inst.config[req.key]
        try:
            value = _coerce(type(current).__name__, req.value)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"值格式不正确: {e}")
        max_value = getattr(current, "max_value", None)
        if max_value is not None and isinstance(value, (int, float)) and value > max_value:
            raise HTTPException(status_code=400, detail=f"超过最大值 {max_value}")
        if not inst.set_config(req.key, value):
            raise HTTPException(status_code=400, detail="写入失败, 类型不符")
        item = _plugin_item(req.key, inst.config[req.key])

    logger.info(f"[配置] {req.group}.{req.key} 已更新")
    return {"ok": True, "group": req.group, "item": item, "needs_restart": item["needs_restart"]}


class ConfigUploadRequest(BaseModel):
    group: str
    key: str
    data: str
    """文件内容, base64; 带不带 data: 前缀都收"""


@app.post("/api/config/upload")
async def upload_config_file(req: ConfigUploadRequest) -> Dict[str, Any]:
    """页面模板/图片一类配置项直接传文件, 落到写死的目标路径, 路径不暴露给前端改。"""
    from rover.api_render import _guess_ext
    from rover.data_store import data_path
    from rover.utils.plugins_config.gs_config import all_config_list

    payload = req.data.split(",", 1)[-1] if req.data.startswith("data:") else req.data
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="文件内容不是合法的 base64")
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")

    if req.group == CORE_GROUP:
        if req.key not in CORE_UPLOAD_KEYS:
            raise HTTPException(status_code=400, detail="该配置项不支持上传")
        target = data_path / f"{req.key}.{_guess_ext(raw)}"
        inst = None
    else:
        inst = all_config_list.get(req.group)
        if inst is None or req.key not in inst.config:
            raise HTTPException(status_code=404, detail=f"配置项不存在: {req.group}.{req.key}")
        item = inst.config[req.key]
        if type(item).__name__ not in UPLOAD_TYPES:
            raise HTTPException(status_code=400, detail="该配置项不支持上传")
        suffix = (getattr(item, "suffix", "") or "bin").lstrip(".")
        target = (
            Path(str(getattr(item, "upload_to", ""))) / f"{getattr(item, 'filename', req.key)}.{suffix}"
        )

    root = data_path.resolve()
    try:
        target.resolve().relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="上传目标不在数据目录内")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    logger.info(f"[配置] {req.group}.{req.key} 已上传 {len(raw)} 字节 → {target}")
    if inst is None:
        core_config.set_config(req.key, str(target))
        view = _core_view(req.key)
    else:
        inst.set_config(req.key, str(target))
        view = _plugin_item(req.key, inst.config[req.key])
    return {"ok": True, "group": req.group, "item": view, "needs_restart": view["needs_restart"]}


@app.exception_handler(Exception)
async def on_error(request, exc: Exception):
    logger.exception(exc)
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
