"""日志。标准 logging + success/trace 两个额外级别。"""

import logging
import os
import sys
from typing import Any

SUCCESS = 25
TRACE = 5
logging.addLevelName(SUCCESS, "SUCCESS")
logging.addLevelName(TRACE, "TRACE")


class RoverLogger(logging.Logger):
    def success(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        if self.isEnabledFor(SUCCESS):
            self._log(SUCCESS, msg, args, **kwargs)

    def trace(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        if self.isEnabledFor(TRACE):
            self._log(TRACE, msg, args, **kwargs)


logging.setLoggerClass(RoverLogger)

_COLORS = {
    "TRACE": "\033[36m",
    "DEBUG": "\033[36m",
    "INFO": "\033[0m",
    "SUCCESS": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        plain = record.levelname
        record.levelname = f"{color}{plain:<8}\033[0m"
        try:
            return super().format(record)
        finally:
            # 同一条记录还要交给文件处理器, 不能把颜色码留在上面
            record.levelname = plain


# 落盘日志的容量上限: 单个文件 2MB, 连备份最多 4 个文件
FILE_MAX_BYTES = 2 * 1024 * 1024
FILE_BACKUPS = 3


def _level() -> str:
    try:
        from rover.config import core_config

        value = core_config.get_config("log_level")
    except Exception:
        value = ""
    return str(os.getenv("ROVER_LOG_LEVEL") or value or "INFO").upper()


def _file_handler() -> logging.Handler:
    from logging.handlers import RotatingFileHandler

    from rover.data_store import get_res_path

    return RotatingFileHandler(
        get_res_path("logs") / "service.log",
        maxBytes=FILE_MAX_BYTES,
        backupCount=FILE_BACKUPS,
        encoding="utf-8",
    )


def _build() -> RoverLogger:
    lg = logging.getLogger("rover")
    if not isinstance(lg, RoverLogger):
        # 本模块之前已有人建过同名 logger, 换成带 success/trace 的实现
        lg.__class__ = RoverLogger
    if lg.handlers:
        return lg  # type: ignore[return-value]

    lg.setLevel(_level())
    fmt = "%(asctime)s | %(levelname)s | %(message)s"

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(_Formatter(fmt, "%m-%d %H:%M:%S"))
    lg.addHandler(stdout)
    try:
        handler = _file_handler()
        # 文件里不要 ANSI 颜色码
        handler.setFormatter(logging.Formatter(fmt, "%m-%d %H:%M:%S"))
        lg.addHandler(handler)
    except OSError:
        pass
    lg.propagate = False
    return lg  # type: ignore[return-value]


logger: RoverLogger = _build()
