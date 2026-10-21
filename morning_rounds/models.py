"""Parsed fixture data. Rules take these, never paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


#
#
# REPO models (source of truth: what should be deployed)

@dataclass(frozen=True)
class Pipeline:
    id: str
    job: str
    cadence: str
    cadence_hours: float
    freshness_slo_hours: float
    tier: int
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


# FINDINGS (what the rules produce)

@dataclass(frozen=True)
class Finding:
    code: str
    subject: str
    what: str
    why: str
    evidence: tuple[str, ...]
