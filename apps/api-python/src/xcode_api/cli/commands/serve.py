"""``xcode-api serve``: run the API with uvicorn.

Settings are validated here first so a bad environment exits 2 with every violation
listed before uvicorn starts; the factory ``main.build_default_app`` then opens the pool
and runs the startup checks inside the lifespan. A failed startup (no database within
30 s, a routine-contract mismatch) exits 1; uvicorn's own code for it is 3.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from ...settings import SettingsError, load_settings

# psycopg's async pool cannot run on Windows' default Proactor loop.
LOOP = "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto"

UVICORN_STARTUP_FAILURE = 3

NAME = "serve"
HELP = "run the API server"


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - binds behind the proxy
    parser.add_argument("--port", type=int, default=5000)


def run(args: argparse.Namespace) -> int:
    try:
        load_settings()
    except SettingsError as exc:
        for message in exc.messages:
            print(message)
        return 2

    try:
        uvicorn.run(
            "xcode_api.main:build_default_app",
            factory=True,
            host=args.host,
            port=args.port,
            access_log=False,
            # XCODE_TRUSTED_PROXIES alone decides which X-Forwarded-For hops are believed.
            proxy_headers=False,
            timeout_graceful_shutdown=30,
            server_header=False,
            loop=LOOP,
        )
    except SystemExit as exc:
        if exc.code == UVICORN_STARTUP_FAILURE:
            return 1
        raise
    return 0
