"""Every read of the fixture pack happens here, so the rules stay pure."""

from __future__ import annotations

import csv
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


CONTRACTS_RELATIVE_PATH = Path("repo") / "contracts"


def parse_column(entry: Any) -> models.Column:
    return models.Column(
        name=entry["name"],
        type=entry["type"],
        nullable=entry["nullable"],
        note=entry.get("note"),
    )


def read_contract(path: Path) -> models.Contract:
    document = read_json(path)
    return models.Contract(
        table=document["table"],
        governed=document["governed"],
        owner=document["owner"],
        contract_version=document["contract_version"],
        source=(CONTRACTS_RELATIVE_PATH / path.name).as_posix(),
        columns=tuple(parse_column(entry) for entry in document["columns"]),
        writers=tuple(
            models.ContractWriter(job=entry["job"], statements=tuple(entry["statements"]))
            for entry in document["writers"]
        ),
    )


def load_contracts(fixtures: Path) -> tuple[models.Contract, ...]:
    directory = fixtures / CONTRACTS_RELATIVE_PATH
    if not directory.is_dir():
        raise FixtureError(f"{directory} is missing")

    return tuple(read_contract(path) for path in sorted(directory.glob("*.json")))


LINEAGE_RELATIVE_PATH = Path("repo") / "platform" / "lineage.json"


def parse_consumer(entry: Any) -> models.Consumer:
    return models.Consumer(
        id=entry["id"],
        name=entry["name"],
        type=entry["type"],
        owner=entry["owner"],
        refresh=entry["refresh"],
        reads=tuple(
            models.ConsumerRead(table=read["table"], fields=tuple(read["fields"]))
            for read in entry["reads"]
        ),
    )


def load_lineage(fixtures: Path) -> models.Lineage:
    document = read_json(fixtures / LINEAGE_RELATIVE_PATH)
    return models.Lineage(
        source=LINEAGE_RELATIVE_PATH.as_posix(),
        tables=tuple(
            models.TableLineage(table=entry["table"], built_from=tuple(entry["built_from"]))
            for entry in document["tables"]
        ),
        consumers=tuple(parse_consumer(entry) for entry in document["consumers"]),
    )


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


TABLES_RELATIVE_PATH = Path("workspace") / "tables"
HISTORY_FILE_NAME = "history.jsonl"
SCHEMA_FILE_NAME = "schema.json"


def table_relative_path(table: str, file_name: str) -> Path:
    return TABLES_RELATIVE_PATH / table / file_name


def parse_table_commit(entry: Any) -> models.TableCommit:
    return models.TableCommit(
        version=entry["version"],
        timestamp=entry["timestamp"],
        user_name=entry["userName"],
        operation=models.Operation(entry["operation"]),
        parameters=entry["operationParameters"],
        # Delta reports the committing job and every metric as strings. Parsing them here is the
        # only reason a rule can compare a commit to a job id or a row count without casting.
        job_id=int(entry["job"]["jobId"]),
        run_id=int(entry["job"]["runId"]),
        metrics={key: int(value) for key, value in entry["operationMetrics"].items()},
    )


def load_table_history(fixtures: Path, manifest: models.Manifest, table: str) -> models.TableHistory:
    relative_path = table_relative_path(table, HISTORY_FILE_NAME)
    captured = captured_file(manifest, relative_path)

    if captured.status is models.CaptureStatus.ERROR:
        commits: tuple[models.TableCommit, ...] = ()
    elif captured.status is models.CaptureStatus.OK:
        commits = tuple(parse_table_commit(entry) for entry in read_jsonl(fixtures / relative_path))
    else:
        raise NotImplementedError(f"unhandled capture status: {captured.status}")

    return models.TableHistory(
        table=table,
        source=relative_path.as_posix(),
        status=captured.status,
        message=captured.message,
        commits=commits,
    )


