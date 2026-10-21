import unittest
from pathlib import Path

from morning_rounds import contracts, loader, models, status

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"

A_TABLE = "hed_dataplatform.gold.a_table"
A_SUBJECT = "a_job"


def a_column(name: str, type_: str = "STRING", nullable: bool = True,
             note: str | None = None) -> models.TableColumn:
    return models.TableColumn(name=name, type=type_, nullable=nullable, note=note)


def a_contract(columns: tuple[models.TableColumn, ...], governed: bool = True) -> models.Contract:
    return models.Contract(
        table=A_TABLE,
        governed=governed,
        owner="data-platform",
        contract_version="1.2.0",
        source="repo/contracts/gold.a_table.json",
        columns=columns,
        writers=(models.ContractWriter(job=A_SUBJECT, statements=("WRITE (overwrite)",)),),
    )


def a_deployed_schema(
    columns: tuple[models.TableColumn, ...],
    capture_status: models.CaptureStatus = models.CaptureStatus.OK,
    message: str | None = None,
) -> models.TableSchema:
    return models.TableSchema(
        table=A_TABLE,
        source=f"workspace/tables/{A_TABLE}/schema.json",
        status=capture_status,
        message=message,
        captured_at="2026-10-20T11:30:00Z",
        columns=columns,
    )


class ContractComparisonTest(unittest.TestCase):
    def test_a_table_deployed_exactly_as_its_contract_promises_is_not_a_finding(self) -> None:
        columns = (a_column("project_id", nullable=False), a_column("gross_fee", "DECIMAL(18,2)"))

        findings = contracts.find_contract_drift_in_table(
            a_contract(columns), a_deployed_schema(columns), A_SUBJECT
        )

        self.assertEqual(findings, ())

    def test_a_column_the_contract_notes_still_matches_a_deployed_column_without_one(self) -> None:
        # The note documents the column for a reader. It is not something the table deploys.
        promised = (a_column("period", nullable=False, note="YYYY-MM"),)
        deployed = (a_column("period", nullable=False),)

        self.assertEqual(contracts.find_contract_drift_in_table(
            a_contract(promised), a_deployed_schema(deployed), A_SUBJECT), ())

    def test_a_promised_column_that_is_not_deployed_breaks_the_contract(self) -> None:
        promised = (a_column("net_fee", "DECIMAL(18,2)"),)

        findings = contracts.find_contract_drift_in_table(
            a_contract(promised), a_deployed_schema(()), A_SUBJECT
        )

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.SCHEMA_BREAKS_CONTRACT])
        self.assertIn("net_fee", findings[0].what)
        self.assertIn("repo/contracts/gold.a_table.json: net_fee = DECIMAL(18,2) nullable",
                      findings[0].evidence)
        self.assertTrue(any("net_fee = absent" in line for line in findings[0].evidence))

    def test_a_column_deployed_with_a_different_type_breaks_the_contract(self) -> None:
        promised = (a_column("net_fee", "DECIMAL(18,2)"),)
        deployed = (a_column("net_fee", "DOUBLE"),)

        findings = contracts.find_contract_drift_in_table(
            a_contract(promised), a_deployed_schema(deployed), A_SUBJECT
        )

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.SCHEMA_BREAKS_CONTRACT])
        self.assertTrue(any("DECIMAL(18,2)" in line for line in findings[0].evidence))
        self.assertTrue(any("DOUBLE" in line for line in findings[0].evidence))

    def test_a_column_that_quietly_became_nullable_breaks_the_contract_too(self) -> None:
        promised = (a_column("project_id", nullable=False),)
        deployed = (a_column("project_id", nullable=True),)

        findings = contracts.find_contract_drift_in_table(
            a_contract(promised), a_deployed_schema(deployed), A_SUBJECT
        )

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.SCHEMA_BREAKS_CONTRACT])
        self.assertTrue(any("not null" in line for line in findings[0].evidence))

    def test_an_extra_deployed_column_is_reported_apart_from_a_broken_promise(self) -> None:
        promised = (a_column("project_id", nullable=False),)
        deployed = (a_column("project_id", nullable=False), a_column("net_fee_usd", "DOUBLE"))

        findings = contracts.find_contract_drift_in_table(
            a_contract(promised), a_deployed_schema(deployed), A_SUBJECT
        )

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.SCHEMA_EXCEEDS_CONTRACT])
        self.assertIn("net_fee_usd", findings[0].what)

    def test_a_renamed_column_is_reported_as_both_a_broken_promise_and_an_undeclared_column(self) -> None:
        promised = (a_column("net_fee", "DECIMAL(18,2)"),)
        deployed = (a_column("net_fee_usd", "DOUBLE"),)

        findings = contracts.find_contract_drift_in_table(
            a_contract(promised), a_deployed_schema(deployed), A_SUBJECT
        )

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.SCHEMA_BREAKS_CONTRACT,
                          models.FindingCode.SCHEMA_EXCEEDS_CONTRACT])

    def test_a_schema_the_snapshot_could_not_read_leaves_the_contract_unchecked(self) -> None:
        denied = "PERMISSION_DENIED: User does not have SELECT on Table 'a_table'."
        unreadable = a_deployed_schema((), models.CaptureStatus.ERROR, denied)

        findings = contracts.find_contract_drift_in_table(
            a_contract((a_column("project_id"),)), unreadable, A_SUBJECT
        )

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.TABLE_EVIDENCE_UNREADABLE])
        self.assertIn(denied, findings[0].why)

    def test_a_contract_that_declares_itself_ungoverned_makes_no_promise_to_keep(self) -> None:
        promised = a_contract((a_column("net_fee", "DECIMAL(18,2)"),), governed=False)
        registry = models.PipelineRegistry(version=3, pipelines=())

        findings = contracts.find_contract_drift(
            (promised,), {A_TABLE: a_deployed_schema(())}, registry
        )

        self.assertEqual(findings, ())


