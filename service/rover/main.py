"""服务入口: python -m rover.main [--host 127.0.0.1] [--port 9777]"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description="鸣潮服务")
    parser.add_argument("--host", default=os.getenv("ROVER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ROVER_PORT", "9777")))
    args = parser.parse_args()

    from rover.config import core_config

    if str(core_config.get_config("PORT")) != str(args.port):
        core_config.set_config("PORT", str(args.port))
    if core_config.get_config("HOST") != args.host:
        core_config.set_config("HOST", args.host)

    import uvicorn

    import rover.api  # noqa: F401  注册路由
    from rover.app_life import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
