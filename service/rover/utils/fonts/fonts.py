"""内置字体。优先用系统中文字体, 缺失时退回 PIL 默认字体。"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import ImageFont

FONT_PATH = Path(__file__).parent

_CANDIDATES = (
    FONT_PATH / "rover_font.ttf",
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/arphic/gbsn00lp.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


@lru_cache(maxsize=1)
def _font_file() -> Optional[Path]:
    for path in _CANDIDATES:
        if path.exists():
            return path
    return None


@lru_cache(maxsize=64)
def core_font(size: int) -> ImageFont.FreeTypeFont:
    path = _font_file()
    if path is None:
        return ImageFont.load_default(size)  # type: ignore[return-value]
    return ImageFont.truetype(str(path), size)
