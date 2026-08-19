"""给渲染好的 HTML 挂上点击动作: 点角色出面板。按渲染上下文的顺序与文档顺序一一对应。"""

import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from rover.logger import logger



# 角色格子的开标签, 与各模板中的写法一致
_ROLE_TAG = re.compile(r'<div class="role-mini(?![-\w])(?P<rest>[^>]*)>')
_BODY_END = re.compile(r"</body\s*>", re.I)

_BRIDGE = """
<style>
[data-ww-cmd]{cursor:pointer;position:relative}
[data-ww-cmd]:hover{outline:2px solid rgba(255,214,102,.95);outline-offset:2px}
html,body{margin:0;padding:0;overflow:hidden;background:transparent}
html{width:100%}
</style>
<script>
(function(){
  var availW = 0;
  var settled = false;
  // 设计宽度只量一次: 模板多是 body 定宽 + 内层 width:100%, 一旦把 body 改窄,
  // 内层跟着缩, 里面的定宽行就溢出被裁。量完就把 body 钉死在设计宽度上。
  var designW = 0;
  function root(){ return document.querySelector('.container') || document.body }
  function post(msg){ try{ parent.postMessage(Object.assign({source:'ww-card'},msg),'*') }catch(e){} }
  // scrollWidth/scrollHeight 是布局值, 不受 transform 影响
  function apply(){
    var el = root();
    if(!designW){
      designW = Math.max(el.scrollWidth, document.body.scrollWidth, 1);
      document.body.style.width = designW + 'px';
    }
    var h = Math.max(el.scrollHeight, document.body.scrollHeight, 1);
    var scale = availW ? Math.min(1, availW / designW) : 1;
    // 缩放整个 body: 卡片外层的背景层之类不在 .container 里的元素也一起等比缩
    document.body.style.transformOrigin = 'top left';
    document.body.style.transform = scale < 1 ? 'scale(' + scale + ')' : '';
    var w = Math.ceil(designW * scale), sh = Math.ceil(h * scale);
    document.documentElement.style.width = w + 'px';
    document.documentElement.style.height = sh + 'px';
    if(settled) post({kind:'size', width: w, height: sh});
  }
  window.addEventListener('message', function(e){
    var d = e.data;
    if(d && d.source === 'ww-host' && d.kind === 'width'){ availW = d.width || 0; apply(); }
  });
  document.addEventListener('click', function(e){
    var t = e.target && e.target.closest ? e.target.closest('[data-ww-cmd]') : null;
    if(!t) return;
    e.preventDefault();
    post({kind:'command', command:t.getAttribute('data-ww-cmd')});
  });
  // 字体和图片没落定就报尺寸, 宿主会先按半成品高度撑开再跳一次;
  // 所以量归量, 落定之后才往外报, 卡片一次到位。
  function settle(){ settled = true; apply(); }
  function whenLoaded(fn){
    if(document.readyState === 'complete') fn();
    else window.addEventListener('load', fn);
  }
  function ready(){ post({kind:'ready'}); apply(); }
  document.addEventListener('DOMContentLoaded', ready);
  whenLoaded(function(){
    var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    fonts.then(settle, settle);
  });
  if(window.ResizeObserver){ new ResizeObserver(apply).observe(root()); }
  setTimeout(ready, 300);
  // 字体加载卡住也不能一直不出, 到点就认
  setTimeout(settle, 2500);
})();
</script>
"""


def _walk(node: Any, path: Iterable[str]) -> List[dict]:
    """按 key 路径逐层展开嵌套列表, 结果保持模板遍历顺序。"""
    keys = list(path)
    current: List[Any] = [node]
    for key in keys:
        nxt: List[Any] = []
        for item in current:
            if isinstance(item, dict):
                value = item.get(key)
                if isinstance(value, list):
                    nxt.extend(value)
        current = nxt
    return [i for i in current if isinstance(i, dict)]


def _roles_from(context: dict, *paths: Iterable[str]) -> List[dict]:
    out: List[dict] = []
    for path in paths:
        out.extend(_walk(context, path))
    return out


# 矩阵模板的上下文里只有图标没有角色 id, 由 cards/matrix_roles 在构图时记下来补上
_RECORDED_ROLE_IDS: List[str] = []


def record_role_id(role_id: Any) -> None:
    _RECORDED_ROLE_IDS.append(str(role_id))


