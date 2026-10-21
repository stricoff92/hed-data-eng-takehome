"""A governed table's deployed schema must match its contract."""

from __future__ import annotations

from morning_rounds import models

GOVERNED_TABLE_STANDARD = "repo/docs/platform-standards.md:35-39"


def describe_column(column: models.Column | None) -> str:
    if column is None:
        return "absent"

    return f"{column.type} {'nullable' if column.nullable else 'not null'}"


def promised_but_not_deployed(
    contract: models.Contract,
    schema: models.TableSchema,
) -> tuple[tuple[models.Column, models.Column | None], ...]:
    # Compared on name, type and nullability only. A contract column may also carry a note, which
    # documents the column for a reader and is not part of what the table has to deploy.
    deployed = {column.name: column for column in schema.columns}
    broken: list[tuple[models.Column, models.Column | None]] = []
    for promised in contract.columns:
        found = deployed.get(promised.name)
        if found is None or (found.type, found.nullable) != (promised.type, promised.nullable):
            broken.append((promised, found))

    return tuple(broken)


def deployed_but_not_promised(
    contract: models.Contract,
    schema: models.TableSchema,
) -> tuple[models.Column, ...]:
    promised = {column.name for column in contract.columns}
    return tuple(column for column in schema.columns if column.name not in promised)


def unreadable_schema_finding(
    contract: models.Contract,
    schema: models.TableSchema,
    subject: str,
) -> models.Finding:
    return models.Finding(
        code=models.FindingCode.TABLE_EVIDENCE_UNREADABLE,
        subject=subject,
        what=f"the deployed schema of {contract.table} was not captured, so its contract cannot "
             f"be checked",
        why=f"the snapshot could not read the table: {schema.message} The contract may be kept or "
            f"broken; the evidence to say which is missing",
        evidence=(
            f"workspace/manifest.json: {schema.source}, status {schema.status}",
            f"workspace/manifest.json: {schema.source}, message {schema.message}",
            f"{contract.source}: contract_version {contract.contract_version}",
        ),
    )


def contract_broken_finding(
    contract: models.Contract,
    schema: models.TableSchema,
    subject: str,
    broken: tuple[tuple[models.Column, models.Column | None], ...],
) -> models.Finding:
    evidence: list[str] = []
    for promised, found in broken:
        evidence.append(f"{contract.source}: {promised.name} = {describe_column(promised)}")
        evidence.append(f"{schema.source}: {promised.name} = {describe_column(found)}")
    evidence.append(f"{contract.source}: contract_version {contract.contract_version}, "
                    f"owner {contract.owner}")
    evidence.append(GOVERNED_TABLE_STANDARD)

    names = ", ".join(promised.name for promised, _ in broken)
    return models.Finding(
        code=models.FindingCode.SCHEMA_BREAKS_CONTRACT,
        subject=subject,
        what=f"the deployed schema of {contract.table} breaks contract "
             f"v{contract.contract_version}: {names}",
        why=f"the contract is the promise this table makes to its consumers, and {names} "
            f"{'is' if len(broken) == 1 else 'are'} not deployed as it says. Anything reading "
            f"{'that column' if len(broken) == 1 else 'those columns'} by name is reading "
            f"something the contract does not describe",
        evidence=tuple(evidence),
    )


def contract_exceeded_finding(
    contract: models.Contract,
    schema: models.TableSchema,
    subject: str,
    undeclared: tuple[models.Column, ...],
) -> models.Finding:
    evidence = [f"{schema.source}: {column.name} = {describe_column(column)}, not in the contract"
                for column in undeclared]
    evidence.append(f"{contract.source}: contract_version {contract.contract_version}, "
                    f"owner {contract.owner}")
    evidence.append(GOVERNED_TABLE_STANDARD)

    names = ", ".join(column.name for column in undeclared)
    return models.Finding(
        code=models.FindingCode.SCHEMA_EXCEEDS_CONTRACT,
        subject=subject,
        what=f"the deployed schema of {contract.table} has columns contract "
             f"v{contract.contract_version} does not declare: {names}",
        why=f"the data in them is not wrong, but the contract no longer describes the table, so a "
            f"consumer cannot tell from it what {names} holds. The standard requires a change to "
            f"a governed table to ship with an updated contract",
        evidence=tuple(evidence),
    )


def find_contract_drift(
    contract: models.Contract,
    schema: models.TableSchema,
    subject: str,
) -> tuple[models.Finding, ...]:
    if schema.status is models.CaptureStatus.ERROR:
        return (unreadable_schema_finding(contract, schema, subject),)
    elif schema.status is not models.CaptureStatus.OK:
        raise NotImplementedError(f"unhandled capture status: {schema.status}")

    findings: list[models.Finding] = []
    broken = promised_but_not_deployed(contract, schema)
    if broken:
        findings.append(contract_broken_finding(contract, schema, subject, broken))

    undeclared = deployed_but_not_promised(contract, schema)
    if undeclared:
        findings.append(contract_exceeded_finding(contract, schema, subject, undeclared))

    return tuple(findings)


def writing_job(registry: models.PipelineRegistry, table: str) -> str:
    # A finding is carried by the pipeline that writes the table. One nobody writes belongs to the
    # platform, and is named by the table itself.
    written_by = {written: pipeline.job for pipeline in registry.pipelines for written in pipeline.writes}
    return written_by.get(table, table)


def find_all_contract_drift(
    contracts: tuple[models.Contract, ...],
    schemas: dict[str, models.TableSchema],
    registry: models.PipelineRegistry,
) -> tuple[models.Finding, ...]:
    findings: list[models.Finding] = []
    for contract in contracts:
        # A contract file is what makes a table governed, but one that declares itself ungoverned
        # is making no promise to keep.
        if not contract.governed:
            continue
        findings.extend(
            find_contract_drift(contract, schemas[contract.table], writing_job(registry, contract.table))
        )

    return tuple(findings)


def count_violations(
    contracts: tuple[models.Contract, ...],
    schemas: dict[str, models.TableSchema],
) -> dict[str, int]:
    counted: dict[str, int] = {}
    for contract in contracts:
        if not contract.governed:
            continue
        schema = schemas[contract.table]
        if schema.status is not models.CaptureStatus.OK:
            continue
        counted[contract.table] = (len(promised_but_not_deployed(contract, schema))
                                   + len(deployed_but_not_promised(contract, schema)))

    return counted
