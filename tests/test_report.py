import json
import unittest
from pathlib import Path
from typing import Any

from morning_rounds import contracts, drift, loader, models, reconcile, report, status

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"


def rounds_for_the_supplied_snapshot() -> models.Rounds:
    manifest = loader.load_manifest(SUPPLIED_FIXTURES)
    registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)
    runs = loader.load_runs_log(SUPPLIED_FIXTURES)
    histories = {
        table: loader.load_table_history(SUPPLIED_FIXTURES, manifest, table)
        for pipeline in registry.pipelines for table in pipeline.writes
    }
    governed = loader.load_contracts(SUPPLIED_FIXTURES)
    schemas = {
        contract.table: loader.load_table_schema(SUPPLIED_FIXTURES, manifest, contract.table)
        for contract in governed
    }
    findings = drift.find_drift(
        loader.load_job_definitions(SUPPLIED_FIXTURES),
        loader.load_jobs_snapshot(SUPPLIED_FIXTURES),
    ) + contracts.find_all_contract_drift(governed, schemas, registry)
    assessed = status.assess(registry, runs, histories, findings, manifest.captured_at)
    review = loader.load_agent_review(SUPPLIED_FIXTURES)
    return models.Rounds(
        as_of=manifest.captured_at,
        manifest=manifest,
        pipelines=assessed,
        platform_findings=status.platform_findings(registry, findings),
        histories=histories,
        review=review,
        verdicts=reconcile.reconcile(review, assessed, runs),
        unreviewed=reconcile.unreviewed_pipelines(review, registry),
        catalog=loader.load_gauge_catalog(SUPPLIED_FIXTURES),
        contract_violations=contracts.count_violations(governed, schemas),
    )


class TelemetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rounds = rounds_for_the_supplied_snapshot()
        self.samples: list[Any] = [
            json.loads(line) for line in report.build_telemetry(self.rounds).splitlines()
        ]

    def gauges_named(self, name: str) -> list[Any]:
        return [s for s in self.samples if s["kind"] == "gauge" and s["name"] == name]

    def test_a_pipeline_nobody_can_measure_publishes_no_age_and_no_breach_at_all(self) -> None:
        unmeasured = "use_case_tracking_scheduled"

        published = {
            sample["name"] for sample in self.samples
            if sample["kind"] == "gauge" and sample["labels"].get("pipeline") == unmeasured
        }

        # A zero here would read as measured and fine, which is the one thing we cannot say.
        self.assertEqual(published, {report.GAUGE_PIPELINE_STATUS})

    def test_a_pipeline_that_was_measured_and_is_within_its_slo_publishes_a_real_zero(self) -> None:
        breaches = {
            sample["labels"]["pipeline"]: sample["value"]
            for sample in self.gauges_named(report.GAUGE_PIPELINE_SLO_BREACH)
        }

        self.assertEqual(breaches["gold_dim_employees_daily"], 0)
        self.assertEqual(breaches["workday_bronze_daily"], 1)
        self.assertNotIn("use_case_tracking_scheduled", breaches)

    def test_a_governed_table_that_keeps_its_contract_publishes_a_measured_zero(self) -> None:
        counted = {
            sample["labels"]["table"]: sample["value"]
            for sample in self.gauges_named(report.GAUGE_SCHEMA_CONTRACT_VIOLATIONS)
        }

        self.assertEqual(counted["hed_dataplatform.gold.dim_projects"], 0)
        self.assertEqual(counted["hed_dataplatform.gold.fact_project_financials"], 3)
        # The ungoverned tables have no contract to keep, so they are not counted at all.
        self.assertEqual(len(counted), 2)

    def test_nothing_another_producer_owns_is_ever_republished(self) -> None:
        published = {sample["name"] for sample in self.samples if sample["kind"] == "gauge"}
        not_ours = {
            gauge.name for gauge in self.rounds.catalog.gauges
            if gauge.owner is not models.GaugeOwner.ROUNDS
        }

        self.assertEqual(published & not_ours, set())

    def test_publishing_a_gauge_another_producer_owns_is_refused_outright(self) -> None:
        with self.assertRaises(ValueError) as raised:
            report.gauge_line(self.rounds, "databricks_job_duration_seconds", 1, {"job": "a_job"})

        self.assertIn("is owned by", str(raised.exception))

    def test_publishing_a_gauge_with_labels_the_catalog_does_not_declare_is_refused(self) -> None:
        with self.assertRaises(ValueError) as raised:
            report.gauge_line(self.rounds, report.GAUGE_PIPELINE_SLO_BREACH, 1, {"pipeline": "a"})

        self.assertIn("declares labels", str(raised.exception))

    def test_every_sample_is_stamped_with_the_as_of_instant_and_not_the_wall_clock(self) -> None:
        self.assertTrue(all(sample["ts"] == self.rounds.as_of for sample in self.samples))

    def test_the_run_is_summarised_in_one_log_event_a_dashboard_can_count(self) -> None:
        completed = [s for s in self.samples if s["name"] == report.LOG_ROUNDS_COMPLETED]

        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["fields"]["broken"], 4)
        self.assertEqual(completed[0]["fields"]["claims_contradicted"], 6)


class WrittenReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rounds = rounds_for_the_supplied_snapshot()

    def test_the_json_report_carries_every_pipeline_with_its_findings_and_provenance(self) -> None:
        # Read back through json, because what the panel reads is the serialised file.
        document: Any = json.loads(json.dumps(report.build_json_report(self.rounds)))

        self.assertEqual(document["as_of"], "2026-10-20T11:30:00Z")
        self.assertEqual(len(document["pipelines"]), 9)
        self.assertEqual(document["counts"]["pipelines_by_status"],
                         {"broken": 4, "unmeasured": 1, "degraded": 2, "healthy": 2})
        self.assertEqual(len(document["snapshot"]["files_not_captured"]), 2)

    def test_the_json_report_survives_a_round_trip_through_json(self) -> None:
        written = json.dumps(report.build_json_report(self.rounds))

        self.assertEqual(json.loads(written)["counts"]["claims_by_verdict"],
                         {"verified": 1, "contradicted": 6, "unverifiable": 1})

    def test_the_markdown_report_leads_with_what_is_broken(self) -> None:
        body = report.build_markdown_report(self.rounds)
        rows = [line for line in body.splitlines() if line.startswith("| ")]

        self.assertIn("# Morning rounds — 2026-10-20T11:30:00Z", body)
        # rows[0] is the header; the first pipeline listed is the worst one.
        self.assertIn("workday_bronze_daily", rows[1])
        self.assertIn("**broken**", rows[1])
        self.assertIn("Registered pipelines the agent did not mention: dashboard_parity_daily.", body)

    def test_all_three_artifacts_are_written_where_they_were_asked_for(self) -> None:
        output_directory = Path(__file__).resolve().parent / "written-by-the-tests"

        written = report.write_reports(self.rounds, output_directory)

        try:
            self.assertEqual([path.name for path in written],
                             ["report.json", "report.md", "telemetry.ndjson"])
            for path in written:
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
        finally:
            for path in written:
                path.unlink()
            output_directory.rmdir()


if __name__ == "__main__":
    unittest.main()
