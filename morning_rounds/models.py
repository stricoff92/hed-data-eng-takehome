"""Parsed fixture data. Rules take these, never paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Any


#
#
# REPO models (source of truth: what should be deployed)

class Tier(IntEnum):
    """How urgently a broken pipeline has to be answered, per platform-standards.md:27-33."""

    BUSINESS_FACING = 1
    INTERNAL_TOOLING = 2
    INTERNAL_CHECKS = 3


@dataclass(frozen=True)
class Pipeline:
    id: str
    job: str
    cadence: str
    cadence_hours: float
    freshness_slo_hours: float
    tier: Tier
    owner: str
    writes: tuple[str, ...]
    reads: tuple[str, ...]


@dataclass(frozen=True)
class PipelineRegistry:
    version: int
    pipelines: tuple[Pipeline, ...]


#
#
@dataclass(frozen=True)
class JobDefinition:
    name: str
    # The relative path the definition was read from, as a string, so a finding can cite the file
    # without a rule ever being handed something it could read from disk.
    source: str
    settings: Any


#
#
@dataclass(frozen=True)
class Column:
    """A contract and a deployed schema describe a column the same way. That is what lets them
    be compared at all, so both are parsed into this."""

    name: str
    type: str
    nullable: bool
    note: str | None


@dataclass(frozen=True)
class ContractWriter:
    job: str
    statements: tuple[str, ...]


@dataclass(frozen=True)
class Contract:
    table: str
    governed: bool
    owner: str
    contract_version: str
    source: str
    columns: tuple[Column, ...]
    writers: tuple[ContractWriter, ...]


#
#
@dataclass(frozen=True)
class TableLineage:
    table: str
    built_from: tuple[str, ...]


@dataclass(frozen=True)
class ConsumerRead:
    table: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class Consumer:
    id: str
    name: str
    # Left as declared rather than an enum: the pack documents the field but not its vocabulary,
    # and nothing branches on it. A finding names the consumer, it does not classify it.
    type: str
    owner: str
    refresh: str
    reads: tuple[ConsumerRead, ...]


@dataclass(frozen=True)
class Lineage:
    source: str
    tables: tuple[TableLineage, ...]
    consumers: tuple[Consumer, ...]


# WORKSPACE models (observed snapshot: what is actually deployed, and what it did)

class CaptureStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class CapturedFile:
    path: str
    status: CaptureStatus
    note: str | None
    message: str | None


@dataclass(frozen=True)
class Manifest:
    """What the snapshot captured, and what it could not. The only honest account of its gaps."""

    export: str
    captured_at: str
    captured_by: str
    workspace: str
    source: str
    files: tuple[CapturedFile, ...]


#
#
@dataclass(frozen=True)
class Job:
    job_id: int
    name: str
    creator_user_name: str
    created_time: str
    last_modified_by: str
    last_modified_at: str
    # Kept whole, and unparsed, because the drift check diffs it against the repo definition.
    # Modelling its fields would silently drop whichever ones we had not thought to model.
    settings: Any


@dataclass(frozen=True)
class JobsSnapshot:
    captured_at: str
    source: str
    jobs: tuple[Job, ...]


#
#
class Trigger(StrEnum):
    PERIODIC = "PERIODIC"
    RETRY = "RETRY"


class ResultState(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RunAttempt:
    job_id: int
    job_name: str
    run_id: int
    attempt_number: int
    trigger: Trigger
    start_time: str
    end_time: str
    result_state: ResultState
    state_message: str


@dataclass(frozen=True)
class Run:
    """One run of a job: the scheduled attempt and any retries of it, in attempt order."""

    run_id: int
    job_id: int
    job_name: str
    attempts: tuple[RunAttempt, ...]

    @property
    def latest_attempt(self) -> RunAttempt:
        return self.attempts[-1]

    @property
    def result_state(self) -> ResultState:
        return self.latest_attempt.result_state

    @property
    def start_time(self) -> str:
        return self.attempts[0].start_time

    @property
    def retries(self) -> int:
        return len(self.attempts) - 1


@dataclass(frozen=True)
class RunsLog:
    source: str
    runs: tuple[Run, ...]


#
#
class Operation(StrEnum):
    WRITE = "WRITE"
    MERGE = "MERGE"
    OPTIMIZE = "OPTIMIZE"
    CREATE_OR_REPLACE_TABLE_AS_SELECT = "CREATE OR REPLACE TABLE AS SELECT"


@dataclass(frozen=True)
class TableCommit:
    version: int
    timestamp: str
    user_name: str
    operation: Operation
    parameters: dict[str, str]
    job_id: int
    run_id: int
    metrics: dict[str, int]


@dataclass(frozen=True)
class TableHistory:
    """The commits to one table, newest first.

    A status of ERROR means the snapshot could not read the table: `commits` is empty and `message`
    says why, so a rule can report the pipeline as unmeasured instead of reading an empty history
    as a table nothing has ever written to."""

    table: str
    source: str
    status: CaptureStatus
    message: str | None
    commits: tuple[TableCommit, ...]


@dataclass(frozen=True)
class TableSchema:
    """The deployed columns of one table. Empty with a message when the snapshot could not read it,
    on the same terms as TableHistory."""

    table: str
    source: str
    status: CaptureStatus
    message: str | None
    captured_at: str | None
    columns: tuple[Column, ...]


# REFERENCE models (neither repo nor workspace: what the platform has written down about itself)

class ReviewStatus(StrEnum):
    APPROVED = "Approved"
    NEEDS_REVIEW = "Needs Review"


@dataclass(frozen=True)
class DictionaryEntry:
    data_product: str
    table: str
    field: str
    definition: str
    review_status: ReviewStatus
    business_owner: str
    source: str
    original_upstream_source: str
    # The row this came from, so a finding about a field can cite a file and a line. An empty cell
    # is not missing data: it means nobody has written that value down, which is itself a finding.
    line: int


@dataclass(frozen=True)
class DataDictionary:
    source: str
    entries: tuple[DictionaryEntry, ...]


#
#
class GaugeOwner(StrEnum):
    ROUNDS = "rounds"
    EXTERNAL = "external"
    UNOWNED = "unowned"


@dataclass(frozen=True)
class Gauge:
    name: str
    type: str
    labels: tuple[str, ...]
    owner: GaugeOwner
    description: str


@dataclass(frozen=True)
class GaugeCatalog:
    source: str
    gauges: tuple[Gauge, ...]


# AGENT models (the overnight review, which the tool reconciles against the evidence)

class ClaimEvidenceType(StrEnum):
    RUN = "run"
    RUNS = "runs"


@dataclass(frozen=True)
class ClaimEvidence:
    type: ClaimEvidenceType
    run_id: int | None
    job_id: int | None
    window: str | None


@dataclass(frozen=True)
class Claim:
    id: str
    pipeline: str
    assertion: str
    # The agent's own word for the state it claims, kept verbatim rather than mapped onto a status
    # the platform defines. It says "recovered" and "late", which are not statuses at all, and
    # reconciliation has to pass a verdict on the word it actually used.
    status: str
    evidence: tuple[ClaimEvidence, ...]


@dataclass(frozen=True)
class AgentReview:
    agent: str
    agent_version: str
    generated_at: str
    scope: str
    summary: str
    source: str
    claims: tuple[Claim, ...]


# FINDINGS (what the rules produce)

class Status(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BROKEN = "broken"
    UNMEASURED = "unmeasured"


class FindingCode(StrEnum):
    """Every code any rule can emit. One registry, so two rules cannot name the same fault twice."""

    JOB_NOT_IN_GIT = "job_deployed_without_a_git_definition"
    JOB_NOT_DEPLOYED = "git_definition_not_deployed"
    JOB_SETTINGS_DIFFER = "deployed_settings_differ_from_git"
    JOB_RUN_FAILED = "job_run_failed"
    JOB_DID_NOT_RUN = "job_did_not_run"
    JOB_SUCCEEDS_ONLY_ON_RETRY = "job_succeeds_only_on_retry"
    TABLE_EVIDENCE_UNREADABLE = "table_evidence_could_not_be_read"
    TABLE_WROTE_NOTHING = "table_write_changed_no_data"
    TABLE_OLDER_THAN_SLO = "table_older_than_its_freshness_slo"
    TABLE_NEVER_REFRESHED = "table_has_no_write_that_changed_data"
    SCHEMA_BREAKS_CONTRACT = "deployed_schema_breaks_its_contract"
    SCHEMA_EXCEEDS_CONTRACT = "deployed_schema_has_columns_its_contract_does_not_declare"


@dataclass(frozen=True)
class Finding:
    code: FindingCode
    subject: str
    what: str
    why: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class PipelineStatus:
    pipeline: Pipeline
    status: Status
    findings: tuple[Finding, ...]


class Verdict(StrEnum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class ClaimVerdict:
    claim: Claim
    verdict: Verdict
    why: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Rounds:
    """Everything one morning's rounds established, which is all the writers are allowed to know."""

    as_of: str
    manifest: Manifest
    pipelines: tuple[PipelineStatus, ...]
    platform_findings: tuple[Finding, ...]
    histories: dict[str, TableHistory]
    review: AgentReview
    verdicts: tuple[ClaimVerdict, ...]
    unreviewed: tuple[str, ...]
    catalog: GaugeCatalog
    # Offending columns per governed table, so the telemetry can publish a count it measured
    # rather than one it inferred from prose.
    contract_violations: dict[str, int]
