"""The three artifacts the rounds leave behind. Nothing here decides anything."""

from __future__ import annotations

import json
import re
from pathlib import Path

from morning_rounds import freshness, models

JSON_REPORT_FILE_NAME = "report.json"
MARKDOWN_REPORT_FILE_NAME = "report.md"
TELEMETRY_FILE_NAME = "telemetry.ndjson"

GAUGE_PIPELINE_STATUS = "pipeline_status"
GAUGE_PIPELINE_DATA_AGE = "pipeline_data_age_seconds"
GAUGE_PIPELINE_SLO_BREACH = "pipeline_slo_breach"
GAUGE_JOB_DRIFT = "job_definition_drift"
GAUGE_SCHEMA_CONTRACT_VIOLATIONS = "schema_contract_violations"
GAUGE_CLAIMS_CONTRADICTED = "agent_claims_contradicted"

LOG_PIPELINE_FINDING = "pipeline_finding"
LOG_ROUNDS_COMPLETED = "rounds_completed"

KIND_GAUGE = "gauge"
KIND_LOG = "log"

PRESENT = 1
BREACHED = 1
NOT_BREACHED = 0
DRIFTED = 1
NOT_DRIFTED = 0

SECONDS_PER_HOUR = 3600

DRIFT_CODES = (
    models.FindingCode.JOB_NOT_IN_GIT,
    models.FindingCode.JOB_NOT_DEPLOYED,
    models.FindingCode.JOB_SETTINGS_DIFFER,
)
SLO_BREACH_CODES = (
    models.FindingCode.TABLE_OLDER_THAN_SLO,
    models.FindingCode.TABLE_NEVER_REFRESHED,
)

# Worst first: this is read at 07:30 by somebody deciding what to touch.
STATUS_ORDER = (
    models.PipelineStatus.BROKEN,
    models.PipelineStatus.UNMEASURED,
    models.PipelineStatus.DEGRADED,
    models.PipelineStatus.HEALTHY,
)


def finding_as_json(finding: models.Finding) -> dict[str, object]:
    return {
        "code": finding.code.value,
        "what": finding.what,
        "why": finding.why,
        "evidence": list(finding.evidence),
    }


def pipeline_as_json(assessed: models.AssessedPipeline) -> dict[str, object]:
    pipeline = assessed.pipeline
    return {
        "id": pipeline.id,
        "job": pipeline.job,
        "tier": int(pipeline.tier),
        "owner": pipeline.owner,
        "cadence": pipeline.cadence,
        "freshness_slo_hours": pipeline.freshness_slo_hours,
        "writes": list(pipeline.writes),
        "status": assessed.status.value,
        "findings": [finding_as_json(finding) for finding in assessed.findings],
    }


def verdict_as_json(judged: models.JudgedClaim) -> dict[str, object]:
    return {
        "id": judged.claim.id,
        "pipeline": judged.claim.pipeline,
        "claimed_status": judged.claim.status,
        "assertion": judged.claim.assertion,
        "verdict": judged.verdict.value,
        "why": judged.why,
        "evidence": list(judged.evidence),
    }


def counted_by_status(rounds: models.RoundsResult) -> dict[str, int]:
    return {
        status.value: sum(
            1 for assessed in rounds.pipelines if assessed.status is status
        )
        for status in STATUS_ORDER
    }


def counted_by_verdict(rounds: models.RoundsResult) -> dict[str, int]:
    return {
        verdict.value: sum(1 for judged in rounds.verdicts if judged.verdict is verdict)
        for verdict in models.ClaimVerdict
    }


def build_json_report(rounds: models.RoundsResult) -> dict[str, object]:
    return {
        "as_of": rounds.as_of,
        "snapshot": {
            "export": rounds.manifest.export,
            "captured_at": rounds.manifest.captured_at,
            "captured_by": rounds.manifest.captured_by,
            "workspace": rounds.manifest.workspace,
            "files_not_captured": [
                {"path": file.path, "message": file.message}
                for file in rounds.manifest.files
                if file.status is models.CaptureStatus.ERROR
            ],
        },
        "pipelines": [pipeline_as_json(assessed) for assessed in rounds.pipelines],
        "platform_findings": [finding_as_json(finding) for finding in rounds.platform_findings],
        "agent_reconciliation": {
            "agent": rounds.review.agent,
            "agent_version": rounds.review.agent_version,
            "generated_at": rounds.review.generated_at,
            "scope": rounds.review.scope,
            "claims": [verdict_as_json(judged) for judged in rounds.verdicts],
            "pipelines_not_reviewed": list(rounds.unreviewed),
        },
        "counts": {
            "pipelines_by_status": counted_by_status(rounds),
            "claims_by_verdict": counted_by_verdict(rounds),
            "platform_findings": len(rounds.platform_findings),
        },
    }


BACKTICK_RUN = re.compile(r"`+")


