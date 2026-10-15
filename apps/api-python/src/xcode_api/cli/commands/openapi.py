"""``xcode-api openapi``: print the OpenAPI document for contract comparison.

The document is built without a database: the container gets a pool that is never opened,
and no routine is called while only the schema is generated.
"""

from __future__ import annotations

import argparse
import json

from ...container import build_container
from ...db.pool import open_pool
from ...main import create_app
from ...settings import SettingsError, load_settings

NAME = "openapi"
HELP = "print the OpenAPI document"


def configure(parser: argparse.ArgumentParser) -> None:
    del parser


def run(args: argparse.Namespace) -> int:
    del args
    try:
        settings = load_settings(openapi_enabled=True)
    except SettingsError as exc:
        for message in exc.messages:
            print(message)
        return 2

    app = create_app(settings, build_container(settings, open_pool(settings)))
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))
    return 0
