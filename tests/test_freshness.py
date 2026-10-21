import dataclasses
import unittest
from pathlib import Path

from morning_rounds import freshness, loader, models

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"

AS_OF = "2026-10-20T11:30:00Z"
A_TABLE = "hed_dataplatform.gold.a_table"


def a_pipeline(writes: tuple[str, ...] = (A_TABLE,), slo_hours: float = 26) -> models.Pipeline:
    return models.Pipeline(
        id="a_pipeline",
        job="a_job",
        cadence="daily 06:00 America/New_York",
        cadence_hours=24,
        freshness_slo_hours=slo_hours,
        tier=models.Tier.BUSINESS_FACING,
        owner="data-platform",
        writes=writes,
        reads=(),
    )


def a_commit(
    version: int,
    timestamp: str,
    operation: models.Operation = models.Operation.WRITE,
    rows: int = 1832,
    job_id: int = 1001,
) -> models.TableCommit:
    if operation is models.Operation.MERGE:
        metrics = {"numSourceRows": rows, "numTargetRowsInserted": rows, "numTargetRowsUpdated": 0,
                   "numTargetRowsDeleted": 0, "numTargetRowsCopied": 0}
    elif operation is models.Operation.OPTIMIZE:
        metrics = {"numAddedFiles": 1, "numRemovedFiles": 10,
                   "numAddedBytes": 3493365, "numRemovedBytes": 6178887}
    else:
        metrics = {"numFiles": 1, "numOutputRows": rows, "numOutputBytes": rows * 100}

    return models.TableCommit(
        version=version,
        timestamp=timestamp,
        user_name="ci-deploy@hed.example",
        operation=operation,
        parameters={},
        job_id=job_id,
        run_id=880000 + version,
        metrics=metrics,
    )


def a_history(
    commits: tuple[models.TableCommit, ...],
    status: models.CaptureStatus = models.CaptureStatus.OK,
    message: str | None = None,
) -> models.TableHistory:
    return models.TableHistory(
        table=A_TABLE,
        source=f"workspace/tables/{A_TABLE}/history.jsonl",
        status=status,
        message=message,
        commits=commits,
    )


class RefreshedDataTest(unittest.TestCase):
    def test_a_write_that_landed_rows_refreshed_the_table(self) -> None:
        landed = a_commit(436, AS_OF, models.Operation.WRITE, rows=1832)

        self.assertTrue(freshness.refreshed_data(landed))

    def test_a_write_that_landed_no_rows_did_not_refresh_the_table_however_it_ended(self) -> None:
        empty = a_commit(436, AS_OF, models.Operation.WRITE, rows=0)

        self.assertFalse(freshness.refreshed_data(empty))

    def test_a_merge_handed_rows_refreshed_the_table_even_when_none_of_them_changed(self) -> None:
        handed_rows = a_commit(1651, AS_OF, models.Operation.MERGE, rows=1832)
        unchanged = dataclasses.replace(
            handed_rows,
            metrics={**handed_rows.metrics, "numTargetRowsInserted": 0, "numTargetRowsUpdated": 0},
        )

        self.assertTrue(freshness.refreshed_data(unchanged))

    def test_a_merge_handed_no_rows_did_not_refresh_the_table_because_nothing_arrived(self) -> None:
        handed_nothing = a_commit(1654, AS_OF, models.Operation.MERGE, rows=0)

        self.assertFalse(freshness.refreshed_data(handed_nothing))

    def test_maintenance_never_refreshes_a_table_however_many_files_it_rewrote(self) -> None:
        optimised = a_commit(326, AS_OF, models.Operation.OPTIMIZE)

        self.assertTrue(freshness.is_maintenance(optimised))
        self.assertFalse(freshness.refreshed_data(optimised))

    def test_asking_maintenance_for_a_row_count_is_refused_rather_than_answered_with_zero(self) -> None:
        optimised = a_commit(326, AS_OF, models.Operation.OPTIMIZE)

        with self.assertRaises(NotImplementedError):
            freshness.rows_arrived(optimised)

    def test_an_age_is_measured_against_the_as_of_instant_and_not_the_machines_clock(self) -> None:
        self.assertEqual(freshness.age_in_hours("2026-10-20T09:30:00Z", AS_OF), 2.0)
        self.assertEqual(freshness.age_in_hours("2026-10-19T11:30:00Z", AS_OF), 24.0)


