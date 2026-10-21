"""

Script Entry Point

Morning rounds: what is actually true about each pipeline, and whether the
agent's overnight review agrees. Run as `python3 rounds.py check --fixtures DIR`."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from io import TextIOWrapper
from pathlib import Path

from morning_rounds import (
    constants,
    drift,
    loader,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

COMMAND_CHECK = "check"

LOG_DIRECTORY = Path(__file__).resolve().parent / "logs"
LOG_FILE_NAME = "rounds.log"
LOG_MESSAGE_FORMAT = "%(asctime)s %(levelname)s %(module)s %(message)s"
LOG_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

logger = logging.getLogger(constants.APP_LOGGER_NAME)


class Utf8LineFeedFileHandler(logging.FileHandler):
    # logging.FileHandler cannot be given a newline, so on Windows it would
    # rewrite every "\n" as CRLF.
    def _open(self) -> TextIOWrapper:
        return open(self.baseFilename, "a", encoding="utf-8", newline="\n")


def configure_logging() -> None:
    # main() may run more than once in a single process, which the tests do.
    # Without this the handler is attached again and every line is duplicated.
    if logger.handlers:
        return

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_MESSAGE_FORMAT, datefmt=LOG_TIMESTAMP_FORMAT)
    # The fixtures timestamp everything in UTC, so the logs read against them
    # without a mental offset.
    formatter.converter = time.gmtime
    handler = Utf8LineFeedFileHandler(LOG_DIRECTORY / LOG_FILE_NAME)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


def configure_streams() -> None:
    # Windows writes stdout in the console code page and rewrites "\n" as CRLF,
    # which corrupts machine-readable output. Only a real TextIOWrapper can be
    # reconfigured; the tests capture output with StringIO, which cannot.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", newline="\n")


def write_output_line(message: str) -> None:
    print(message, file=sys.stdout, flush=True)


def write_error_line(message: str) -> None:
    logger.error(message)
    print(f"{constants.APP_LOGGER_NAME}: {message}", file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rounds.py",
        description="Work out what is true about each pipeline this morning, "
        "and check the agent's overnight review against it.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    check = subcommands.add_parser(
        COMMAND_CHECK,
        help="Run the morning rounds over a fixture pack and write the report.",
    )
    check.add_argument(
        "--fixtures",
        type=Path,
        default=Path("takehome-packet/fixtures"),
        metavar="DIR",
        help="Path to the fixture pack, read-only (default: %(default)s).",
    )
    check.add_argument(
        "--as-of",
        dest="as_of",
        default=None,
        metavar="TIMESTAMP",
        help="Override 'now'. Defaults to captured_at in workspace/manifest.json.",
    )
    check.add_argument(
        "--out",
        type=Path,
        default=Path("."),
        metavar="DIR",
        help="Where report.json, report.md and telemetry.ndjson are written "
        "(default: the current directory).",
    )
    check.set_defaults(handler=run_check)

    return parser


def run_check(arguments: argparse.Namespace) -> int:
    # Resolved up front so every later fixture read is an absolute path, which
    # keeps messages unambiguous regardless of the caller's directory.
    fixtures: Path = arguments.fixtures.resolve()
    output_directory: Path = arguments.out.resolve()

    if not fixtures.is_dir():
        write_error_line(f"no fixture pack at {fixtures}")
        write_error_line("pass --fixtures DIR to point at it.")
        return EXIT_USAGE

    if not loader.is_fixture_pack(fixtures):
        write_error_line(
            f"{fixtures} is not a fixture pack: "
            f"{loader.MANIFEST_RELATIVE_PATH} is missing."
        )
        return EXIT_USAGE

    # The panel diffs the pack against their original, so refuse to aim our own
    # output into it rather than trusting ourselves not to.
    if output_directory == fixtures or output_directory.is_relative_to(fixtures):
        write_error_line(
            f"--out {output_directory} is inside the fixture pack; "
            f"the pack is read-only. Write the report somewhere else."
        )
        return EXIT_USAGE

    logger.info("fixtures: %s", fixtures)
    logger.info("as-of: %s", arguments.as_of or "unset, reading captured_at from manifest")
    logger.info("output directory: %s", output_directory)

    try:
        registry = loader.load_pipeline_registry(fixtures)
        definitions = loader.load_job_definitions(fixtures)
        deployed = loader.load_jobs_snapshot(fixtures)
    except loader.FixtureError as error:
        write_error_line(str(error))
        write_error_line("pass --fixtures DIR to point at the fixture pack.")
        return EXIT_ERROR

    write_output_line(
        f"{loader.PIPELINES_RELATIVE_PATH.as_posix()}: registry version {registry.version}, "
        f"{len(registry.pipelines)} pipelines"
    )
    write_output_line(
        f"{loader.JOB_DEFINITIONS_RELATIVE_PATH.as_posix()}/: {len(definitions)} job definitions"
    )
    write_output_line(f"{loader.JOBS_RELATIVE_PATH.as_posix()}: {len(deployed.jobs)} deployed jobs")

    drift_findings = drift.find_drift(definitions, deployed)
    write_output_line(f"drift: {len(drift_findings)} findings")
    for finding in drift_findings:
        write_output_line(f"  {finding.subject}: {finding.code}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    configure_logging()
    arguments = build_parser().parse_args(argv)

    # A fixture that does not have its documented shape reaches us as a KeyError or a TypeError
    # from deep inside a loader. Crash, but leave the traceback somewhere a reader can find it.
    try:
        return arguments.handler(arguments)
    except Exception:
        logger.exception("rounds failed")
        write_error_line(f"unexpected failure. the traceback is in {LOG_DIRECTORY / LOG_FILE_NAME}")
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
