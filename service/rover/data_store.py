"""数据目录。根为 service/data。"""

from pathlib import Path
from typing import List, Optional, Union

core_path = Path(__file__).parent
data_path = Path(__file__).parents[1] / "data"


def get_res_path(_path: Optional[Union[str, List[str], Path]] = None) -> Path:
    if _path is None:
        path = data_path
    elif isinstance(_path, Path):
        path = _path
    elif isinstance(_path, str):
        path = data_path / _path
    else:
        path = data_path.joinpath(*_path)

    if not path.exists():
        path.mkdir(parents=True)

    return path


RES = get_res_path()

# 下面这些按需创建: 取用时才落盘, 避免一上来就铺一堆空目录
image_res = data_path / "IMAGE_TEMP"
data_cache_path = data_path / "DATA_CACHE_PATH"
CONFIGS_PATH = data_path / "configs"
