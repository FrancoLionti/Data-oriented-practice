from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from data_challenge.ingestion import InputFormatError
from data_challenge.pipeline import PipelineError, build_files


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for dataset build operations."""

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
    """Run the CLI and return a process status suitable for ``SystemExit``."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            build_files(
                crm_path=args.crm,
                market_path=args.market,
                interactions_path=args.interactions,
                output_path=args.output,
                rejects_path=args.rejects,
            )
        except (InputFormatError, PipelineError, OSError) as error:
            print(f"build failed: {error}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
