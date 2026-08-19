"""图片处理工具。"""

import math

from PIL import Image

__all__ = ["crop_center_img"]


def crop_center_img(img: Image.Image, based_w: int, based_h: int) -> Image.Image:
    # 确定图片的长宽
    based_scale = "%.3f" % (based_w / based_h)
    w, h = img.size
    scale_f = "%.3f" % (w / h)
    new_w = math.ceil(based_h * float(scale_f))
    new_h = math.ceil(based_w / float(scale_f))
    if scale_f > based_scale:
        resize_img = img.resize((new_w, based_h), Image.Resampling.LANCZOS)
        x1 = int(new_w / 2 - based_w / 2)
        y1 = 0
        x2 = int(new_w / 2 + based_w / 2)
        y2 = based_h
    else:
        resize_img = img.resize((based_w, new_h), Image.Resampling.LANCZOS)
        x1 = 0
        y1 = int(new_h / 2 - based_h / 2)
        x2 = based_w
        y2 = int(new_h / 2 + based_h / 2)
    crop_img = resize_img.crop((x1, y1, x2, y2))
    return crop_img
