"""

Script Entry Point

Morning rounds: what is actually true about each pipeline, and whether the
agent's overnight review agrees. Run as `python3 rounds.py check --fixtures DIR`."""

from __future__ import annotations

import argparse
import sys
from io import TextIOWrapper
from pathlib import Path

from morning_rounds import (
    constants,
    contracts,
    drift,
    freshness,
    loader,
    models,
    reconcile,
    report,
    status,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

COMMAND_CHECK = "check"


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
    print(f"{constants.APP_NAME}: {message}", file=sys.stderr, flush=True)


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

    if output_directory.exists() and not output_directory.is_dir():
        write_error_line(f"--out {output_directory} is a file; it has to be a directory.")
        return EXIT_USAGE

    # The panel diffs the pack against their original, so refuse to aim our own
    # output into it rather than trusting ourselves not to.
    if output_directory == fixtures or output_directory.is_relative_to(fixtures):
        write_error_line(
            f"--out {output_directory} is inside the fixture pack; "
            f"the pack is read-only. Write the report somewhere else."
        )
        return EXIT_USAGE

    as_of_override: str | None = arguments.as_of

    try:
        manifest = loader.load_manifest(fixtures)
        registry = loader.load_pipeline_registry(fixtures)
        definitions = loader.load_job_definitions(fixtures)
        deployed = loader.load_jobs_snapshot(fixtures)
        runs = loader.load_runs_log(fixtures)
        governed_contracts = loader.load_contracts(fixtures)
        lineage = loader.load_lineage(fixtures)
        dictionary = loader.load_data_dictionary(fixtures)
        gauges = loader.load_gauge_catalog(fixtures)
        review = loader.load_agent_review(fixtures)
        written_tables = sorted(
            {table for pipeline in registry.pipelines for table in pipeline.writes}
            | {contract.table for contract in governed_contracts}
        )
        histories = {
            table: loader.load_table_history(fixtures, manifest, table) for table in written_tables
        }
        schemas = {
            table: loader.load_table_schema(fixtures, manifest, table) for table in written_tables
        }
    except loader.FixtureError as error:
        write_error_line(str(error))
        write_error_line("pass --fixtures DIR to point at the fixture pack.")
        return EXIT_ERROR

    as_of: str = as_of_override or manifest.captured_at
    as_of_source = "--as-of" if as_of_override else manifest.source
    try:
        asked_for = freshness.parse_timestamp(as_of)
    except ValueError as error:
        write_error_line(f"{as_of_source}: {error}")
        return EXIT_USAGE

    # Every age is measured against the snapshot, and the snapshot holds runs and commits from up
    # to the instant it was captured. Measuring from before that would date evidence to the future
    # and report negative ages; hiding the evidence instead is a feature this does not have.
    if asked_for < freshness.parse_timestamp(manifest.captured_at):
        write_error_line(
            f"--as-of {as_of} is before {manifest.source} was captured "
            f"({manifest.captured_at}), and the snapshot cannot be un-seen."
        )
        return EXIT_USAGE

    unreadable = tuple(
        file for file in manifest.files if file.status is models.CaptureStatus.ERROR
    )
    write_output_line(
        f"{manifest.source}: captured by {manifest.captured_by}, {len(manifest.files)} files, "
        f"{len(unreadable)} the snapshot could not read"
    )
    write_output_line(f"as of {as_of}")
    write_output_line(
        f"{loader.PIPELINES_RELATIVE_PATH.as_posix()}: registry version {registry.version}, "
        f"{len(registry.pipelines)} pipelines"
    )
    write_output_line(
        f"{loader.JOB_DEFINITIONS_RELATIVE_PATH.as_posix()}/: {len(definitions)} job definitions"
    )
    write_output_line(f"{loader.JOBS_RELATIVE_PATH.as_posix()}: {len(deployed.jobs)} deployed jobs")
    write_output_line(
        f"{loader.RUNS_RELATIVE_PATH.as_posix()}: {len(runs.runs)} runs, "
        f"{sum(len(run.attempts) for run in runs.runs)} attempts"
    )
    findings = (drift.find_drift(definitions, deployed)
                + contracts.find_contract_drift(governed_contracts, schemas, registry))
    assessed = status.assess(registry, runs, histories, findings, as_of)
    rounds_result = models.RoundsResult(
        as_of=as_of,
        manifest=manifest,
        pipelines=assessed,
        platform_findings=status.platform_findings(registry, findings),
        histories=histories,
        review=review,
        verdicts=reconcile.reconcile(review, assessed, runs),
        unreviewed=reconcile.unreviewed_pipelines(review, registry),
        catalog=gauges,
        contract_violations=contracts.count_violations(governed_contracts, schemas),
    )

    write_output_line(
        f"{len(governed_contracts)} governed tables, {len(lineage.consumers)} consumers, "
        f"{len(dictionary.entries)} documented fields, {len(schemas)} deployed schemas read"
    )
    worst_first = sorted(
        rounds_result.pipelines, key=lambda assessed: report.STATUS_ORDER.index(assessed.status)
    )
    for assessed in worst_first:
        write_output_line(
            f"{assessed.status}: {assessed.pipeline.id} "
            f"(tier {assessed.pipeline.tier}, {len(assessed.findings)} findings)"
        )
    for finding in rounds_result.platform_findings:
        write_output_line(f"platform: {finding.subject}, {finding.code}")
    for judged in rounds_result.verdicts:
        write_output_line(f"{judged.verdict}: {judged.claim.id} {judged.claim.pipeline}")
    write_output_line(f"not reviewed by the agent: {', '.join(rounds_result.unreviewed)}")

    for written_path in report.write_reports(rounds_result, output_directory):
        write_output_line(f"wrote {written_path}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    arguments = build_parser().parse_args(argv)
    # A fixture that does not have its documented shape reaches us from deep inside a loader, as a
    # KeyError for a missing field or a ValueError for a value outside the vocabulary models
    # declares. Nothing here can handle that, so it propagates: traceback to stderr, exit code 1.
    return arguments.handler(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
