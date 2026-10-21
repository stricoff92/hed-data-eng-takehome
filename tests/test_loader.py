import unittest
from pathlib import Path

from morning_rounds import loader, models

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"

MM_RAPID_PIPELINE = {
    "id": "mm_rapid_pipeline_30min",
    "job": "mm_rapid_pipeline_30min",
    "cadence": "every 30 minutes",
    "cadence_hours": 0.5,
    "freshness_slo_hours": 2,
    "tier": 1,
    "owner": "data-platform",
    "writes": ["meeting_minutes.silver.meeting_segments"],
    "reads": ["hed_dataplatform.silver.graph_meeting_events", "Fireflies transcripts"],
}

RAPID_PIPELINE_FIRST_ATTEMPT = {
    "job_id": 1007,
    "job_name": "mm_rapid_pipeline_30min",
    "run_id": 882210,
    "attempt": 0,
    "trigger": "PERIODIC",
    "start_time": "2026-10-20T11:00:00Z",
    "end_time": "2026-10-20T11:03:49Z",
    "result_state": "FAILED",
    "state_message": "io.delta.exceptions.ConcurrentAppendException: Files were added to partition "
                     "[meeting_date=2026-10-20] by a concurrent update. Please try the operation again.",
}


USECASE_REGISTRY_HISTORY = Path("workspace/tables/hed_dataplatform.gold.usecase_registry/history.jsonl")

PERMISSION_DENIED_CAPTURE = {
    "path": USECASE_REGISTRY_HISTORY.as_posix(),
    "status": "error",
    "message": "PERMISSION_DENIED: User does not have SELECT on Table "
               "'hed_dataplatform.gold.usecase_registry'.",
}


class PipelineRegistryTest(unittest.TestCase):
    def test_the_supplied_registry_loads_every_pipeline_the_platform_has_declared(self) -> None:
        registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)

        self.assertEqual(registry.version, 3)
        self.assertEqual(len(registry.pipelines), 9)

    def test_a_pipeline_keeps_the_cadence_and_slo_it_was_registered_with(self) -> None:
        registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)
        by_id = {pipeline.id: pipeline for pipeline in registry.pipelines}

        rapid = by_id["mm_rapid_pipeline_30min"]
        self.assertEqual(rapid.cadence_hours, 0.5)
        self.assertEqual(rapid.freshness_slo_hours, 2)
        self.assertEqual(rapid.tier, models.Tier.BUSINESS_FACING)

        weekly = by_id["workday_project_transactions_weekly"]
        self.assertEqual(weekly.cadence_hours, 168)
        self.assertEqual(weekly.freshness_slo_hours, 192)

    def test_a_sub_hourly_cadence_survives_as_a_fraction_rather_than_rounding_to_zero(self) -> None:
        pipeline = loader.parse_pipeline(MM_RAPID_PIPELINE)

        self.assertEqual(pipeline.cadence_hours, 0.5)

    def test_the_tables_a_pipeline_writes_and_reads_stay_in_their_registered_order(self) -> None:
        registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)
        bronze = next(p for p in registry.pipelines if p.id == "workday_bronze_daily")

        self.assertEqual(
            bronze.writes,
            ("hed_dataplatform.bronze.workday_workers", "hed_dataplatform.silver.workday_workers"),
        )
        self.assertEqual(bronze.reads, ("Workday RaaS: Worker_Snapshot",))

    def test_a_pipeline_missing_its_freshness_slo_is_refused_rather_than_defaulted(self) -> None:
        incomplete = {key: value for key, value in MM_RAPID_PIPELINE.items()
                      if key != "freshness_slo_hours"}

        with self.assertRaises(KeyError):
            loader.parse_pipeline(incomplete)

    def test_a_pipeline_registered_at_a_tier_the_standards_do_not_define_is_refused(self) -> None:
        off_the_scale = {**MM_RAPID_PIPELINE, "tier": 4}

        with self.assertRaises(ValueError):
            loader.parse_pipeline(off_the_scale)

    def test_pointing_the_loader_at_a_directory_with_no_registry_names_the_file_it_wanted(self) -> None:
        with self.assertRaises(loader.FixtureError) as raised:
            loader.load_pipeline_registry(REPOSITORY_ROOT)

        self.assertIn("pipelines.json", str(raised.exception))
        self.assertIn("is missing", str(raised.exception))