class SuppliedSnapshotContractTest(unittest.TestCase):
    def setUp(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        self.registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)
        self.contracts = loader.load_contracts(SUPPLIED_FIXTURES)
        self.schemas = {
            contract.table: loader.load_table_schema(SUPPLIED_FIXTURES, manifest, contract.table)
            for contract in self.contracts
        }
        self.findings = contracts.find_contract_drift(
            self.contracts, self.schemas, self.registry
        )

    def test_the_financials_table_lost_a_decimal_money_column_and_gained_a_float_one(self) -> None:
        broken = next(f for f in self.findings
                      if f.code is models.FindingCode.SCHEMA_BREAKS_CONTRACT)
        exceeded = next(f for f in self.findings
                        if f.code is models.FindingCode.SCHEMA_EXCEEDS_CONTRACT)

        self.assertIn("net_fee, fee_currency", broken.what)
        self.assertIn("v1.2.0", broken.what)
        self.assertIn("net_fee_usd", exceeded.what)
        self.assertTrue(any("net_fee = DECIMAL(18,2) nullable" in line for line in broken.evidence))
        self.assertTrue(any("net_fee_usd = DOUBLE nullable" in line for line in exceeded.evidence))

    def test_the_only_other_governed_table_keeps_its_contract_exactly(self) -> None:
        self.assertEqual(
            {finding.subject for finding in self.findings}, {"deltek_helix_daily_refresh"}
        )
        self.assertEqual(contracts.count_violations(self.contracts, self.schemas),
                         {"hed_dataplatform.gold.dim_projects": 0,
                          "hed_dataplatform.gold.fact_project_financials": 3})

    def test_the_finding_is_carried_by_the_pipeline_that_writes_the_table(self) -> None:
        # The contract names deltek_helix_daily_refresh as the writer, and the registry agrees.
        self.assertEqual(
            contracts.writing_job(self.registry, "hed_dataplatform.gold.fact_project_financials"),
            "deltek_helix_daily_refresh",
        )
        self.assertEqual(status.platform_findings(self.registry, self.findings), ())


if __name__ == "__main__":
    unittest.main()
