"""文案取用。本项目不做多语言 UI, 词条表为空, t() 直接回落 key 本身。"""

from typing import Optional

DEFAULT_LANG: str = "zh-cn"


def t(key: str, /, lang: Optional[str] = None, **params: object) -> str:
    """按 key 取词条; 无词条时回落 key 本身并填充具名占位符。"""
    if not params:
        return key
    try:
        return key.format(**params)
    except (KeyError, IndexError, ValueError):
        return key


def get_lang() -> str:
    return DEFAULT_LANG
