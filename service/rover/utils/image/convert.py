"""图片格式转换。"""

import os
from base64 import b64encode
from io import BytesIO
from pathlib import Path
from typing import Union

from PIL import Image

from rover.logger import logger
from rover.pool import to_thread

pic_quality: int = int(os.getenv("ROVER_PIC_QUALITY", "92"))


async def convert_img(
    img: Union[Image.Image, str, Path, bytes],
    is_base64: bool = False,
):
    """图片转 bytes 或 base64。is_base64 只对 PIL 对象生效, 其余一律返回 base64 串。"""
    return await _convert_img(img, is_base64)


@to_thread
def _convert_img(
    img: Union[Image.Image, str, Path, bytes],
    is_base64: bool = False,
):
    logger.info("[图片] 开始处理图片...")

    if isinstance(img, Image.Image):
        result_buffer = BytesIO()
        if img.format == "GIF":
            img.save(result_buffer, format="GIF")
        else:
            img.convert("RGB").save(result_buffer, format="JPEG", quality=pic_quality)

        res = result_buffer.getvalue()
        if is_base64:
            res = "base64://" + b64encode(res).decode()
        return res
    elif isinstance(img, bytes):
        pass
    else:
        with open(Path(img), "rb") as fp:
            img = fp.read()

    logger.success("[图片] 处理完成!")

    return f"base64://{b64encode(img).decode()}"
