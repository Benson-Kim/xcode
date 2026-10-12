"""``xcode-api settings-check``: validate settings and print the summary."""

from __future__ import annotations

import argparse
import json

from ...settings import SettingsError, load_settings

NAME = "settings-check"
HELP = "validate XCODE_* settings and print the startup summary"


def configure(parser: argparse.ArgumentParser) -> None:
    del parser


def run(args: argparse.Namespace) -> int:
    del args
    try:
        settings = load_settings()
    except SettingsError as exc:
        for message in exc.messages:
            print(message)
        return 2
    print(json.dumps(settings.summary(), indent=2, sort_keys=True))
    return 0
