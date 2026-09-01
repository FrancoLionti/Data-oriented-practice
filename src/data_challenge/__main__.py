from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="data-challenge",
        description="Build a canonical company dataset from inconsistent sources.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build canonical and rejected JSONL outputs.")
    build.add_argument("--crm", required=True, help="Path to the CRM CSV input.")
    build.add_argument("--market", required=True, help="Path to the market-data JSON input.")
    build.add_argument("--interactions", required=True, help="Path to the interactions CSV input.")
    build.add_argument("--output", required=True, help="Path to canonical companies JSONL output.")
    build.add_argument("--rejects", required=True, help="Path to rejected records JSONL output.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        # TODO: Replace this placeholder with your implementation.
        parser.error("The build pipeline has not been implemented yet.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
