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


# FINDINGS (what the rules produce)

class FindingCode(StrEnum):
    """Every code any rule can emit. One registry, so two rules cannot name the same fault twice."""

    JOB_NOT_IN_GIT = "job_deployed_without_a_git_definition"
    JOB_NOT_DEPLOYED = "git_definition_not_deployed"
    JOB_SETTINGS_DIFFER = "deployed_settings_differ_from_git"


@dataclass(frozen=True)
class Finding:
    code: FindingCode
    subject: str
    what: str
    why: str
    evidence: tuple[str, ...]
