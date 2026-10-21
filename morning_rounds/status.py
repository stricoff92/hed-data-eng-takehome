"""Exactly one status per registered pipeline, from the findings its own evidence supports."""

from __future__ import annotations

from morning_rounds import freshness, models

THE_RUN_LOG = "workspace/runs.jsonl"

# A pipeline nobody can measure must not be reported as degraded, which would claim its data is
# fine for now. A job we watched fail is measured, so broken outranks unmeasured.
STATUS_PRECEDENCE = (
    models.PipelineStatus.BROKEN,
    models.PipelineStatus.UNMEASURED,
    models.PipelineStatus.DEGRADED,
)

# Which findings make a pipeline what. Kept in one table so the same fault always carries the same
# weight, and so the choice is somewhere a reader can check it against the brief.
STATUS_BY_FINDING_CODE = {
    models.FindingCode.JOB_NOT_IN_GIT: models.PipelineStatus.DEGRADED,
    models.FindingCode.JOB_NOT_DEPLOYED: models.PipelineStatus.BROKEN,
    models.FindingCode.JOB_SETTINGS_DIFFER: models.PipelineStatus.DEGRADED,
    models.FindingCode.JOB_RUN_FAILED: models.PipelineStatus.BROKEN,
    models.FindingCode.JOB_DID_NOT_RUN: models.PipelineStatus.BROKEN,
    models.FindingCode.JOB_SUCCEEDS_ONLY_ON_RETRY: models.PipelineStatus.DEGRADED,
    models.FindingCode.TABLE_EVIDENCE_UNREADABLE: models.PipelineStatus.UNMEASURED,
    models.FindingCode.TABLE_WROTE_NOTHING: models.PipelineStatus.BROKEN,
    models.FindingCode.TABLE_OLDER_THAN_SLO: models.PipelineStatus.BROKEN,
    models.FindingCode.TABLE_NEVER_REFRESHED: models.PipelineStatus.BROKEN,
    models.FindingCode.SCHEMA_BREAKS_CONTRACT: models.PipelineStatus.BROKEN,
    models.FindingCode.SCHEMA_EXCEEDS_CONTRACT: models.PipelineStatus.DEGRADED,
}

# One retry is weather. A second run that needed one is a pattern, and the pattern is the finding.
RETRY_PATTERN_MINIMUM_RUNS = 2


def implied_status(finding: models.Finding) -> models.PipelineStatus:
    status = STATUS_BY_FINDING_CODE.get(finding.code)
    if status is None:
        raise NotImplementedError(f"no status is defined for finding code: {finding.code}")

    return status


def worst_status_among(findings: tuple[models.Finding, ...]) -> models.PipelineStatus:
    implied = {implied_status(finding) for finding in findings}
    for status in STATUS_PRECEDENCE:
        if status in implied:
            return status

    return models.PipelineStatus.HEALTHY


def runs_of_job(runs: models.RunsLog, job: str) -> tuple[models.Run, ...]:
    return tuple(run for run in runs.runs if run.job_name == job)


def describe_attempt(run: models.Run, attempt: models.RunAttempt) -> str:
    return (f"{THE_RUN_LOG}: run_id {run.run_id} attempt {attempt.attempt_number}, "
            f"{attempt.result_state} at {attempt.end_time}")


def never_ran_finding(pipeline: models.Pipeline) -> models.Finding:
    return models.Finding(
        code=models.FindingCode.JOB_DID_NOT_RUN,
        subject=pipeline.id,
        what=f"no run of {pipeline.job} appears in the captured run log",
        why=f"the snapshot holds the last 25 runs of every job it found, and none of them belongs "
            f"to {pipeline.job}, so nothing has written the tables it owns",
        evidence=(
            f"{THE_RUN_LOG}: no run with job_name {pipeline.job}",
            freshness.describe_slo(pipeline),
        ),
    )


def overdue_finding(pipeline: models.Pipeline, run: models.Run, as_of: str) -> models.Finding:
    age = freshness.age_in_hours(run.start_time, as_of)
    return models.Finding(
        code=models.FindingCode.JOB_DID_NOT_RUN,
        subject=pipeline.id,
        what=f"{pipeline.job} last started {age:.1f}h before {as_of}, longer ago than its "
             f"{pipeline.freshness_slo_hours}h SLO allows",
        why=f"its cadence is {pipeline.cadence}, so runs it should have made have not happened. "
            f"Run {run.run_id} is the newest the snapshot holds and it ended {run.result_state}",
        evidence=(
            f"{THE_RUN_LOG}: run_id {run.run_id} started {run.start_time}, {run.result_state}",
            freshness.describe_slo(pipeline),
        ),
    )


