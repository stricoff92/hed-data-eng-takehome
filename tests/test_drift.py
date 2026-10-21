import unittest
from pathlib import Path
from typing import Any

from morning_rounds import drift, loader, models

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"

CI_DEPLOY = "ci-deploy@hed.example"
AN_ENGINEER = "j.okafor@hed.example"


def declared_in_git(name: str, settings: Any) -> models.JobDefinition:
    return models.JobDefinition(
        name=name,
        source=f"repo/databricks/jobs/{name}.json",
        settings=settings,
    )


def deployed(name: str, settings: Any, changed_by: str = CI_DEPLOY) -> models.JobsSnapshot:
    job = models.Job(
        job_id=1001,
        name=name,
        creator_user_name=CI_DEPLOY,
        created_time="2026-01-01T00:00:00Z",
        last_modified_by=changed_by,
        last_modified_at="2026-10-15T19:41:00Z",
        settings=settings,
    )
    return models.JobsSnapshot(
        captured_at="2026-10-20T11:30:00Z",
        source="workspace/jobs.json",
        jobs=(job,),
    )


def differences(declared: object, deployed: object) -> tuple[tuple[str, object, object], ...]:
    return tuple(drift.settings_differences(declared, deployed))


class SettingsDifferencesTest(unittest.TestCase):
    def test_settings_that_match_field_for_field_produce_no_differences(self) -> None:
        settings = {"name": "a_job", "max_concurrent_runs": 1}

        self.assertEqual(differences(settings, settings), ())

    def test_nested_settings_that_match_all_the_way_down_produce_no_differences(self) -> None:
        settings = {"schedule": {"quartz_cron_expression": "0 0 6 * * ?", "pause_status": "UNPAUSED"}}

        self.assertEqual(differences(settings, settings), ())

    def test_a_changed_value_is_named_by_its_key_with_the_git_side_first(self) -> None:
        found = differences({"max_concurrent_runs": 1}, {"max_concurrent_runs": 4})

        self.assertEqual(found, (("max_concurrent_runs", 1, 4),))

    def test_a_field_only_git_declares_reports_the_workspace_side_as_absent(self) -> None:
        found = differences({"timeout_seconds": 3600}, {})

        self.assertEqual(found, (("timeout_seconds", 3600, drift.ABSENT),))

    def test_a_field_only_the_workspace_carries_reports_the_git_side_as_absent(self) -> None:
        found = differences({}, {"timeout_seconds": 3600})

        self.assertEqual(found, (("timeout_seconds", drift.ABSENT, 3600),))

    def test_a_change_inside_a_block_is_named_by_its_dotted_path(self) -> None:
        found = differences(
            {"schedule": {"pause_status": "UNPAUSED"}},
            {"schedule": {"pause_status": "PAUSED"}},
        )

        self.assertEqual(found, (("schedule.pause_status", "UNPAUSED", "PAUSED"),))

    def test_a_change_three_blocks_deep_keeps_every_segment_of_the_path(self) -> None:
        found = differences(
            {"a": {"b": {"c": {"d": "git"}}}},
            {"a": {"b": {"c": {"d": "workspace"}}}},
        )

        self.assertEqual(found, (("a.b.c.d", "git", "workspace"),))

    def test_a_block_the_workspace_lost_entirely_is_reported_once_at_its_root(self) -> None:
        git_source = {"git_url": "https://example", "git_branch": "main", "git_provider": "gitHub"}

        found = differences({"git_source": git_source}, {})

        self.assertEqual(found, (("git_source", git_source, drift.ABSENT),))

    def test_a_changed_element_of_a_list_is_named_by_its_index(self) -> None:
        found = differences({"tags": ["gold", "daily"]}, {"tags": ["gold", "hourly"]})

        self.assertEqual(found, (("tags[1]", "daily", "hourly"),))

    def test_an_element_the_workspace_added_reports_the_git_side_as_absent(self) -> None:
        found = differences({"tags": ["gold"]}, {"tags": ["gold", "experimental"]})

        self.assertEqual(found, (("tags[1]", drift.ABSENT, "experimental"),))

    def test_an_element_the_workspace_dropped_reports_the_workspace_side_as_absent(self) -> None:
        found = differences({"tags": ["gold", "daily"]}, {"tags": ["gold"]})

        self.assertEqual(found, (("tags[1]", "daily", drift.ABSENT),))

    def test_a_change_inside_a_list_of_blocks_combines_the_index_and_the_dotted_path(self) -> None:
        found = differences(
            {"job_clusters": [{"new_cluster": {"num_workers": 2}}]},
            {"job_clusters": [{"new_cluster": {"num_workers": 8}}]},
        )

        self.assertEqual(found, (("job_clusters[0].new_cluster.num_workers", 2, 8),))

    def test_a_block_that_became_a_scalar_is_reported_whole_rather_than_walked(self) -> None:
        found = differences({"schedule": {"pause_status": "UNPAUSED"}}, {"schedule": "UNPAUSED"})

        self.assertEqual(found, (("schedule", {"pause_status": "UNPAUSED"}, "UNPAUSED"),))

    def test_a_list_that_became_a_block_is_reported_whole_rather_than_walked(self) -> None:
        found = differences({"tasks": [{"task_key": "main"}]}, {"tasks": {"task_key": "main"}})

        self.assertEqual(found, (("tasks", [{"task_key": "main"}], {"task_key": "main"}),))

    def test_a_field_that_stayed_null_is_not_a_difference(self) -> None:
        self.assertEqual(differences({"timeout_seconds": None}, {"timeout_seconds": None}), ())

    def test_a_null_field_and_a_field_that_is_not_there_are_not_the_same_thing(self) -> None:
        found = differences({"timeout_seconds": None}, {})

        self.assertEqual(found, (("timeout_seconds", None, drift.ABSENT),))

    def test_a_boolean_that_became_a_number_is_reported_although_python_compares_them_equal(self) -> None:
        found = differences({"continuous": True}, {"continuous": 1})

        self.assertEqual(found, (("continuous", True, 1),))

    def test_an_integer_that_became_a_float_is_reported_although_python_compares_them_equal(self) -> None:
        found = differences({"num_workers": 2}, {"num_workers": 2.0})

        self.assertEqual(found, (("num_workers", 2, 2.0),))

    def test_several_changed_fields_come_back_in_a_stable_alphabetical_order(self) -> None:
        found = differences(
            {"timeout_seconds": 1, "name": "git", "max_concurrent_runs": 1},
            {"timeout_seconds": 2, "name": "workspace", "max_concurrent_runs": 2},
        )

        self.assertEqual([field for field, _, _ in found],
                         ["max_concurrent_runs", "name", "timeout_seconds"])

    def test_an_absent_value_renders_as_the_word_absent_and_a_null_renders_as_json_null(self) -> None:
        self.assertEqual(drift.describe(drift.ABSENT), "absent")
        self.assertEqual(drift.describe(None), "null")
        self.assertEqual(drift.describe(True), "true")
        self.assertEqual(drift.describe("PAUSED"), '"PAUSED"')


