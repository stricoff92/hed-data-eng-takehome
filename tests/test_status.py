import unittest
from pathlib import Path

from morning_rounds import contracts, drift, loader, models, status

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"

AS_OF = "2026-10-20T11:30:00Z"
A_TABLE = "hed_dataplatform.gold.a_table"
CONCURRENT_APPEND = ("io.delta.exceptions.ConcurrentAppendException: Files were added to partition "
                     "[meeting_date=2026-10-20] by a concurrent update.")


def a_pipeline(writes: tuple[str, ...] = (), slo_hours: float = 26) -> models.Pipeline:
    return models.Pipeline(
        id="a_pipeline",
        job="a_job",
        cadence="daily 06:00 America/New_York",
        cadence_hours=24,
        freshness_slo_hours=slo_hours,
        tier=models.PipelineTier.BUSINESS_FACING,
        owner="data-platform",
        writes=writes,
        reads=(),
    )


def an_attempt(
    run_id: int,
    attempt_number: int,
    result_state: models.RunResultState,
    start_time: str,
    state_message: str = "",
) -> models.RunAttempt:
    return models.RunAttempt(
        job_id=1001,
        job_name="a_job",
        run_id=run_id,
        attempt_number=attempt_number,
        trigger=models.RunTrigger.PERIODIC if attempt_number == 0 else models.RunTrigger.RETRY,
        start_time=start_time,
        end_time=start_time,
        result_state=result_state,
        state_message=state_message,
    )


def a_run(run_id: int, attempts: tuple[models.RunAttempt, ...]) -> models.Run:
    return models.Run(run_id=run_id, job_id=1001, job_name="a_job", attempts=attempts)


def a_successful_run(run_id: int, start_time: str) -> models.Run:
    return a_run(run_id, (an_attempt(run_id, 0, models.RunResultState.SUCCESS, start_time),))


def a_retried_run(run_id: int, start_time: str) -> models.Run:
    return a_run(run_id, (
        an_attempt(run_id, 0, models.RunResultState.FAILED, start_time, CONCURRENT_APPEND),
        an_attempt(run_id, 1, models.RunResultState.SUCCESS, start_time),
    ))


def a_runs_log(runs: tuple[models.Run, ...]) -> models.RunsLog:
    return models.RunsLog(source="workspace/runs.jsonl", runs=runs)


def a_finding(code: models.FindingCode, subject: str) -> models.Finding:
    return models.Finding(code=code, subject=subject, what="what", why="why", evidence=())


class StatusPrecedenceTest(unittest.TestCase):
    def test_a_pipeline_with_nothing_wrong_with_it_is_healthy(self) -> None:
        self.assertEqual(status.worst_status_among(()), models.PipelineStatus.HEALTHY)

    def test_one_broken_finding_outranks_every_softer_one_it_arrives_with(self) -> None:
        findings = (
            a_finding(models.FindingCode.JOB_SETTINGS_DIFFER, "a_job"),
            a_finding(models.FindingCode.TABLE_EVIDENCE_UNREADABLE, "a_pipeline"),
            a_finding(models.FindingCode.JOB_RUN_FAILED, "a_pipeline"),
        )

        self.assertEqual(status.worst_status_among(findings), models.PipelineStatus.BROKEN)

    def test_a_pipeline_nobody_can_measure_is_unmeasured_rather_than_degraded(self) -> None:
        # Reporting degraded would claim the data is fine for now, which is exactly what the
        # missing evidence makes unknowable.
        findings = (
            a_finding(models.FindingCode.JOB_SETTINGS_DIFFER, "a_job"),
            a_finding(models.FindingCode.TABLE_EVIDENCE_UNREADABLE, "a_pipeline"),
        )

        self.assertEqual(status.worst_status_among(findings), models.PipelineStatus.UNMEASURED)

    def test_drift_on_its_own_degrades_a_pipeline_without_breaking_it(self) -> None:
        findings = (a_finding(models.FindingCode.JOB_SETTINGS_DIFFER, "a_job"),)

        self.assertEqual(status.worst_status_among(findings), models.PipelineStatus.DEGRADED)

    def test_every_finding_any_rule_can_emit_has_a_status_it_implies(self) -> None:
        self.assertEqual(set(models.FindingCode), set(status.STATUS_BY_FINDING_CODE))