def as_inline_code(text: str) -> str:
    # Evidence is quoted verbatim, and a Delta error message can itself contain backticks. A code
    # span has to be fenced by a longer run of them than anything inside it.
    longest = max((len(run.group()) for run in BACKTICK_RUN.finditer(text)), default=0)
    fence = "`" * (longest + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def markdown_finding(finding: models.Finding) -> list[str]:
    lines = [f"**{finding.what}** ({as_inline_code(finding.code)})", "", finding.why, ""]
    lines.extend(f"- {as_inline_code(line)}" for line in finding.evidence)
    lines.append("")
    return lines


def markdown_pipeline(assessed: models.AssessedPipeline) -> list[str]:
    pipeline = assessed.pipeline
    lines = [
        f"### {pipeline.id} — {assessed.status}",
        "",
        f"Tier {int(pipeline.tier)}, owned by {pipeline.owner}, runs {pipeline.cadence}, "
        f"freshness SLO {pipeline.freshness_slo_hours}h, writes {', '.join(pipeline.writes)}.",
        "",
    ]
    for finding in assessed.findings:
        lines.extend(markdown_finding(finding))

    return lines


def build_markdown_report(rounds: models.RoundsResult) -> str:
    not_captured = [
        file for file in rounds.manifest.files if file.status is models.CaptureStatus.ERROR
    ]
    counts = counted_by_status(rounds)
    lines = [
        f"# Morning rounds — {rounds.as_of}",
        "",
        f"Snapshot `{rounds.manifest.export}` of workspace `{rounds.manifest.workspace}`, captured "
        f"by `{rounds.manifest.captured_by}` at {rounds.manifest.captured_at}. "
        f"{len(not_captured)} of {len(rounds.manifest.files)} files could not be read.",
        "",
        f"{counts[models.PipelineStatus.BROKEN.value]} broken, "
        f"{counts[models.PipelineStatus.DEGRADED.value]} degraded, "
        f"{counts[models.PipelineStatus.UNMEASURED.value]} unmeasured, "
        f"{counts[models.PipelineStatus.HEALTHY.value]} healthy.",
        "",
        "## Pipelines",
        "",
        "| Pipeline | Tier | Status | Findings |",
        "|---|---|---|---|",
    ]
    ordered = sorted(
        rounds.pipelines,
        key=lambda assessed: (STATUS_ORDER.index(assessed.status), int(assessed.pipeline.tier)),
    )
    for assessed in ordered:
        lines.append(
            f"| {assessed.pipeline.id} | {int(assessed.pipeline.tier)} | "
            f"**{assessed.status}** | {len(assessed.findings)} |"
        )
    lines.append("")

    for assessed in ordered:
        if assessed.findings:
            lines.extend(markdown_pipeline(assessed))

    healthy = [
        assessed.pipeline.id for assessed in ordered
        if assessed.status is models.PipelineStatus.HEALTHY
    ]
    if healthy:
        lines.extend([
            "### Healthy",
            "",
            f"Nothing to report against {', '.join(healthy)}.",
            "",
        ])

    lines.extend(["## Platform findings", ""])
    if rounds.platform_findings:
        for finding in rounds.platform_findings:
            lines.append(f"### {finding.subject}")
            lines.append("")
            lines.extend(markdown_finding(finding))
    else:
        lines.extend(["None.", ""])

    lines.extend([
        "## Agent reconciliation",
        "",
        f"`{rounds.review.agent}` {rounds.review.agent_version} wrote "
        f"{len(rounds.review.claims)} claims at {rounds.review.generated_at}, scoped to "
        f"{rounds.review.scope}.",
        "",
        "| Claim | Pipeline | Claimed | Verdict |",
        "|---|---|---|---|",
    ])
    for judged in rounds.verdicts:
        lines.append(
            f"| {judged.claim.id} | {judged.claim.pipeline} | {judged.claim.status} | "
            f"**{judged.verdict}** |"
        )
    lines.append("")

    for judged in rounds.verdicts:
        lines.extend([
            f"### {judged.claim.id} {judged.claim.pipeline} — {judged.verdict}",
            "",
            f"Claimed: _{judged.claim.assertion}_",
            "",
            judged.why,
            "",
        ])
        lines.extend(f"- {as_inline_code(line)}" for line in judged.evidence)
        lines.append("")

    unreviewed = ", ".join(rounds.unreviewed) if rounds.unreviewed else "none"
    lines.extend([f"Registered pipelines the agent did not mention: {unreviewed}.", ""])
    return "\n".join(lines)


def gauge_line(rounds: models.RoundsResult, name: str, value: float, labels: dict[str, str]) -> str:
    declared = next((gauge for gauge in rounds.catalog.gauges if gauge.name == name), None)
    if declared is None:
        raise ValueError(f"{name} is not in {rounds.catalog.source}")
    if declared.owner is not models.GaugeOwner.ROUNDS:
        raise ValueError(f"{name} is owned by {declared.owner}, so this tool must not publish it")
    if sorted(labels) != sorted(declared.labels):
        raise ValueError(f"{name} declares labels {list(declared.labels)}, not {sorted(labels)}")

    return json.dumps(
        {"kind": KIND_GAUGE, "name": name, "value": value, "labels": labels, "ts": rounds.as_of}
    )


def log_line(name: str, fields: dict[str, object], as_of: str) -> str:
    return json.dumps({"kind": KIND_LOG, "name": name, "fields": fields, "ts": as_of})


def pipeline_gauges(rounds: models.RoundsResult, assessed: models.AssessedPipeline) -> list[str]:
    pipeline = assessed.pipeline
    tier = str(int(pipeline.tier))
    lines = [gauge_line(rounds, GAUGE_PIPELINE_STATUS, PRESENT,
                        {"pipeline": pipeline.id, "status": assessed.status.value, "tier": tier})]

    # An unmeasured pipeline gets no age and no breach sample at all. A zero here would read as
    # "measured, and fine", which is the one thing the evidence does not say.
    if assessed.status is models.PipelineStatus.UNMEASURED:
        return lines

    for table in pipeline.writes:
        refreshed = freshness.newest_refresh(rounds.histories[table])
        if refreshed is None:
            continue
        age = freshness.age_in_hours(refreshed.timestamp, rounds.as_of) * SECONDS_PER_HOUR
        lines.append(gauge_line(rounds, GAUGE_PIPELINE_DATA_AGE, round(age),
                                {"pipeline": pipeline.id, "table": table, "tier": tier}))

    breached = any(finding.code in SLO_BREACH_CODES for finding in assessed.findings)
    lines.append(gauge_line(rounds, GAUGE_PIPELINE_SLO_BREACH, BREACHED if breached else NOT_BREACHED,
                            {"pipeline": pipeline.id, "tier": tier}))
    return lines


def drift_gauges(rounds: models.RoundsResult) -> list[str]:
    drifted_jobs = {
        finding.subject for finding in rounds.platform_findings if finding.code in DRIFT_CODES
    }
    lines = [
        gauge_line(rounds, GAUGE_JOB_DRIFT, DRIFTED, {"job": job}) for job in sorted(drifted_jobs)
    ]
    for assessed in rounds.pipelines:
        drifted = any(finding.code in DRIFT_CODES for finding in assessed.findings)
        lines.append(gauge_line(rounds, GAUGE_JOB_DRIFT, DRIFTED if drifted else NOT_DRIFTED,
                                {"job": assessed.pipeline.job}))
    return lines


def contract_gauges(rounds: models.RoundsResult) -> list[str]:
    # A governed table whose schema could not be read is absent from the counts, and so gets no
    # sample: a zero would claim its contract was checked and kept.
    return [
        gauge_line(rounds, GAUGE_SCHEMA_CONTRACT_VIOLATIONS, offending, {"table": table})
        for table, offending in sorted(rounds.contract_violations.items())
    ]


def build_telemetry(rounds: models.RoundsResult) -> str:
    lines: list[str] = []
    for assessed in rounds.pipelines:
        lines.extend(pipeline_gauges(rounds, assessed))
    lines.extend(drift_gauges(rounds))
    lines.extend(contract_gauges(rounds))

    contradicted = sum(
        1 for judged in rounds.verdicts if judged.verdict is models.ClaimVerdict.CONTRADICTED
    )
    lines.append(gauge_line(rounds, GAUGE_CLAIMS_CONTRADICTED, contradicted,
                            {"agent": rounds.review.agent}))

    for assessed in rounds.pipelines:
        for finding in assessed.findings:
            lines.append(log_line(LOG_PIPELINE_FINDING, {
                "pipeline": assessed.pipeline.id,
                "tier": int(assessed.pipeline.tier),
                "status": assessed.status.value,
                "code": finding.code.value,
                "what": finding.what,
            }, rounds.as_of))

    counts = counted_by_status(rounds)
    lines.append(log_line(LOG_ROUNDS_COMPLETED, {
        "pipelines": len(rounds.pipelines),
        "broken": counts[models.PipelineStatus.BROKEN.value],
        "degraded": counts[models.PipelineStatus.DEGRADED.value],
        "unmeasured": counts[models.PipelineStatus.UNMEASURED.value],
        "healthy": counts[models.PipelineStatus.HEALTHY.value],
        "platform_findings": len(rounds.platform_findings),
        "claims_contradicted": contradicted,
    }, rounds.as_of))

    return "\n".join(lines) + "\n"


def write_reports(rounds: models.RoundsResult, output_directory: Path) -> tuple[Path, ...]:
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for file_name, body in (
        (JSON_REPORT_FILE_NAME, json.dumps(build_json_report(rounds), indent=2) + "\n"),
        (MARKDOWN_REPORT_FILE_NAME, build_markdown_report(rounds)),
        (TELEMETRY_FILE_NAME, build_telemetry(rounds)),
    ):
        path = output_directory / file_name
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        written.append(path)

    return tuple(written)
