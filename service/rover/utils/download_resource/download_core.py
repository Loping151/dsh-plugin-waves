"""资源批量下载。目录索引解析 + 按大小比对增量下载。"""

import asyncio
import os
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup, Tag

from rover.logger import logger

from .download_file import download


async def _get_url(url: str, client: httpx.AsyncClient) -> bytes:
    try:
        response = await client.get(url)
        return response.read()
    except httpx.HTTPStatusError as exc:
        logger.warning(f"[资源下载] HTTP 错误: {url} {exc}")
        return b""
    except httpx.ConnectError as exc:
        logger.warning(f"[资源下载] 连接错误: {url} {exc}")
        return b""
    except httpx.UnsupportedProtocol as exc:
        logger.warning(f"[资源下载] 协议不支持: {url} {exc}")
        return b""
    except httpx.RequestError as exc:
        logger.warning(f"[资源下载] 请求错误: {url} {exc}")
        return b""


async def download_atag_file(
    PLUGIN_RES: str,
    endpoint: str,
    EPATH_MAP: Dict[str, Path],
    client: httpx.AsyncClient,
    TAG: str,
    plugin_name: str,
):
    TASKS = []
    url = f"{PLUGIN_RES}/{endpoint}"
    if not url.endswith("/"):
        url += "/"

    if endpoint not in EPATH_MAP:
        # 仅当用户填了尾斜杠时才裁掉, 避免 EPATH_MAP 误匹
        _endpoint = endpoint[:-1] if endpoint.endswith("/") else endpoint
        _et = _endpoint.rsplit("/", 1)
        _e = _et[0]
        _t = _et[1]
        if _e in EPATH_MAP:
            path = EPATH_MAP[_e] / _t
        else:
            return
    else:
        path = EPATH_MAP[endpoint]

    if not path.exists():
        path.mkdir(parents=True)

    base_data = await _get_url(url, client)
    content_bs = BeautifulSoup(base_data, "lxml")
    pre_data_list = content_bs.find_all("pre")
    if not pre_data_list:
        logger.warning(f"{TAG} {endpoint} 目录索引解析失败")
        return
    pre_data = pre_data_list[0]

    if not isinstance(pre_data, Tag):
        logger.warning(f"{TAG} {endpoint} 目录索引解析失败")
        return
    data_list = pre_data.find_all("a")
    size_list = [i for i in content_bs.strings]

    logger.trace(f"{TAG} {endpoint} 共 {len(data_list)} 个条目")

    temp_num = 0
    size_temp = 0
    for index, data in enumerate(data_list):
        if data["href"] == "../":  # type: ignore
            continue
        file_url = f"{url}{data['href']}"  # type: ignore
        name: str = unquote(file_url.split("/")[-1])
        size = size_list[index * 2 + 6].split(" ")[-1]
        _size: str = size.replace("\r", "")
        _size = _size.replace("\n", "")

        if _size == "-" or _size == "-\n":
            await download_atag_file(
                PLUGIN_RES,
                f"{endpoint}/{data['href']}",  # type: ignore
                EPATH_MAP,
                client,
                TAG,
                plugin_name,
            )
            continue

        if _size.isdigit():
            size = int(_size)
        else:
            continue

        file_path = path / name

        if file_path.exists():
            is_diff = size == os.stat(file_path).st_size
        else:
            is_diff = True

        if not file_path.exists() or not os.stat(file_path).st_size or not is_diff:
            logger.info(f"{TAG} {plugin_name} {endpoint} 下载 {name}")
            temp_num += 1
            size_temp += size
            TASK = asyncio.create_task(download(file_url, path, name, client, TAG))
            TASKS.append(TASK)
            if size_temp >= 1500000:
                await asyncio.gather(*TASKS)
                TASKS.clear()
    else:
        await asyncio.gather(*TASKS)
        TASKS.clear()

    if temp_num == 0:
        logger.trace(f"{TAG} {endpoint} 无需更新")
    else:
        logger.success(f"{TAG} {endpoint} 下载 {temp_num} 个文件完成")
    temp_num = 0


async def download_all_file(
    plugin_name: str,
    EPATH_MAP: Dict[str, Path],
    URL: Optional[str] = None,
    TAG: Optional[str] = None,
):
    # 资源站由调用方测速后给出, 缺失时直接跳过
    if not URL:
        logger.warning(f"[资源下载] {plugin_name} 无可用资源站, 跳过")
        return

    TAG = TAG or "[Unknown]"
    PLUGIN_RES = f"{URL}/{plugin_name}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(200.0)) as client:
        n = 0
        for endpoint in EPATH_MAP:
            await download_atag_file(
                PLUGIN_RES,
                endpoint,
                EPATH_MAP,
                client,
                TAG,
                plugin_name,
            )
            n += 1

        if n == len(EPATH_MAP):
            logger.success(f"[资源下载] {plugin_name} 资源下载完成")
