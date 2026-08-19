"""资源文件下载。"""

from pathlib import Path
from typing import TYPE_CHECKING, Union

import aiofiles
import httpx

from rover.logger import logger

if TYPE_CHECKING:
    from aiohttp.client import ClientSession


async def download(
    url: str,
    path: Path,
    name: str,
    sess: Union["ClientSession", httpx.AsyncClient, None] = None,
    tag: str = "",
):
    logger.info(f"{tag} 开始下载: {name}")
    logger.info(f"{tag} 下载地址: {url}")
    if sess is None:
        sess = httpx.AsyncClient()

    try:
        if isinstance(sess, httpx.AsyncClient):
            res = await sess.get(url)
            content = res.read()
            retcode = res.status_code
        else:
            async with sess.get(url) as resp:
                content = await resp.read()
                retcode = resp.status

        if retcode == 200:
            async with aiofiles.open(path / name, "wb") as f:
                await f.write(content)
            logger.success(f"{tag} 下载完成: {name}")
        else:
            logger.warning(f"{tag} 下载失败: {name}, 状态码 {retcode}")
        return retcode
    except Exception as e:
        logger.error(e)
        logger.warning(f"{tag} 下载出错: {name}")