def load_table_schema(fixtures: Path, manifest: models.Manifest, table: str) -> models.TableSchema:
    relative_path = table_relative_path(table, SCHEMA_FILE_NAME)
    captured = captured_file(manifest, relative_path)

    if captured.status is models.CaptureStatus.ERROR:
        captured_at: str | None = None
        columns: tuple[models.Column, ...] = ()
    elif captured.status is models.CaptureStatus.OK:
        document = read_json(fixtures / relative_path)
        captured_at = document["captured_at"]
        columns = tuple(parse_column(entry) for entry in document["columns"])
    else:
        raise NotImplementedError(f"unhandled capture status: {captured.status}")

    return models.TableSchema(
        table=table,
        source=relative_path.as_posix(),
        status=captured.status,
        message=captured.message,
        captured_at=captured_at,
        columns=columns,
    )


# REFERENCE loaders (neither repo nor workspace: what the platform has written down about itself)

DICTIONARY_RELATIVE_PATH = Path("dictionary") / "data-dictionary.csv"
DICTIONARY_FIRST_ENTRY_LINE = 2


def parse_dictionary_entry(row: Any, line: int) -> models.DictionaryEntry:
    return models.DictionaryEntry(
        data_product=row["data_product"],
        table=row["table"],
        field=row["field"],
        definition=row["definition"],
        review_status=models.ReviewStatus(row["review_status"]),
        business_owner=row["business_owner"],
        source=row["source"],
        original_upstream_source=row["original_upstream_source"],
        line=line,
    )


def load_data_dictionary(fixtures: Path) -> models.DataDictionary:
    path = fixtures / DICTIONARY_RELATIVE_PATH
    if not path.is_file():
        raise FixtureError(f"{path} is missing")

    # The csv module asks for newline="" so it can handle a quoted field that spans lines itself.
    with path.open(encoding="utf-8", newline="") as handle:
        entries = tuple(
            parse_dictionary_entry(row, line)
            for line, row in enumerate(csv.DictReader(handle), start=DICTIONARY_FIRST_ENTRY_LINE)
        )

    return models.DataDictionary(source=DICTIONARY_RELATIVE_PATH.as_posix(), entries=entries)


GAUGES_RELATIVE_PATH = Path("gauges.json")


def parse_gauge(entry: Any) -> models.Gauge:
    return models.Gauge(
        name=entry["name"],
        type=entry["type"],
        labels=tuple(entry["labels"]),
        owner=models.GaugeOwner(entry["owner"]),
        description=entry["description"],
    )


def load_gauge_catalog(fixtures: Path) -> models.GaugeCatalog:
    document = read_json(fixtures / GAUGES_RELATIVE_PATH)
    return models.GaugeCatalog(
        source=GAUGES_RELATIVE_PATH.as_posix(),
        gauges=tuple(parse_gauge(entry) for entry in document["gauges"]),
    )


# AGENT loader (the overnight review, which the tool reconciles against the evidence)

# Named rather than globbed: the brief cites this file, and a pack without it should say so by name
# instead of quietly reconciling against whichever review happened to be lying around.
AGENT_REVIEW_RELATIVE_PATH = Path("agent") / "morning-review-2026-10-20.json"


def parse_claim_evidence(entry: Any) -> models.ClaimEvidence:
    evidence_type = models.ClaimEvidenceType(entry["type"])

    if evidence_type is models.ClaimEvidenceType.RUN:
        return models.ClaimEvidence(type=evidence_type, run_id=entry["run_id"], job_id=None, window=None)
    elif evidence_type is models.ClaimEvidenceType.RUNS:
        return models.ClaimEvidence(
            type=evidence_type, run_id=None, job_id=entry["job_id"], window=entry["window"]
        )
    else:
        raise NotImplementedError(f"unhandled claim evidence type: {evidence_type}")


def parse_claim(entry: Any) -> models.Claim:
    return models.Claim(
        id=entry["id"],
        pipeline=entry["pipeline"],
        assertion=entry["assertion"],
        status=entry["status"],
        evidence=tuple(parse_claim_evidence(item) for item in entry["evidence"]),
    )


def load_agent_review(fixtures: Path) -> models.AgentReview:
    document = read_json(fixtures / AGENT_REVIEW_RELATIVE_PATH)
    return models.AgentReview(
        agent=document["agent"],
        agent_version=document["agent_version"],
        generated_at=document["generated_at"],
        scope=document["scope"],
        summary=document["summary"],
        source=AGENT_REVIEW_RELATIVE_PATH.as_posix(),
        claims=tuple(parse_claim(entry) for entry in document["claims"]),
    )