class JobFindingsTest(unittest.TestCase):
    def test_a_job_with_no_run_in_the_window_is_reported_as_not_having_run(self) -> None:
        findings = status.find_run_log_findings(a_pipeline(), a_runs_log(()), AS_OF)

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.JOB_DID_NOT_RUN])
        self.assertIn("workspace/runs.jsonl: no run with job_name a_job", findings[0].evidence)

    def test_a_job_whose_newest_run_failed_is_reported_with_every_attempt_it_made(self) -> None:
        missing_source = "[TABLE_OR_VIEW_NOT_FOUND] hed_dataplatform.bronze.dataverse_projects"
        failed = a_run(882174, (
            an_attempt(882174, 0, models.RunResultState.FAILED, "2026-10-20T09:30:00Z", missing_source),
            an_attempt(882174, 1, models.RunResultState.FAILED, "2026-10-20T09:33:08Z", missing_source),
        ))

        findings = status.find_run_log_findings(a_pipeline(), a_runs_log((failed,)), AS_OF)

        self.assertEqual([finding.code for finding in findings], [models.FindingCode.JOB_RUN_FAILED])
        self.assertIn("2 attempts", findings[0].why)
        self.assertIn("[TABLE_OR_VIEW_NOT_FOUND]", findings[0].why)
        self.assertEqual(len(findings[0].evidence), 3)

    def test_a_job_that_last_started_longer_ago_than_its_slo_allows_is_overdue(self) -> None:
        stale = a_successful_run(881814, "2026-10-11T08:00:00Z")

        findings = status.find_run_log_findings(a_pipeline(), a_runs_log((stale,)), AS_OF)

        self.assertEqual([finding.code for finding in findings], [models.FindingCode.JOB_DID_NOT_RUN])
        self.assertIn("219.5h", findings[0].what)
        self.assertIn("daily 06:00 America/New_York", findings[0].why)

    def test_a_job_that_ran_on_time_and_succeeded_has_nothing_said_about_it(self) -> None:
        on_time = a_successful_run(882184, "2026-10-20T10:00:00Z")

        self.assertEqual(status.find_run_log_findings(a_pipeline(), a_runs_log((on_time,)), AS_OF), ())

    def test_a_single_retry_is_weather_and_not_worth_reporting(self) -> None:
        once = a_retried_run(882210, "2026-10-20T11:00:00Z")

        self.assertEqual(status.find_run_log_findings(a_pipeline(), a_runs_log((once,)), AS_OF), ())

    def test_a_job_retried_run_after_run_is_reported_with_what_the_attempts_failed_with(self) -> None:
        storm = a_runs_log((
            a_retried_run(882210, "2026-10-20T11:00:00Z"),
            a_retried_run(882202, "2026-10-20T10:30:00Z"),
            a_successful_run(882196, "2026-10-20T10:00:00Z"),
        ))

        findings = status.find_run_log_findings(a_pipeline(), storm, AS_OF)

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.JOB_SUCCEEDS_ONLY_ON_RETRY])
        self.assertIn("2 of the last 3 runs", findings[0].why)
        self.assertTrue(any(CONCURRENT_APPEND in line for line in findings[0].evidence))

    def test_the_newest_run_is_the_one_judged_however_the_log_was_ordered(self) -> None:
        out_of_order = a_runs_log((
            a_successful_run(881814, "2026-10-11T08:00:00Z"),
            a_successful_run(882184, "2026-10-20T10:00:00Z"),
        ))

        self.assertEqual(status.find_run_log_findings(a_pipeline(), out_of_order, AS_OF), ())


class AssessmentTest(unittest.TestCase):
    def test_a_pipeline_owns_the_drift_of_the_job_it_runs_and_nobody_elses(self) -> None:
        registry = models.PipelineRegistry(version=3, pipelines=(a_pipeline(),))
        findings = (
            a_finding(models.FindingCode.JOB_SETTINGS_DIFFER, "a_job"),
            a_finding(models.FindingCode.JOB_NOT_IN_GIT, "somebody_elses_job"),
        )

        assessed = status.assess(
            registry, a_runs_log((a_successful_run(1, "2026-10-20T10:00:00Z"),)), {}, findings, AS_OF
        )

        self.assertEqual(len(assessed), 1)
        self.assertEqual(assessed[0].status, models.PipelineStatus.DEGRADED)
        self.assertEqual([finding.code for finding in assessed[0].findings],
                         [models.FindingCode.JOB_SETTINGS_DIFFER])

    def test_a_finding_against_a_job_no_pipeline_is_registered_against_belongs_to_the_platform(self) -> None:
        registry = models.PipelineRegistry(version=3, pipelines=(a_pipeline(),))
        findings = (
            a_finding(models.FindingCode.JOB_SETTINGS_DIFFER, "a_job"),
            a_finding(models.FindingCode.JOB_NOT_IN_GIT, "mm_segments_backfill"),
        )

        platform = status.platform_findings(registry, findings)

        self.assertEqual([finding.subject for finding in platform], ["mm_segments_backfill"])


class SuppliedSnapshotStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        self.registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)
        runs = loader.load_runs_log(SUPPLIED_FIXTURES)
        histories = {
            table: loader.load_table_history(SUPPLIED_FIXTURES, self.manifest, table)
            for pipeline in self.registry.pipelines for table in pipeline.writes
        }
        governed = loader.load_contracts(SUPPLIED_FIXTURES)
        schemas = {
            contract.table: loader.load_table_schema(SUPPLIED_FIXTURES, self.manifest, contract.table)
            for contract in governed
        }
        self.drift_findings = drift.find_drift(
            loader.load_job_definitions(SUPPLIED_FIXTURES),
            loader.load_jobs_snapshot(SUPPLIED_FIXTURES),
        ) + contracts.find_contract_drift(governed, schemas, self.registry)
        self.assessed = {
            assessed.pipeline.id: assessed
            for assessed in status.assess(
                self.registry, runs, histories, self.drift_findings, self.manifest.captured_at
            )
        }

    def test_every_registered_pipeline_gets_exactly_one_status(self) -> None:
        self.assertEqual(len(self.assessed), len(self.registry.pipelines))
        self.assertEqual(
            {assessed.status for assessed in self.assessed.values()},
            {models.PipelineStatus.BROKEN, models.PipelineStatus.DEGRADED, models.PipelineStatus.HEALTHY,
             models.PipelineStatus.UNMEASURED},
        )

    def test_the_four_sentences_the_brief_refuses_to_let_collapse_each_land_on_one_pipeline(self) -> None:
        def codes(pipeline_id: str) -> list[models.FindingCode]:
            return [finding.code for finding in self.assessed[pipeline_id].findings]

        self.assertIn(models.FindingCode.JOB_RUN_FAILED, codes("dim_projects_daily"))
        self.assertIn(models.FindingCode.JOB_DID_NOT_RUN, codes("dashboard_parity_daily"))
        self.assertIn(models.FindingCode.TABLE_WROTE_NOTHING, codes("workday_bronze_daily"))
        self.assertIn(models.FindingCode.TABLE_EVIDENCE_UNREADABLE,
                      codes("use_case_tracking_scheduled"))

    def test_the_job_that_succeeded_while_writing_nothing_for_three_days_is_broken(self) -> None:
        assessed = self.assessed["workday_bronze_daily"]

        self.assertEqual(assessed.status, models.PipelineStatus.BROKEN)
        self.assertEqual(assessed.pipeline.tier, models.PipelineTier.BUSINESS_FACING)
        # Both tables it writes are empty and stale, so it carries a finding for each.
        self.assertEqual(len(assessed.findings), 4)

    def test_the_pipeline_whose_table_cannot_be_read_is_unmeasured_despite_a_successful_run(self) -> None:
        assessed = self.assessed["use_case_tracking_scheduled"]

        self.assertEqual(assessed.status, models.PipelineStatus.UNMEASURED)
        self.assertEqual([finding.code for finding in assessed.findings],
                         [models.FindingCode.TABLE_EVIDENCE_UNREADABLE])

    def test_the_table_that_lost_a_money_column_breaks_the_pipeline_that_writes_it(self) -> None:
        assessed = self.assessed["deltek_helix_daily_refresh"]

        self.assertEqual(assessed.status, models.PipelineStatus.BROKEN)
        self.assertEqual([finding.code for finding in assessed.findings],
                         [models.FindingCode.SCHEMA_BREAKS_CONTRACT,
                          models.FindingCode.SCHEMA_EXCEEDS_CONTRACT])

    def test_the_hand_downgraded_pipeline_is_degraded_by_its_drift_alone(self) -> None:
        assessed = self.assessed["graph_pipeline_daily"]

        self.assertEqual(assessed.status, models.PipelineStatus.DEGRADED)
        self.assertEqual([finding.code for finding in assessed.findings],
                         [models.FindingCode.JOB_SETTINGS_DIFFER])

    def test_the_retried_pipeline_is_degraded_even_though_its_data_is_fresh(self) -> None:
        assessed = self.assessed["mm_rapid_pipeline_30min"]

        self.assertEqual(assessed.status, models.PipelineStatus.DEGRADED)
        self.assertEqual([finding.code for finding in assessed.findings],
                         [models.FindingCode.JOB_SUCCEEDS_ONLY_ON_RETRY])

    def test_the_paused_pipeline_is_broken_for_three_separate_reasons(self) -> None:
        assessed = self.assessed["dashboard_parity_daily"]

        self.assertEqual(assessed.status, models.PipelineStatus.BROKEN)
        self.assertEqual([finding.code for finding in assessed.findings], [
            models.FindingCode.JOB_SETTINGS_DIFFER,
            models.FindingCode.JOB_DID_NOT_RUN,
            models.FindingCode.TABLE_OLDER_THAN_SLO,
        ])

    def test_the_pipelines_with_nothing_wrong_with_them_are_healthy_and_silent(self) -> None:
        healthy = sorted(
            assessed.pipeline.id for assessed in self.assessed.values()
            if assessed.status is models.PipelineStatus.HEALTHY
        )

        self.assertEqual(healthy, ["gold_dim_employees_daily",
                                   "workday_project_transactions_weekly"])
        for pipeline_id in healthy:
            self.assertEqual(self.assessed[pipeline_id].findings, ())

    def test_the_undeclared_job_is_a_platform_finding_and_degrades_no_pipeline(self) -> None:
        platform = status.platform_findings(self.registry, self.drift_findings)

        self.assertEqual([finding.subject for finding in platform], ["mm_segments_backfill"])
        for assessed in self.assessed.values():
            self.assertNotIn(models.FindingCode.JOB_NOT_IN_GIT,
                             [finding.code for finding in assessed.findings])


if __name__ == "__main__":
    unittest.main()
