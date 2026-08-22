"""Validate owner-curated editorial memory without contacting external services."""

import argparse
import json
from pathlib import Path

from services.editorial_memory_service import (
    DEFAULT_MEMORY_PATH,
    get_editorial_memory_operator_schema,
    validate_editorial_memory_operations,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Validate the WeatherWatch owner-curated editorial corpus."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate", help="Validate a corpus JSON file.")
    validate.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_MEMORY_PATH,
        help="Corpus path (defaults to the active runtime editorial-memory path).",
    )
    subcommands.add_parser("schema", help="Print the operator schema as JSON.")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "schema":
            payload = get_editorial_memory_operator_schema()
        else:
            payload = validate_editorial_memory_operations(arguments.path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"editorial memory validation failed: {error}") from error
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