def _matrix_roles(context: dict) -> List[dict]:
    roles = _roles_from(context, ("modes", "teams", "roles"))
    recorded = list(_RECORDED_ROLE_IDS)
    _RECORDED_ROLE_IDS.clear()
    real = [r for r in roles if not r.get("is_placeholder")]
    # 条数对不上说明记录与实际渲染错位了, 宁可不挂也不能挂错人
    if len(recorded) == len(real):
        for role, role_id in zip(real, recorded):
            role.setdefault("id", role_id)
    elif recorded:
        logger.debug(f"[鸣潮·交互] 矩阵角色 id 记录 {len(recorded)} 个, 实到 {len(real)} 个, 跳过")
    return roles


_EXTRACTORS: Dict[str, Callable[[dict], List[dict]]] = {
    "abyss/abyss_card.html": lambda c: _roles_from(c, ("towers", "floors", "roles")),
    "abyss/slash_card.html": lambda c: _roles_from(c, ("challenges", "half_list", "roles")),
    "abyss/challenge_card.html": lambda c: _roles_from(c, ("challenges", "roles")),
    "abyss/matrix_detail_card.html": _matrix_roles,
}


def _char_name(role_id: str) -> Optional[str]:
    """角色名转换在插件侧, 延迟取用避免本模块依赖插件。"""
    import importlib
    import sys

    suffix = "XutheringWavesUID.utils.name_convert"
    for name, module in list(sys.modules.items()):
        if name.endswith(suffix) and module is not None:
            return module.char_id_to_char_name(str(role_id))
    for package in ("plugins.XutheringWavesUID.XutheringWavesUID", "waves"):
        try:
            convert = importlib.import_module(f"{package}.utils.name_convert")
        except ModuleNotFoundError:
            continue
        return convert.char_id_to_char_name(str(role_id))
    return None


def _prefix() -> str:
    from rover.sv import all_prefixes

    items = all_prefixes()
    return items[0] if items else ""


def _role_name(role: dict) -> Optional[str]:
    role_id = role.get("id") or role.get("role_id") or role.get("roleId")
    name = role.get("name") or role.get("role_name")
    if not name and role_id:
        name = _char_name(role_id)
    return name or None


def _role_command(role: dict) -> Optional[str]:
    name = _role_name(role)
    return f"{_prefix()}{name}面板" if name else None


_CONTAINER = re.compile(
    r'<div[^>]*class="[^"]*\bcontainer\b[^"]*"[^>]*>.*</div>', re.S | re.I
)


def merge_html_cards(parts: List[Any]) -> Any:
    """多张同模板卡片竖排成一页。"""
    from rover.media import HtmlBytes

    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    base = parts[0].html
    extra: List[str] = []
    for part in parts[1:]:
        found = _CONTAINER.search(part.html)
        if found:
            extra.append(found.group(0))
    if not extra:
        return parts[0]
    block = "\n".join(extra)
    if "</body" in base:
        merged = base.replace("</body", block + "\n</body", 1)
    else:
        merged = base + block
    return HtmlBytes(merged, getattr(parts[0], "template_name", ""))


def annotate_html(html: str, template_name: str, context: dict) -> str:
    """在角色格子上写入命令, 并注入点击/尺寸桥接脚本。"""
    try:
        extractor = _EXTRACTORS.get(template_name)
        if extractor:
            roles = extractor(context)
            names = [_role_name(r) for r in roles]
            commands = [_role_command(r) for r in roles]
            if commands:
                counter = {"i": 0}

                def repl(match: re.Match) -> str:
                    idx = counter["i"]
                    counter["i"] += 1
                    command = commands[idx] if idx < len(commands) else None
                    tag = match.group(0)
                    if not command:
                        return tag
                    # 角色在卡面上只有头像, 名字另存一份: 给模型的文字摘要要认得出是谁
                    name = names[idx] if idx < len(names) else ""
                    extra = f' data-ww-name="{name}"' if name else ""
                    return f'{tag[:-1]} data-ww-cmd="{command}"{extra}>'

                html = _ROLE_TAG.sub(repl, html)
                if counter["i"] != len(commands):
                    logger.debug(
                        f"[鸣潮·交互] {template_name} 角色格 {counter['i']} 个, 上下文 {len(commands)} 个"
                    )
        if _BODY_END.search(html):
            return _BODY_END.sub(_BRIDGE + "</body>", html, count=1)
        return html + _BRIDGE
    except Exception as e:
        logger.warning(f"[鸣潮·交互] 注入失败 {template_name}: {e}")
        return html
