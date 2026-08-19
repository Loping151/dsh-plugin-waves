"""扫码登录二维码。"""

import io
from pathlib import Path


async def get_qrcode_base64(url: str, path: Path, bot_id: str) -> bytes:
    # qrcode(+约2.7MB, 连带 PIL) 仅扫码登录时用到, 按需导入避免常驻启动内存。
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L

    qr = qrcode.QRCode(  # type: ignore
        version=1,
        error_correction=ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=(255, 134, 36), back_color="white")

    img_byte = io.BytesIO()
    img.save(img_byte, format="PNG")  # type: ignore
    return img_byte.getvalue()