class JobDefinitionsTest(unittest.TestCase):
    def test_every_job_definition_the_repository_holds_is_loaded_in_a_stable_order(self) -> None:
        definitions = loader.load_job_definitions(SUPPLIED_FIXTURES)
        names = [definition.name for definition in definitions]

        self.assertEqual(len(definitions), 10)
        self.assertEqual(names, sorted(names))

    def test_a_definition_cites_the_repository_file_it_was_read_from(self) -> None:
        definitions = loader.load_job_definitions(SUPPLIED_FIXTURES)
        by_name = {definition.name: definition for definition in definitions}

        self.assertEqual(
            by_name["workday_bronze_daily"].source,
            "repo/databricks/jobs/workday_bronze_daily.json",
        )

    def test_the_declared_settings_are_kept_whole_so_the_drift_check_can_diff_them(self) -> None:
        definitions = loader.load_job_definitions(SUPPLIED_FIXTURES)
        by_name = {definition.name: definition for definition in definitions}

        declared = by_name["dashboard_parity_daily"].settings
        self.assertEqual(declared["schedule"]["pause_status"], "UNPAUSED")
        self.assertIn("git_source", declared)

    def test_the_repository_declares_a_maintenance_job_that_the_registry_does_not_register(self) -> None:
        definitions = loader.load_job_definitions(SUPPLIED_FIXTURES)
        registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)

        declared = {definition.name for definition in definitions}
        registered = {pipeline.job for pipeline in registry.pipelines}

        self.assertIn("table_maintenance_nightly", declared)
        self.assertNotIn("table_maintenance_nightly", registered)