class FreshnessFindingsTest(unittest.TestCase):
    def test_a_table_refreshed_inside_its_slo_has_nothing_wrong_with_it(self) -> None:
        history = a_history((a_commit(902, "2026-10-20T10:33:47Z"),))

        self.assertEqual(freshness.find_freshness(a_pipeline(), history, AS_OF), ())

    def test_a_table_refreshed_longer_ago_than_its_slo_allows_is_reported_stale(self) -> None:
        history = a_history((a_commit(325, "2026-10-11T08:08:00Z"),))

        findings = freshness.find_freshness(a_pipeline(), history, AS_OF)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, models.FindingCode.TABLE_OLDER_THAN_SLO)
        self.assertIn("219.4h", findings[0].what)
        self.assertIn("26h SLO", findings[0].what)
        self.assertIn("repo/platform/pipelines.json: a_pipeline cadence_hours 24, "
                      "freshness_slo_hours 26", findings[0].evidence)
        self.assertIn(freshness.FRESHNESS_STANDARD, findings[0].evidence)

    def test_a_table_whose_newest_commit_is_maintenance_is_aged_from_its_last_real_write(self) -> None:
        history = a_history((
            a_commit(326, "2026-10-19T03:07:00Z", models.Operation.OPTIMIZE, job_id=1099),
            a_commit(325, "2026-10-11T08:08:00Z", rows=143),
        ))

        findings = freshness.find_freshness(a_pipeline(), history, AS_OF)

        self.assertEqual(len(findings), 1)
        # Measured from v325 at 219.4h, not from the 32.4h-old OPTIMIZE that touched no data.
        self.assertIn("219.4h", findings[0].what)
        self.assertIn("maintenance and refreshed nothing", findings[0].why)
        self.assertTrue(any("v326 OPTIMIZE" in line for line in findings[0].evidence))
        self.assertTrue(any("v325 WRITE" in line for line in findings[0].evidence))

    def test_a_newest_write_that_moved_nothing_is_reported_against_the_last_one_that_did(self) -> None:
        history = a_history((
            a_commit(436, "2026-10-20T10:06:03Z", rows=0),
            a_commit(435, "2026-10-19T10:05:34Z", rows=0),
            a_commit(433, "2026-10-17T10:06:10Z", rows=1832),
        ))

        findings = freshness.find_freshness(a_pipeline(), history, AS_OF)
        codes = [finding.code for finding in findings]

        self.assertEqual(codes, [models.FindingCode.TABLE_WROTE_NOTHING,
                                 models.FindingCode.TABLE_OLDER_THAN_SLO])
        self.assertIn("numOutputRows is 0", findings[0].what)
        self.assertTrue(any("v436 WRITE" in line and "numOutputRows 0" in line
                            for line in findings[0].evidence))
        self.assertTrue(any("v433 WRITE" in line and "numOutputRows 1832" in line
                            for line in findings[0].evidence))

    def test_a_table_that_moved_nothing_but_is_still_inside_its_slo_is_reported_only_once(self) -> None:
        history = a_history((
            a_commit(436, "2026-10-20T10:06:03Z", rows=0),
            a_commit(435, "2026-10-20T09:00:00Z", rows=1832),
        ))

        findings = freshness.find_freshness(a_pipeline(), history, AS_OF)

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.TABLE_WROTE_NOTHING])

    def test_a_table_the_snapshot_could_not_read_is_unmeasured_and_carries_the_reason(self) -> None:
        denied = "PERMISSION_DENIED: User does not have SELECT on Table 'a_table'."
        history = a_history((), status=models.CaptureStatus.ERROR, message=denied)

        findings = freshness.find_freshness(a_pipeline(), history, AS_OF)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, models.FindingCode.TABLE_EVIDENCE_UNREADABLE)
        self.assertIn(denied, findings[0].why)
        self.assertTrue(any(denied in line for line in findings[0].evidence))
        self.assertIn("unmeasured rather than broken or healthy", findings[0].why)

    def test_a_table_only_ever_maintained_has_no_refresh_to_measure_from(self) -> None:
        history = a_history((
            a_commit(326, "2026-10-19T03:07:00Z", models.Operation.OPTIMIZE, job_id=1099),
            a_commit(325, "2026-10-18T03:07:00Z", models.Operation.OPTIMIZE, job_id=1099),
        ))

        findings = freshness.find_freshness(a_pipeline(), history, AS_OF)

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.TABLE_NEVER_REFRESHED])
        self.assertIn("2 versions", findings[0].why)

    def test_a_table_with_no_captured_history_at_all_is_not_quietly_called_fresh(self) -> None:
        findings = freshness.find_freshness(a_pipeline(), a_history(()), AS_OF)

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.TABLE_NEVER_REFRESHED])
        self.assertIn("no versions", findings[0].why)

    def test_every_finding_names_the_pipeline_it_belongs_to_not_the_table(self) -> None:
        history = a_history((a_commit(325, "2026-10-11T08:08:00Z"),))

        findings = freshness.find_freshness(a_pipeline(), history, AS_OF)

        self.assertEqual([finding.subject for finding in findings], ["a_pipeline"])


class SuppliedSnapshotFreshnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        self.registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)

    def pipeline(self, pipeline_id: str) -> models.Pipeline:
        return next(p for p in self.registry.pipelines if p.id == pipeline_id)

    def history(self, table: str) -> models.TableHistory:
        return loader.load_table_history(SUPPLIED_FIXTURES, self.manifest, table)

    def test_the_bronze_table_the_expired_credential_feeds_is_both_empty_and_stale(self) -> None:
        pipeline = self.pipeline("workday_bronze_daily")
        history = self.history("hed_dataplatform.bronze.workday_workers")

        findings = freshness.find_freshness(pipeline, history, self.manifest.captured_at)

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.TABLE_WROTE_NOTHING,
                          models.FindingCode.TABLE_OLDER_THAN_SLO])
        # 2026-10-17 is the day the ISU password expired, per the runbook.
        self.assertTrue(any("2026-10-17T10:06:10Z" in line for line in findings[0].evidence))
        self.assertIn("73.4h", findings[1].what)

    def test_the_parity_table_is_eight_times_its_slo_behind_under_a_fresh_looking_optimize(self) -> None:
        pipeline = self.pipeline("dashboard_parity_daily")
        history = self.history("hed_dataplatform.gold.dashboard_parity")

        findings = freshness.find_freshness(pipeline, history, self.manifest.captured_at)

        self.assertEqual([finding.code for finding in findings],
                         [models.FindingCode.TABLE_OLDER_THAN_SLO])
        self.assertIn("219.4h", findings[0].what)
        self.assertTrue(any("job 1099" in line for line in findings[0].evidence))

    def test_a_pipeline_that_ran_and_moved_rows_this_morning_has_no_freshness_finding(self) -> None:
        pipeline = self.pipeline("gold_dim_employees_daily")
        history = self.history("hed_dataplatform.gold.dim_employees")

        self.assertEqual(freshness.find_freshness(pipeline, history, self.manifest.captured_at), ())

    def test_the_weekly_pipeline_is_six_days_old_and_still_inside_its_own_slo(self) -> None:
        pipeline = self.pipeline("workday_project_transactions_weekly")
        history = self.history("hed_dataplatform.silver.workday_project_transactions")

        self.assertEqual(pipeline.freshness_slo_hours, 192)
        self.assertEqual(freshness.find_freshness(pipeline, history, self.manifest.captured_at), ())


if __name__ == "__main__":
    unittest.main()
