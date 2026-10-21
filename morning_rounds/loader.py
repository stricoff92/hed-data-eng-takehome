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
        tier=entry["tier"],
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