class ManifestTest(unittest.TestCase):
    def test_the_manifest_says_when_the_snapshot_was_taken_and_who_took_it(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        self.assertEqual(manifest.captured_at, "2026-10-20T11:30:00Z")
        self.assertEqual(manifest.captured_by, "svc-platform-snapshot@hed.example")
        self.assertEqual(manifest.export, "platform-snapshot")
        self.assertEqual(manifest.source, "workspace/manifest.json")
        self.assertEqual(len(manifest.files), 22)

    def test_the_snapshot_captured_every_file_it_tried_but_two_of_them_failed(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        failed = [file for file in manifest.files if file.status is models.CaptureStatus.ERROR]

        self.assertEqual(len(failed), 2)
        self.assertEqual(
            sorted(file.path for file in failed),
            [
                "workspace/tables/hed_dataplatform.gold.usecase_registry/history.jsonl",
                "workspace/tables/hed_dataplatform.gold.usecase_registry/schema.json",
            ],
        )

    def test_a_file_the_snapshot_could_not_read_carries_the_reason_it_could_not(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        unreadable = loader.captured_file(manifest, USECASE_REGISTRY_HISTORY)

        self.assertEqual(unreadable.status, models.CaptureStatus.ERROR)
        self.assertIn("PERMISSION_DENIED", str(unreadable.message))
        self.assertIn("does not have SELECT", str(unreadable.message))

    def test_a_file_the_snapshot_read_cleanly_offers_no_reason_because_there_is_none(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        readable = loader.captured_file(manifest, loader.RUNS_RELATIVE_PATH)

        self.assertEqual(readable.status, models.CaptureStatus.OK)
        self.assertIsNone(readable.message)
        self.assertIn("one line per attempt", str(readable.note))

    def test_every_table_the_registry_declares_a_pipeline_writes_was_accounted_for(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)

        for pipeline in registry.pipelines:
            for table in pipeline.writes:
                history = Path(f"workspace/tables/{table}/history.jsonl")
                self.assertEqual(loader.captured_file(manifest, history).path, history.as_posix())

    def test_asking_about_a_file_the_snapshot_never_exported_is_refused_not_assumed_fine(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        never_exported = Path("workspace/tables/hed_dataplatform.gold.invented/history.jsonl")

        with self.assertRaises(loader.FixtureError) as raised:
            loader.captured_file(manifest, never_exported)

        self.assertIn("does not list", str(raised.exception))
        self.assertIn("hed_dataplatform.gold.invented", str(raised.exception))

    def test_a_capture_the_manifest_claims_failed_without_saying_why_is_refused(self) -> None:
        unexplained = {key: value for key, value in PERMISSION_DENIED_CAPTURE.items()
                       if key != "message"}

        with self.assertRaises(KeyError):
            loader.parse_captured_file(unexplained)

    def test_a_capture_status_the_snapshot_format_does_not_document_is_refused(self) -> None:
        half_read = {**PERMISSION_DENIED_CAPTURE, "status": "truncated"}

        with self.assertRaises(ValueError):
            loader.parse_captured_file(half_read)

    def test_pointing_the_loader_at_a_directory_with_no_manifest_names_the_file_it_wanted(self) -> None:
        with self.assertRaises(loader.FixtureError) as raised:
            loader.load_manifest(REPOSITORY_ROOT)

        self.assertIn("manifest.json", str(raised.exception))
        self.assertIn("is missing", str(raised.exception))


class DeployedJobsTest(unittest.TestCase):
    def test_the_snapshot_loads_every_job_the_workspace_had_deployed_at_the_as_of_instant(self) -> None:
        snapshot = loader.load_jobs_snapshot(SUPPLIED_FIXTURES)

        self.assertEqual(snapshot.captured_at, "2026-10-20T11:30:00Z")
        self.assertEqual(len(snapshot.jobs), 11)

    def test_a_job_is_keyed_by_the_name_the_registry_refers_to_it_by(self) -> None:
        snapshot = loader.load_jobs_snapshot(SUPPLIED_FIXTURES)
        by_name = {job.name: job for job in snapshot.jobs}

        self.assertEqual(by_name["workday_bronze_daily"].job_id, 1001)
        self.assertEqual(by_name["mm_rapid_pipeline_30min"].job_id, 1007)

    def test_deployed_settings_are_kept_whole_so_the_drift_check_can_diff_them(self) -> None:
        snapshot = loader.load_jobs_snapshot(SUPPLIED_FIXTURES)
        by_name = {job.name: job for job in snapshot.jobs}

        from_git = by_name["workday_bronze_daily"].settings
        self.assertEqual(from_git["schedule"]["pause_status"], "UNPAUSED")
        self.assertIn("git_source", from_git)

        # The job nobody deployed from Git has no git_source to deploy it from.
        hand_made = by_name["mm_segments_backfill"].settings
        self.assertNotIn("git_source", hand_made)

    def test_the_principal_that_last_touched_a_job_is_carried_so_a_hand_edit_is_visible(self) -> None:
        snapshot = loader.load_jobs_snapshot(SUPPLIED_FIXTURES)
        by_name = {job.name: job for job in snapshot.jobs}

        deployed_by_ci = by_name["workday_bronze_daily"]
        self.assertEqual(deployed_by_ci.last_modified_by, "ci-deploy@hed.example")

        paused_by_hand = by_name["dashboard_parity_daily"]
        self.assertEqual(paused_by_hand.last_modified_by, "r.chen@hed.example")
        self.assertEqual(paused_by_hand.last_modified_at, "2026-10-11T14:02:00Z")


class RunsLogTest(unittest.TestCase):
    def test_every_attempt_in_the_log_is_grouped_into_the_run_it_was_an_attempt_of(self) -> None:
        log = loader.load_runs_log(SUPPLIED_FIXTURES)

        self.assertEqual(log.source, "workspace/runs.jsonl")
        self.assertEqual(len(log.runs), 259)
        self.assertEqual(sum(len(run.attempts) for run in log.runs), 278)

    def test_a_run_that_succeeded_only_after_two_retries_reports_the_latest_attempt(self) -> None:
        log = loader.load_runs_log(SUPPLIED_FIXTURES)
        by_run_id = {run.run_id: run for run in log.runs}

        retried = by_run_id[882210]
        self.assertEqual(retried.job_name, "mm_rapid_pipeline_30min")
        self.assertEqual(retried.retries, 2)
        self.assertEqual(retried.result_state, models.ResultState.SUCCESS)
        self.assertEqual(retried.latest_attempt.attempt_number, 2)

    def test_the_attempts_of_a_run_arrive_in_attempt_order_though_the_file_lists_them_newest_first(
        self,
    ) -> None:
        log = loader.load_runs_log(SUPPLIED_FIXTURES)
        by_run_id = {run.run_id: run for run in log.runs}

        retried = by_run_id[882210]
        self.assertEqual([attempt.attempt_number for attempt in retried.attempts], [0, 1, 2])
        self.assertEqual(
            [attempt.result_state for attempt in retried.attempts],
            [models.ResultState.FAILED, models.ResultState.FAILED, models.ResultState.SUCCESS],
        )
        self.assertEqual(
            [attempt.trigger for attempt in retried.attempts],
            [models.Trigger.PERIODIC, models.Trigger.RETRY, models.Trigger.RETRY],
        )

    def test_a_run_is_timed_from_when_it_was_scheduled_rather_than_from_its_last_retry(self) -> None:
        log = loader.load_runs_log(SUPPLIED_FIXTURES)
        by_run_id = {run.run_id: run for run in log.runs}

        retried = by_run_id[882210]
        self.assertEqual(retried.start_time, "2026-10-20T11:00:00Z")
        self.assertEqual(retried.latest_attempt.end_time, "2026-10-20T11:13:49Z")

    def test_a_run_whose_retry_failed_too_keeps_the_error_every_attempt_reported(self) -> None:
        log = loader.load_runs_log(SUPPLIED_FIXTURES)
        by_run_id = {run.run_id: run for run in log.runs}

        exhausted = by_run_id[882174]
        self.assertEqual(exhausted.job_name, "dim_projects_daily")
        self.assertEqual(exhausted.result_state, models.ResultState.FAILED)
        self.assertEqual(exhausted.retries, 1)
        for attempt in exhausted.attempts:
            self.assertIn("TABLE_OR_VIEW_NOT_FOUND", attempt.state_message)
            self.assertIn("hed_dataplatform.bronze.dataverse_projects", attempt.state_message)

    def test_a_run_that_succeeded_first_time_needed_no_retries_and_says_nothing_went_wrong(self) -> None:
        log = loader.load_runs_log(SUPPLIED_FIXTURES)
        by_run_id = {run.run_id: run for run in log.runs}

        clean = by_run_id[882213]
        self.assertEqual(clean.job_name, "use_case_tracking_scheduled")
        self.assertEqual(clean.retries, 0)
        self.assertEqual(clean.result_state, models.ResultState.SUCCESS)
        self.assertEqual(clean.latest_attempt.state_message, "")

    def test_the_runs_stay_newest_first_as_the_jobs_api_returned_them(self) -> None:
        log = loader.load_runs_log(SUPPLIED_FIXTURES)

        self.assertEqual(log.runs[0].run_id, 882210)
        self.assertEqual(log.runs[-1].run_id, 881205)
        self.assertEqual(log.runs[-1].start_time, "2026-04-29T09:00:00Z")

    def test_an_attempt_is_keyed_by_the_job_the_registry_refers_to_it_by(self) -> None:
        attempt = loader.parse_run_attempt(RAPID_PIPELINE_FIRST_ATTEMPT)

        self.assertEqual(attempt.job_id, 1007)
        self.assertEqual(attempt.job_name, "mm_rapid_pipeline_30min")
        self.assertEqual(attempt.run_id, 882210)
        self.assertEqual(attempt.attempt_number, 0)

    def test_an_attempt_missing_its_result_state_is_refused_rather_than_defaulted(self) -> None:
        incomplete = {key: value for key, value in RAPID_PIPELINE_FIRST_ATTEMPT.items()
                      if key != "result_state"}

        with self.assertRaises(KeyError):
            loader.parse_run_attempt(incomplete)

    def test_an_attempt_in_a_state_the_platform_does_not_document_is_refused_not_guessed_at(self) -> None:
        cancelled = {**RAPID_PIPELINE_FIRST_ATTEMPT, "result_state": "CANCELED"}

        with self.assertRaises(ValueError):
            loader.parse_run_attempt(cancelled)

    def test_pointing_the_loader_at_a_directory_with_no_runs_log_names_the_file_it_wanted(self) -> None:
        with self.assertRaises(loader.FixtureError) as raised:
            loader.load_runs_log(REPOSITORY_ROOT)

        self.assertIn("runs.jsonl", str(raised.exception))
        self.assertIn("is missing", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
