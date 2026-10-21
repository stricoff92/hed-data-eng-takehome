"""Freshness is measured from writes that changed data, against each pipeline's own declared SLO.

A table rewritten with nothing in it, or touched only by maintenance, has not been refreshed."""

from __future__ import annotations

from datetime import datetime

from morning_rounds import models

FRESHNESS_STANDARD = "repo/docs/platform-standards.md:20-25"
THE_REGISTRY = "repo/platform/pipelines.json"
THE_SNAPSHOT_MANIFEST = "workspace/manifest.json"

SECONDS_PER_HOUR = 3600

# The metric that says whether data arrived, per operation. A merge is judged on the rows it was
# handed: one handed rows has refreshed the table even when none of them needed changing, and one
# handed none has not, whatever it then copied. OPTIMIZE is absent because it is maintenance.
ROWS_ARRIVED_METRIC = {
    models.Operation.MERGE: "numSourceRows",
    models.Operation.WRITE: "numOutputRows",
    models.Operation.CREATE_OR_REPLACE_TABLE_AS_SELECT: "numOutputRows",
}


def age_in_hours(timestamp: str, as_of: str) -> float:
    elapsed = datetime.fromisoformat(as_of) - datetime.fromisoformat(timestamp)
    return elapsed.total_seconds() / SECONDS_PER_HOUR


def is_maintenance(commit: models.TableCommit) -> bool:
    return commit.operation is models.Operation.OPTIMIZE


def rows_arrived(commit: models.TableCommit) -> tuple[str, int]:
    metric = ROWS_ARRIVED_METRIC.get(commit.operation)
    if metric is None:
        raise NotImplementedError(f"no row count known for operation: {commit.operation}")

    return metric, commit.metrics[metric]


def refreshed_data(commit: models.TableCommit) -> bool:
    if is_maintenance(commit):
        return False

    _, rows = rows_arrived(commit)
    return rows > 0


def describe_commit(history: models.TableHistory, commit: models.TableCommit) -> str:
    if is_maintenance(commit):
        counted = "no rows: maintenance rewrites files"
    else:
        metric, rows = rows_arrived(commit)
        counted = f"{metric} {rows}"

    return (f"{history.source}: v{commit.version} {commit.operation} at {commit.timestamp} by job "
            f"{commit.job_id} run {commit.run_id}, {counted}")


def describe_slo(pipeline: models.Pipeline) -> str:
    return (f"{THE_REGISTRY}: {pipeline.id} cadence_hours {pipeline.cadence_hours}, "
            f"freshness_slo_hours {pipeline.freshness_slo_hours}")


def unreadable_evidence_finding(
    pipeline: models.Pipeline,
    history: models.TableHistory,
) -> models.Finding:
    return models.Finding(
        code=models.FindingCode.TABLE_EVIDENCE_UNREADABLE,
        subject=pipeline.id,
        what=f"the evidence for {history.table} was not captured, so {pipeline.id} cannot be judged",
        why=f"the snapshot could not read the table: {history.message} That is a gap in the "
            f"evidence and not a statement about the data, so the pipeline is unmeasured rather "
            f"than broken or healthy",
        evidence=(
            f"{THE_SNAPSHOT_MANIFEST}: {history.source}, status {history.status}",
            f"{THE_SNAPSHOT_MANIFEST}: {history.source}, message {history.message}",
            describe_slo(pipeline),
        ),
    )


def wrote_nothing_finding(
    pipeline: models.Pipeline,
    history: models.TableHistory,
    newest_write: models.TableCommit,
    newest_refresh: models.TableCommit | None,
) -> models.Finding:
    metric, rows = rows_arrived(newest_write)
    evidence = [describe_commit(history, newest_write)]
    if newest_refresh is not None:
        evidence.append(describe_commit(history, newest_refresh))
    evidence.append(FRESHNESS_STANDARD)

    return models.Finding(
        code=models.FindingCode.TABLE_WROTE_NOTHING,
        subject=pipeline.id,
        what=f"the newest write to {history.table} changed no data: {metric} is {rows}",
        why=f"v{newest_write.version} was committed at {newest_write.timestamp} by job "
            f"{newest_write.job_id} and moved no rows, so the job reporting success says nothing "
            f"about the data. Consumers are reading whatever was there before it ran",
        evidence=tuple(evidence),
    )


def stale_finding(
    pipeline: models.Pipeline,
    history: models.TableHistory,
    newest_refresh: models.TableCommit,
    newest_commit: models.TableCommit,
    as_of: str,
) -> models.Finding:
    age = age_in_hours(newest_refresh.timestamp, as_of)
    evidence = [describe_commit(history, newest_refresh)]

    masked_by_maintenance = is_maintenance(newest_commit)
    if masked_by_maintenance:
        evidence.append(describe_commit(history, newest_commit))
    evidence.append(describe_slo(pipeline))
    evidence.append(FRESHNESS_STANDARD)

    masked = ""
    if masked_by_maintenance:
        masked = (f". The newest commit is v{newest_commit.version} {newest_commit.operation} at "
                  f"{newest_commit.timestamp}, which is maintenance and refreshed nothing")

    return models.Finding(
        code=models.FindingCode.TABLE_OLDER_THAN_SLO,
        subject=pipeline.id,
        what=f"{history.table} last changed {age:.1f}h before {as_of}, against a "
             f"{pipeline.freshness_slo_hours}h SLO",
        why=f"the last write that changed data was v{newest_refresh.version} at "
            f"{newest_refresh.timestamp}{masked}",
        evidence=tuple(evidence),
    )


def never_refreshed_finding(
    pipeline: models.Pipeline,
    history: models.TableHistory,
) -> models.Finding:
    captured = f"{len(history.commits)} versions" if history.commits else "no versions"
    evidence = [f"{history.source}: {captured} captured, none of them changed data"]
    evidence.extend(describe_commit(history, commit) for commit in history.commits)
    evidence.append(FRESHNESS_STANDARD)

    return models.Finding(
        code=models.FindingCode.TABLE_NEVER_REFRESHED,
        subject=pipeline.id,
        what=f"no write in the captured history of {history.table} changed data",
        why=f"the snapshot holds {captured} of this table and every one of them is maintenance or "
            f"moved no rows, so there is nothing to measure freshness from",
        evidence=tuple(evidence),
    )


def newest_refresh(history: models.TableHistory) -> models.TableCommit | None:
    return next((commit for commit in history.commits if refreshed_data(commit)), None)


def find_freshness(
    pipeline: models.Pipeline,
    history: models.TableHistory,
    as_of: str,
) -> tuple[models.Finding, ...]:
    if history.status is models.CaptureStatus.ERROR:
        return (unreadable_evidence_finding(pipeline, history),)
    elif history.status is not models.CaptureStatus.OK:
        raise NotImplementedError(f"unhandled capture status: {history.status}")

    refreshed = newest_refresh(history)
    if refreshed is None:
        return (never_refreshed_finding(pipeline, history),)

    findings: list[models.Finding] = []
    newest_write = next((commit for commit in history.commits if not is_maintenance(commit)), None)
    if newest_write is not None and not refreshed_data(newest_write):
        findings.append(wrote_nothing_finding(pipeline, history, newest_write, refreshed))

    if age_in_hours(refreshed.timestamp, as_of) > pipeline.freshness_slo_hours:
        findings.append(stale_finding(pipeline, history, refreshed, history.commits[0], as_of))

    return tuple(findings)