class DriftTest(unittest.TestCase):
    def test_a_job_deployed_exactly_as_git_declares_it_is_not_drift(self) -> None:
        settings = {"name": "a_job", "schedule": {"pause_status": "UNPAUSED"}}

        findings = drift.find_drift((declared_in_git("a_job", settings),), deployed("a_job", settings))

        self.assertEqual(findings, ())

    def test_a_changed_nested_field_is_reported_by_its_path_with_both_sides_quoted(self) -> None:
        in_git = {"name": "a_job", "schedule": {"pause_status": "UNPAUSED"}}
        in_workspace = {"name": "a_job", "schedule": {"pause_status": "PAUSED"}}

        findings = drift.find_drift(
            (declared_in_git("a_job", in_git),),
            deployed("a_job", in_workspace, changed_by=AN_ENGINEER),
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, models.FindingCode.JOB_SETTINGS_DIFFER)
        self.assertIn("schedule.pause_status", findings[0].what)
        self.assertIn('repo/databricks/jobs/a_job.json: schedule.pause_status = "UNPAUSED"',
                      findings[0].evidence)
        self.assertIn('workspace/jobs.json: job_id 1001, schedule.pause_status = "PAUSED"',
                      findings[0].evidence)

    def test_a_changed_cluster_is_reported_by_its_index_so_the_reader_knows_which_one(self) -> None:
        in_git = {"name": "a_job", "job_clusters": [{"new_cluster": {"node_type_id": "D4s_v5"}}]}
        in_workspace = {"name": "a_job", "job_clusters": [{"new_cluster": {"node_type_id": "DS3_v2"}}]}

        findings = drift.find_drift(
            (declared_in_git("a_job", in_git),),
            deployed("a_job", in_workspace),
        )

        self.assertIn("job_clusters[0].new_cluster.node_type_id", findings[0].what)

    def test_a_whole_block_the_workspace_lacks_is_reported_once_rather_than_leaf_by_leaf(self) -> None:
        in_git = {"name": "a_job", "git_source": {"git_branch": "main", "git_provider": "gitHub"}}
        in_workspace = {"name": "a_job"}

        findings = drift.find_drift(
            (declared_in_git("a_job", in_git),),
            deployed("a_job", in_workspace),
        )

        self.assertEqual(findings[0].what.count("git_source"), 1)
        self.assertIn("workspace/jobs.json: job_id 1001, git_source = absent", findings[0].evidence)

    def test_a_single_missing_field_inside_a_block_that_is_present_is_named_by_its_path(self) -> None:
        in_git = {"name": "a_job", "git_source": {"git_branch": "main", "git_provider": "gitHub"}}
        in_workspace = {"name": "a_job", "git_source": {"git_provider": "gitHub"}}

        findings = drift.find_drift(
            (declared_in_git("a_job", in_git),),
            deployed("a_job", in_workspace),
        )

        self.assertIn("git_source.git_branch", findings[0].what)
        self.assertIn("workspace/jobs.json: job_id 1001, git_source.git_branch = absent",
                      findings[0].evidence)

    def test_a_job_deployed_with_no_git_definition_names_the_principal_that_created_it(self) -> None:
        findings = drift.find_drift((), deployed("a_backfill", {"name": "a_backfill"}, AN_ENGINEER))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, models.FindingCode.JOB_NOT_IN_GIT)
        self.assertIn(AN_ENGINEER, findings[0].why)
        self.assertIn("workspace/jobs.json: job_id 1001, git_source absent", findings[0].evidence)

    def test_a_git_definition_that_was_never_deployed_is_drift_with_the_cause_left_open(self) -> None:
        empty_workspace = models.JobsSnapshot(
            captured_at="2026-10-20T11:30:00Z",
            source="workspace/jobs.json",
            jobs=(),
        )

        findings = drift.find_drift((declared_in_git("a_job", {"name": "a_job"}),), empty_workspace)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, models.FindingCode.JOB_NOT_DEPLOYED)
        self.assertIn("inference", findings[0].why)

    def test_a_finding_code_reaches_the_report_as_its_documented_slug_not_its_member_name(self) -> None:
        finding = drift.undeployed_definition_finding(declared_in_git("a_job", {"name": "a_job"}))

        self.assertEqual(f"{finding.code}", "git_definition_not_deployed")

    def test_every_finding_cites_the_standard_it_is_held_to(self) -> None:
        findings = drift.find_drift(
            loader.load_job_definitions(SUPPLIED_FIXTURES),
            loader.load_jobs_snapshot(SUPPLIED_FIXTURES),
        )

        for finding in findings:
            self.assertIn(drift.GIT_IS_THE_SOURCE_OF_TRUTH, finding.evidence)


class SuppliedSnapshotDriftTest(unittest.TestCase):
    def test_the_shipped_snapshot_has_drifted_from_git_in_exactly_three_ways(self) -> None:
        findings = drift.find_drift(
            loader.load_job_definitions(SUPPLIED_FIXTURES),
            loader.load_jobs_snapshot(SUPPLIED_FIXTURES),
        )
        by_subject = {finding.subject: finding for finding in findings}

        self.assertEqual(len(findings), 3)

        # Paused by hand nine days ago, so the parity check has not run since.
        self.assertEqual(by_subject["dashboard_parity_daily"].code, models.FindingCode.JOB_SETTINGS_DIFFER)

        # Downgraded by hand to a node family the platform standards forbid.
        self.assertIn(
            "job_clusters[0].new_cluster.node_type_id",
            by_subject["graph_pipeline_daily"].what,
        )

        # A second writer to the meeting_segments table that Git has never heard of.
        self.assertEqual(by_subject["mm_segments_backfill"].code, models.FindingCode.JOB_NOT_IN_GIT)


if __name__ == "__main__":
    unittest.main()
