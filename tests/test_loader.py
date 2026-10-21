import unittest
from pathlib import Path

from morning_rounds import loader

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
        self.assertEqual(rapid.tier, 1)

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


if __name__ == "__main__":
    unittest.main()
