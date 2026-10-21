import collections
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


A_BRONZE_WRITE_COMMIT = {
    "version": 436,
    "timestamp": "2026-10-20T10:06:03Z",
    "userName": "ci-deploy@hed.example",
    "operation": "WRITE",
    "operationParameters": {"mode": "Append"},
    "job": {"jobId": "1001", "runId": "882184"},
    "operationMetrics": {"numFiles": "0", "numOutputRows": "0", "numOutputBytes": "0"},
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
        self.assertEqual(rapid.tier, models.PipelineTier.BUSINESS_FACING)

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
        self.assertEqual(retried.result_state, models.RunResultState.SUCCESS)
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
            [models.RunResultState.FAILED, models.RunResultState.FAILED, models.RunResultState.SUCCESS],
        )
        self.assertEqual(
            [attempt.trigger for attempt in retried.attempts],
            [models.RunTrigger.PERIODIC, models.RunTrigger.RETRY, models.RunTrigger.RETRY],
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
        self.assertEqual(exhausted.result_state, models.RunResultState.FAILED)
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
        self.assertEqual(clean.result_state, models.RunResultState.SUCCESS)
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


class ContractsTest(unittest.TestCase):
    def test_both_governed_tables_load_with_the_contract_version_they_promise(self) -> None:
        contracts = loader.load_contracts(SUPPLIED_FIXTURES)
        by_table = {contract.table: contract for contract in contracts}

        self.assertEqual(len(contracts), 2)
        self.assertEqual(by_table["hed_dataplatform.gold.dim_projects"].contract_version, "2.0.1")
        self.assertEqual(
            by_table["hed_dataplatform.gold.fact_project_financials"].contract_version, "1.2.0"
        )
        self.assertTrue(all(contract.governed for contract in contracts))

    def test_a_contract_cites_the_repository_file_it_was_read_from(self) -> None:
        contracts = loader.load_contracts(SUPPLIED_FIXTURES)
        by_table = {contract.table: contract for contract in contracts}

        self.assertEqual(
            by_table["hed_dataplatform.gold.dim_projects"].source,
            "repo/contracts/gold.dim_projects.json",
        )

    def test_a_contract_names_the_job_allowed_to_write_the_table_and_how(self) -> None:
        contracts = loader.load_contracts(SUPPLIED_FIXTURES)
        by_table = {contract.table: contract for contract in contracts}

        writers = by_table["hed_dataplatform.gold.fact_project_financials"].writers
        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].job, "deltek_helix_daily_refresh")
        self.assertEqual(writers[0].statements, ("WRITE (overwrite)",))

    def test_a_contract_column_keeps_the_note_that_explains_how_to_read_its_values(self) -> None:
        contracts = loader.load_contracts(SUPPLIED_FIXTURES)
        by_table = {contract.table: contract for contract in contracts}

        financials = by_table["hed_dataplatform.gold.fact_project_financials"]
        columns = {column.name: column for column in financials.columns}
        self.assertEqual(columns["period"].note, "YYYY-MM")
        self.assertEqual(columns["fee_currency"].note, "ISO 4217")
        self.assertIsNone(columns["gross_fee"].note)

    def test_the_contract_promises_a_money_column_the_deployed_table_no_longer_has(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        contracts = loader.load_contracts(SUPPLIED_FIXTURES)
        promised = next(c for c in contracts if c.table.endswith("fact_project_financials"))

        deployed = loader.load_table_schema(SUPPLIED_FIXTURES, manifest, promised.table)

        promised_columns = {column.name: column for column in promised.columns}
        deployed_columns = {column.name: column for column in deployed.columns}
        self.assertEqual(promised_columns["net_fee"].type, "DECIMAL(18,2)")
        self.assertNotIn("net_fee", deployed_columns)
        self.assertEqual(deployed_columns["net_fee_usd"].type, "DOUBLE")
        self.assertNotIn("fee_currency", deployed_columns)


class LineageTest(unittest.TestCase):
    def test_the_lineage_loads_every_table_edge_and_every_consumer_it_declares(self) -> None:
        lineage = loader.load_lineage(SUPPLIED_FIXTURES)

        self.assertEqual(lineage.source, "repo/platform/lineage.json")
        self.assertEqual(len(lineage.tables), 4)
        self.assertEqual(len(lineage.consumers), 8)

    def test_a_table_knows_which_tables_it_was_built_from(self) -> None:
        lineage = loader.load_lineage(SUPPLIED_FIXTURES)
        built_from = {edge.table: edge.built_from for edge in lineage.tables}

        self.assertEqual(
            built_from["hed_dataplatform.gold.dim_employees"],
            ("hed_dataplatform.silver.workday_workers",),
        )

    def test_a_consumer_names_the_fields_it_reads_so_a_finding_can_reach_the_field(self) -> None:
        lineage = loader.load_lineage(SUPPLIED_FIXTURES)
        by_id = {consumer.id: consumer for consumer in lineage.consumers}

        financials = by_id["pbi-project-financials"]
        self.assertEqual(financials.name, "Project Financials")
        self.assertEqual(financials.type, "powerbi")
        reads = {read.table: read.fields for read in financials.reads}
        self.assertIn("net_fee", reads["hed_dataplatform.gold.fact_project_financials"])
        self.assertIn("fee_currency", reads["hed_dataplatform.gold.fact_project_financials"])


class TableHistoryTest(unittest.TestCase):
    def test_a_readable_table_loads_its_commits_newest_first(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        history = loader.load_table_history(
            SUPPLIED_FIXTURES, manifest, "hed_dataplatform.bronze.workday_workers"
        )

        self.assertEqual(history.status, models.CaptureStatus.OK)
        self.assertEqual(
            history.source,
            "workspace/tables/hed_dataplatform.bronze.workday_workers/history.jsonl",
        )
        self.assertEqual(len(history.commits), 25)
        self.assertEqual([commit.version for commit in history.commits[:3]], [436, 435, 434])

    def test_a_table_the_snapshot_could_not_read_comes_back_empty_with_the_reason_why(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        history = loader.load_table_history(
            SUPPLIED_FIXTURES, manifest, "hed_dataplatform.gold.usecase_registry"
        )

        self.assertEqual(history.status, models.CaptureStatus.ERROR)
        self.assertEqual(history.commits, ())
        self.assertIn("PERMISSION_DENIED", str(history.message))

    def test_the_newest_commit_on_a_table_can_be_maintenance_run_by_another_job_entirely(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        history = loader.load_table_history(
            SUPPLIED_FIXTURES, manifest, "hed_dataplatform.gold.dashboard_parity"
        )

        newest, previous = history.commits[0], history.commits[1]
        self.assertEqual(newest.operation, models.TableOperation.OPTIMIZE)
        self.assertEqual(newest.job_id, 1099)
        self.assertEqual(newest.timestamp, "2026-10-19T03:07:00Z")

        self.assertEqual(previous.operation, models.TableOperation.WRITE)
        self.assertEqual(previous.job_id, 1004)
        self.assertEqual(previous.timestamp, "2026-10-11T08:08:00Z")

    def test_a_table_can_carry_commits_from_two_different_jobs_writing_the_same_rows(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        history = loader.load_table_history(
            SUPPLIED_FIXTURES, manifest, "meeting_minutes.silver.meeting_segments"
        )

        self.assertEqual(sorted({commit.job_id for commit in history.commits}), [1007, 1188])

    def test_a_commit_arrives_with_its_job_and_its_counters_as_numbers_not_delta_strings(self) -> None:
        commit = loader.parse_table_commit(A_BRONZE_WRITE_COMMIT)

        self.assertEqual(commit.job_id, 1001)
        self.assertEqual(commit.run_id, 882184)
        self.assertEqual(commit.metrics["numOutputRows"], 0)
        self.assertEqual(commit.operation, models.TableOperation.WRITE)
        self.assertEqual(commit.parameters, {"mode": "Append"})

    def test_every_operation_the_platform_performs_on_a_table_is_recognised(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)

        seen = {
            commit.operation
            for pipeline in registry.pipelines
            for table in pipeline.writes
            for commit in loader.load_table_history(SUPPLIED_FIXTURES, manifest, table).commits
        }

        self.assertEqual(seen, set(models.TableOperation))

    def test_a_commit_in_an_operation_the_pack_does_not_document_is_refused(self) -> None:
        vacuumed = {**A_BRONZE_WRITE_COMMIT, "operation": "VACUUM START"}

        with self.assertRaises(ValueError):
            loader.parse_table_commit(vacuumed)


class TableSchemaTest(unittest.TestCase):
    def test_a_readable_schema_loads_its_columns_in_the_order_the_table_declares_them(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        schema = loader.load_table_schema(
            SUPPLIED_FIXTURES, manifest, "hed_dataplatform.gold.dim_projects"
        )

        self.assertEqual(schema.status, models.CaptureStatus.OK)
        self.assertEqual(schema.captured_at, "2026-10-20T11:30:00Z")
        self.assertEqual(
            [column.name for column in schema.columns],
            ["project_id", "project_name", "sector", "project_status", "_built_at"],
        )
        self.assertFalse(schema.columns[0].nullable)
        self.assertTrue(schema.columns[1].nullable)

    def test_a_schema_the_snapshot_could_not_read_has_no_columns_and_no_capture_time(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)

        schema = loader.load_table_schema(
            SUPPLIED_FIXTURES, manifest, "hed_dataplatform.gold.usecase_registry"
        )

        self.assertEqual(schema.status, models.CaptureStatus.ERROR)
        self.assertEqual(schema.columns, ())
        self.assertIsNone(schema.captured_at)
        self.assertIn("PERMISSION_DENIED", str(schema.message))


class DataDictionaryTest(unittest.TestCase):
    def test_every_documented_field_loads_with_the_line_it_sits_on(self) -> None:
        dictionary = loader.load_data_dictionary(SUPPLIED_FIXTURES)

        self.assertEqual(dictionary.source, "dictionary/data-dictionary.csv")
        self.assertEqual(len(dictionary.entries), 17)
        self.assertEqual(dictionary.entries[0].line, 2)
        self.assertEqual(dictionary.entries[-1].line, 18)

    def test_a_field_nobody_has_defined_is_loaded_empty_rather_than_quietly_filled_in(self) -> None:
        dictionary = loader.load_data_dictionary(SUPPLIED_FIXTURES)
        by_line = {entry.line: entry for entry in dictionary.entries}

        undefined = by_line[13]
        self.assertEqual(undefined.table, "hed_dataplatform.gold.fact_project_financials")
        self.assertEqual(undefined.field, "net_fee")
        self.assertEqual(undefined.definition, "")
        self.assertEqual(undefined.business_owner, "")
        self.assertEqual(undefined.review_status, models.ReviewStatus.NEEDS_REVIEW)

    def test_an_approved_field_carries_the_definition_and_owner_somebody_signed_off(self) -> None:
        dictionary = loader.load_data_dictionary(SUPPLIED_FIXTURES)
        by_line = {entry.line: entry for entry in dictionary.entries}

        approved = by_line[2]
        self.assertEqual(approved.field, "employee_id")
        self.assertEqual(approved.review_status, models.ReviewStatus.APPROVED)
        self.assertEqual(approved.business_owner, "People Analytics — S. Patel")
        self.assertEqual(approved.original_upstream_source, "Workday")

    def test_five_of_the_documented_fields_are_still_waiting_on_review(self) -> None:
        dictionary = loader.load_data_dictionary(SUPPLIED_FIXTURES)

        waiting = [
            entry for entry in dictionary.entries
            if entry.review_status is models.ReviewStatus.NEEDS_REVIEW
        ]

        self.assertEqual([entry.line for entry in waiting], [3, 6, 9, 13, 16])

    def test_a_review_status_the_dictionary_format_does_not_document_is_refused(self) -> None:
        row = {
            "data_product": "Workforce",
            "table": "hed_dataplatform.gold.dim_employees",
            "field": "employee_id",
            "definition": "Unique Workday employee identifier.",
            "review_status": "Rejected",
            "business_owner": "People Analytics — S. Patel",
            "source": "Databricks Gold",
            "original_upstream_source": "Workday",
        }

        with self.assertRaises(ValueError):
            loader.parse_dictionary_entry(row, line=2)


class GaugeCatalogTest(unittest.TestCase):
    def test_the_catalog_loads_every_gauge_and_who_is_meant_to_produce_it(self) -> None:
        catalog = loader.load_gauge_catalog(SUPPLIED_FIXTURES)
        owners = collections.Counter(gauge.owner for gauge in catalog.gauges)

        self.assertEqual(catalog.source, "gauges.json")
        self.assertEqual(len(catalog.gauges), 10)
        self.assertEqual(owners[models.GaugeOwner.ROUNDS], 6)
        self.assertEqual(owners[models.GaugeOwner.EXTERNAL], 2)
        self.assertEqual(owners[models.GaugeOwner.UNOWNED], 2)

    def test_a_gauge_this_tool_owns_declares_the_labels_every_sample_must_carry(self) -> None:
        catalog = loader.load_gauge_catalog(SUPPLIED_FIXTURES)
        by_name = {gauge.name: gauge for gauge in catalog.gauges}

        self.assertEqual(by_name["pipeline_status"].owner, models.GaugeOwner.ROUNDS)
        self.assertEqual(by_name["pipeline_status"].labels, ("pipeline", "status", "tier"))
        self.assertEqual(by_name["pipeline_data_age_seconds"].labels, ("pipeline", "table", "tier"))

    def test_a_gauge_nothing_measures_yet_is_loaded_as_unowned_not_as_ours(self) -> None:
        catalog = loader.load_gauge_catalog(SUPPLIED_FIXTURES)
        by_name = {gauge.name: gauge for gauge in catalog.gauges}

        self.assertEqual(by_name["pipeline_cost_usd_daily"].owner, models.GaugeOwner.UNOWNED)
        self.assertEqual(by_name["pipeline_dq_pass_ratio"].owner, models.GaugeOwner.UNOWNED)
        self.assertEqual(by_name["databricks_job_failures_total"].owner, models.GaugeOwner.EXTERNAL)

    def test_a_gauge_owner_the_catalog_format_does_not_document_is_refused(self) -> None:
        orphaned = {
            "name": "pipeline_status",
            "type": "gauge",
            "labels": ["pipeline"],
            "owner": "somebody-else",
            "description": "Pipeline status.",
        }

        with self.assertRaises(ValueError):
            loader.parse_gauge(orphaned)


class AgentReviewTest(unittest.TestCase):
    def test_the_review_loads_every_claim_the_agent_made_and_who_made_them(self) -> None:
        review = loader.load_agent_review(SUPPLIED_FIXTURES)

        self.assertEqual(review.agent, "pipeline-health-monitor")
        self.assertEqual(review.agent_version, "0.4.2")
        self.assertEqual(review.generated_at, "2026-10-20T10:45:00Z")
        self.assertEqual(review.source, "agent/morning-review-2026-10-20.json")
        self.assertEqual(len(review.claims), 8)

    def test_a_claim_about_one_run_cites_that_run_and_claims_no_window(self) -> None:
        review = loader.load_agent_review(SUPPLIED_FIXTURES)
        by_id = {claim.id: claim for claim in review.claims}

        single = by_id["C1"]
        self.assertEqual(single.pipeline, "workday_bronze_daily")
        self.assertEqual(single.evidence[0].type, models.AgentClaimEvidenceType.RUN)
        self.assertEqual(single.evidence[0].run_id, 882184)
        self.assertIsNone(single.evidence[0].window)

    def test_a_claim_about_a_run_of_runs_cites_the_job_and_the_window_it_looked_at(self) -> None:
        review = loader.load_agent_review(SUPPLIED_FIXTURES)
        by_id = {claim.id: claim for claim in review.claims}

        aggregate = by_id["C6"].evidence[0]
        self.assertEqual(aggregate.type, models.AgentClaimEvidenceType.RUNS)
        self.assertEqual(aggregate.job_id, 1007)
        self.assertEqual(aggregate.window, "last 25")
        self.assertIsNone(aggregate.run_id)

    def test_the_agent_states_pipelines_in_words_the_platform_does_not_define(self) -> None:
        review = loader.load_agent_review(SUPPLIED_FIXTURES)

        claimed = {claim.status for claim in review.claims}

        self.assertEqual(claimed, {"healthy", "recovered", "late"})

    def test_the_agent_never_mentions_the_one_pipeline_that_has_not_run_in_nine_days(self) -> None:
        review = loader.load_agent_review(SUPPLIED_FIXTURES)
        registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)

        reviewed = {claim.pipeline for claim in review.claims}
        registered = {pipeline.id for pipeline in registry.pipelines}

        self.assertEqual(registered - reviewed, {"dashboard_parity_daily"})
        self.assertEqual(review.scope, "Databricks jobs with a run in the last 7 days")

    def test_a_claim_can_cite_a_run_the_workspace_has_no_record_of(self) -> None:
        review = loader.load_agent_review(SUPPLIED_FIXTURES)
        runs = loader.load_runs_log(SUPPLIED_FIXTURES)
        by_id = {claim.id: claim for claim in review.claims}

        recorded = {run.run_id for run in runs.runs}
        cited = [evidence.run_id for evidence in by_id["C3"].evidence]

        self.assertEqual(cited, [882174, 882177])
        self.assertIn(882174, recorded)
        self.assertNotIn(882177, recorded)

    def test_a_claim_citing_a_single_run_without_naming_it_is_refused(self) -> None:
        unnamed = {"type": "run"}

        with self.assertRaises(KeyError):
            loader.parse_claim_evidence(unnamed)

    def test_a_claim_citing_evidence_of_a_kind_the_pack_does_not_document_is_refused(self) -> None:
        hearsay = {"type": "dashboard", "url": "https://example.invalid/graph"}

        with self.assertRaises(ValueError):
            loader.parse_claim_evidence(hearsay)


if __name__ == "__main__":
    unittest.main()