def failed_run_finding(pipeline: models.Pipeline, run: models.Run) -> models.Finding:
    latest = run.latest_attempt
    evidence = [describe_attempt(run, attempt) for attempt in run.attempts]
    evidence.append(f"{THE_RUN_LOG}: run_id {run.run_id}, state_message {latest.state_message}")

    attempted = f"{run.retries + 1} attempts" if run.retries else "its only attempt"
    return models.Finding(
        code=models.FindingCode.JOB_RUN_FAILED,
        subject=pipeline.id,
        what=f"the newest run of {pipeline.job} failed",
        why=f"run {run.run_id} failed on {attempted}, the last of them at {latest.end_time}: "
            f"{latest.state_message}",
        evidence=tuple(evidence),
    )


def retry_pattern_finding(
    pipeline: models.Pipeline,
    run: models.Run,
    retried: tuple[models.Run, ...],
    captured: int,
) -> models.Finding:
    failed_attempts = tuple(
        attempt for attempt in run.attempts if attempt.result_state is models.RunResultState.FAILED
    )
    evidence = [describe_attempt(run, attempt) for attempt in run.attempts]
    evidence.extend(
        f"{THE_RUN_LOG}: run_id {run.run_id} attempt {attempt.attempt_number}, state_message "
        f"{attempt.state_message}"
        for attempt in failed_attempts
    )
    evidence.append(
        f"{THE_RUN_LOG}: {len(retried)} of the last {captured} runs of {pipeline.job} needed a retry"
    )

    return models.Finding(
        code=models.FindingCode.JOB_SUCCEEDS_ONLY_ON_RETRY,
        subject=pipeline.id,
        what=f"{pipeline.job} is succeeding only because it is being retried",
        why=f"run {run.run_id} failed {len(failed_attempts)} attempts before succeeding, and "
            f"{len(retried)} of the last {captured} runs did the same. What the attempts failed "
            f"with is in the run log; why it keeps happening is not",
        evidence=tuple(evidence),
    )


def find_run_log_findings(
    pipeline: models.Pipeline,
    runs: models.RunsLog,
    as_of: str,
) -> tuple[models.Finding, ...]:
    captured = runs_of_job(runs, pipeline.job)
    if not captured:
        return (never_ran_finding(pipeline),)

    newest = max(captured, key=lambda run: freshness.parse_timestamp(run.start_time))
    findings: list[models.Finding] = []

    if newest.result_state is models.RunResultState.FAILED:
        findings.append(failed_run_finding(pipeline, newest))
    elif newest.result_state is not models.RunResultState.SUCCESS:
        raise NotImplementedError(f"unhandled result state: {newest.result_state}")

    if freshness.age_in_hours(newest.start_time, as_of) > pipeline.freshness_slo_hours:
        findings.append(overdue_finding(pipeline, newest, as_of))

    retried = tuple(run for run in captured if run.retries > 0)
    if newest.retries > 0 and len(retried) >= RETRY_PATTERN_MINIMUM_RUNS:
        findings.append(retry_pattern_finding(pipeline, newest, retried, len(captured)))

    return tuple(findings)


def assess_pipeline(
    pipeline: models.Pipeline,
    runs: models.RunsLog,
    histories: dict[str, models.TableHistory],
    inherited_findings: tuple[models.Finding, ...],
    as_of: str,
) -> models.AssessedPipeline:
    findings = list(inherited_findings)
    findings.extend(find_run_log_findings(pipeline, runs, as_of))
    for table in pipeline.writes:
        findings.extend(freshness.find_freshness(pipeline, histories[table], as_of))

    return models.AssessedPipeline(
        pipeline=pipeline,
        status=worst_status_among(tuple(findings)),
        findings=tuple(findings),
    )


def assess(
    registry: models.PipelineRegistry,
    runs: models.RunsLog,
    histories: dict[str, models.TableHistory],
    findings: tuple[models.Finding, ...],
    as_of: str,
) -> tuple[models.AssessedPipeline, ...]:
    return tuple(
        assess_pipeline(
            pipeline,
            runs,
            histories,
            # An inherited finding names either the job or the pipeline, depending on which the
            # rule that raised it was looking at. Anything naming neither belongs to the platform.
            tuple(finding for finding in findings
                  if finding.subject in (pipeline.job, pipeline.id)),
            as_of,
        )
        for pipeline in registry.pipelines
    )


def platform_findings(
    registry: models.PipelineRegistry,
    findings: tuple[models.Finding, ...],
) -> tuple[models.Finding, ...]:
    registered = {pipeline.job for pipeline in registry.pipelines}
    registered |= {pipeline.id for pipeline in registry.pipelines}
    return tuple(finding for finding in findings if finding.subject not in registered)
