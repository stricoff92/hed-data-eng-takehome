"""Git is the source of truth for jobs. Anything the workspace does not get from Git is drift."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import cast

from morning_rounds import models

GIT_IS_THE_SOURCE_OF_TRUTH = "repo/docs/platform-standards.md:5-11"

# Distinguishes "the field holds null" from "the field is not there at all", which are different
# kinds of drift and must not collapse into each other.
ABSENT = object()


def describe(value: object) -> str:
    return "absent" if value is ABSENT else json.dumps(value, sort_keys=True)


def settings_differences(
    declared: object,
    deployed: object,
    field: str = "",
) -> Iterator[tuple[str, object, object]]:
    # Captured before the isinstance checks below narrow the parameters. True equals 1 in Python,
    # and 1 equals 1.0, so a value that changed type has drifted even when it compares equal.
    same_type = type(declared) is type(deployed)

    if isinstance(declared, dict) and isinstance(deployed, dict):
        declared_fields = cast(dict[str, object], declared)
        deployed_fields = cast(dict[str, object], deployed)
        for key in sorted(set(declared_fields) | set(deployed_fields)):
            nested = f"{field}.{key}" if field else key
            yield from settings_differences(
                declared_fields.get(key, ABSENT), deployed_fields.get(key, ABSENT), nested
            )
    elif isinstance(declared, list) and isinstance(deployed, list):
        declared_items = cast(list[object], declared)
        deployed_items = cast(list[object], deployed)
        for index in range(max(len(declared_items), len(deployed_items))):
            yield from settings_differences(
                declared_items[index] if index < len(declared_items) else ABSENT,
                deployed_items[index] if index < len(deployed_items) else ABSENT,
                f"{field}[{index}]",
            )
    elif declared != deployed or not same_type:
        yield field, declared, deployed


def undeclared_job_finding(job: models.Job, source: str) -> models.Finding:
    where = f"{source}: job_id {job.job_id}"
    return models.Finding(
        code=models.FindingCode.JOB_NOT_IN_GIT,
        subject=job.name,
        what=f"job {job.name} is deployed in the workspace and is not defined in Git",
        why=f"it was last changed by {job.last_modified_by} at {job.last_modified_at}, and no file in "
            f"repo/databricks/jobs/ declares it, so the workspace cannot be reproduced from main",
        evidence=(
            f"{where}, name {job.name}",
            f"{where}, last_modified {job.last_modified_by} at {job.last_modified_at}",
            f"{where}, git_source {describe(job.settings.get('git_source', ABSENT))}",
            GIT_IS_THE_SOURCE_OF_TRUTH,
        ),
    )


def undeployed_definition_finding(definition: models.JobDefinition) -> models.Finding:
    return models.Finding(
        code=models.FindingCode.JOB_NOT_DEPLOYED,
        subject=definition.name,
        what=f"job {definition.name} is defined in Git and is not deployed in the workspace",
        why="inference: either the definition was never deployed or the job was deleted from the "
            "workspace. The snapshot does not say which, only that the two disagree",
        evidence=(
            f"{definition.source}: name {definition.name}",
            GIT_IS_THE_SOURCE_OF_TRUTH,
        ),
    )


def settings_drift_finding(
    definition: models.JobDefinition,
    job: models.Job,
    source: str,
    differences: tuple[tuple[str, object, object], ...],
) -> models.Finding:
    where = f"{source}: job_id {job.job_id}"
    evidence: list[str] = []
    for field, declared, found in differences:
        evidence.append(f"{definition.source}: {field} = {describe(declared)}")
        evidence.append(f"{where}, {field} = {describe(found)}")
    evidence.append(f"{where}, last_modified {job.last_modified_by} at {job.last_modified_at}")
    evidence.append(GIT_IS_THE_SOURCE_OF_TRUTH)

    fields = ", ".join(field for field, _, _ in differences)
    return models.Finding(
        code=models.FindingCode.JOB_SETTINGS_DIFFER,
        subject=job.name,
        what=f"the deployed settings for {job.name} differ from Git: {fields}",
        why=f"the workspace is a deployment target, not an editing surface. {job.last_modified_by} "
            f"changed the job at {job.last_modified_at}, so a redeploy from main would revert it",
        evidence=tuple(evidence),
    )


def find_drift(
    definitions: tuple[models.JobDefinition, ...],
    deployed: models.JobsSnapshot,
) -> tuple[models.Finding, ...]:
    declared_by_name = {definition.name: definition for definition in definitions}
    deployed_by_name = {job.name: job for job in deployed.jobs}

    findings: list[models.Finding] = []
    for name in sorted(set(declared_by_name) | set(deployed_by_name)):
        definition = declared_by_name.get(name)
        job = deployed_by_name.get(name)

        if definition is None and job is not None:
            findings.append(undeclared_job_finding(job, deployed.source))
        elif job is None and definition is not None:
            findings.append(undeployed_definition_finding(definition))
        elif definition is not None and job is not None:
            differences = tuple(settings_differences(definition.settings, job.settings))
            if differences:
                findings.append(settings_drift_finding(definition, job, deployed.source, differences))
        else:
            raise NotImplementedError(f"{name} is in neither the repository nor the workspace")

    return tuple(findings)
