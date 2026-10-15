"""``xcode-api`` command line: a subcommand registry over ``cli/commands/``.

Each command is a module or object exposing ``NAME``, ``HELP``, ``configure(parser)`` and
``run(args) -> int``; registering it in ``COMMANDS`` is the only wiring. The full list is
``docs/08-operability.md`` section 8. Logs go to stderr at INFO; stdout is the command's
output.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ..infra.logging import configure_cli_logging
from .commands import db, openapi, seed, serve, settings_check, users

COMMANDS = (serve, db, *users.COMMANDS, seed, openapi, settings_check)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xcode-api", description="xcode revenue-management API")
    sub = parser.add_subparsers(dest="command", required=True)
    for module in COMMANDS:
        command_parser = sub.add_parser(module.NAME, help=module.HELP)
        module.configure(command_parser)
        command_parser.set_defaults(_run=module.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_cli_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    run = args._run
    return int(run(args))


if __name__ == "__main__":
    sys.exit(main())
