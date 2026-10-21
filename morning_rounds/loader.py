"""Every read of the fixture pack happens here, so the rules stay pure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from morning_rounds import models


class FixtureError(Exception):
    """A fixture file the pack promises is not there."""


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise FixtureError(f"{path} is missing")

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


# REPO loaders (source of truth: what should be deployed)

PIPELINES_RELATIVE_PATH = Path("repo") / "platform" / "pipelines.json"


def parse_pipeline(entry: Any) -> models.Pipeline:
    return models.Pipeline(
        id=entry["id"],
        job=entry["job"],
        cadence=entry["cadence"],
        cadence_hours=entry["cadence_hours"],
        freshness_slo_hours=entry["freshness_slo_hours"],
        tier=models.Tier(entry["tier"]),
        owner=entry["owner"],
        writes=tuple(entry["writes"]),
        reads=tuple(entry["reads"]),
    )


def load_pipeline_registry(fixtures: Path) -> models.PipelineRegistry:
    document = read_json(fixtures / PIPELINES_RELATIVE_PATH)
    return models.PipelineRegistry(
        version=document["registry_version"],
        pipelines=tuple(parse_pipeline(entry) for entry in document["pipelines"]),
    )


JOB_DEFINITIONS_RELATIVE_PATH = Path("repo") / "databricks" / "jobs"


def read_job_definition(path: Path) -> models.JobDefinition:
    settings = read_json(path)
    return models.JobDefinition(
        name=settings["name"],
        source=(JOB_DEFINITIONS_RELATIVE_PATH / path.name).as_posix(),
        settings=settings,
    )


def load_job_definitions(fixtures: Path) -> tuple[models.JobDefinition, ...]:
    directory = fixtures / JOB_DEFINITIONS_RELATIVE_PATH
    if not directory.is_dir():
        raise FixtureError(f"{directory} is missing")

    return tuple(read_job_definition(path) for path in sorted(directory.glob("*.json")))


# WORKSPACE loaders (observed snapshot: what is actually deployed, and what it did)

MANIFEST_RELATIVE_PATH = Path("workspace") / "manifest.json"
JOBS_RELATIVE_PATH = Path("workspace") / "jobs.json"


def is_fixture_pack(directory: Path) -> bool:
    return (directory / MANIFEST_RELATIVE_PATH).is_file()


def parse_captured_file(entry: Any) -> models.CapturedFile:
    status = models.CaptureStatus(entry["status"])
    return models.CapturedFile(
        path=entry["path"],
        status=status,
        note=entry.get("note"),
        # An unexplained error would reach the report as a pipeline nobody can judge and no reason
        # given, so the message is required of the entries that claim one failed.
        message=entry["message"] if status is models.CaptureStatus.ERROR else None,
    )


def load_manifest(fixtures: Path) -> models.Manifest:
    document = read_json(fixtures / MANIFEST_RELATIVE_PATH)
    return models.Manifest(
        export=document["export"],
        captured_at=document["captured_at"],
        captured_by=document["captured_by"],
        workspace=document["workspace"],
        source=MANIFEST_RELATIVE_PATH.as_posix(),
        files=tuple(parse_captured_file(entry) for entry in document["files"]),
    )


def captured_file(manifest: models.Manifest, relative_path: Path) -> models.CapturedFile:
    wanted = relative_path.as_posix()
    for captured in manifest.files:
        if captured.path == wanted:
            return captured

    # The manifest is the index of the snapshot. A path it does not list was never exported, which
    # is not the same as a read that failed, and must not be guessed at either way.
    raise FixtureError(f"{manifest.source} does not list {wanted}")


def parse_job(entry: Any) -> models.Job:
    return models.Job(
        job_id=entry["job_id"],
        name=entry["settings"]["name"],
        creator_user_name=entry["creator_user_name"],
        created_time=entry["created_time"],
        last_modified_by=entry["last_modified"]["by"],
        last_modified_at=entry["last_modified"]["at"],
        settings=entry["settings"],
    )


def load_jobs_snapshot(fixtures: Path) -> models.JobsSnapshot:
    document = read_json(fixtures / JOBS_RELATIVE_PATH)
    return models.JobsSnapshot(
        captured_at=document["captured_at"],
        source=JOBS_RELATIVE_PATH.as_posix(),
        jobs=tuple(parse_job(entry) for entry in document["jobs"]),
    )


RUNS_RELATIVE_PATH = Path("workspace") / "runs.jsonl"


def read_jsonl(path: Path) -> list[Any]:
    if not path.is_file():
        raise FixtureError(f"{path} is missing")

    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def parse_run_attempt(entry: Any) -> models.RunAttempt:
    return models.RunAttempt(
        job_id=entry["job_id"],
        job_name=entry["job_name"],
        run_id=entry["run_id"],
        attempt_number=entry["attempt"],
        trigger=models.Trigger(entry["trigger"]),
        start_time=entry["start_time"],
        end_time=entry["end_time"],
        result_state=models.ResultState(entry["result_state"]),
        state_message=entry["state_message"],
    )


def load_runs_log(fixtures: Path) -> models.RunsLog:
    attempts_by_run: dict[int, list[models.RunAttempt]] = {}
    for entry in read_jsonl(fixtures / RUNS_RELATIVE_PATH):
        attempt = parse_run_attempt(entry)
        attempts_by_run.setdefault(attempt.run_id, []).append(attempt)

    # A dict keeps insertion order, so the runs stay newest first, the order runs/list returned
    # them in. Attempts are sorted because the file lists the newest attempt of a run first.
    runs = tuple(
        models.Run(
            run_id=run_id,
            job_id=attempts[0].job_id,
            job_name=attempts[0].job_name,
            attempts=tuple(sorted(attempts, key=lambda attempt: attempt.attempt_number)),
        )
        for run_id, attempts in attempts_by_run.items()
    )
    return models.RunsLog(source=RUNS_RELATIVE_PATH.as_posix(), runs=runs)
