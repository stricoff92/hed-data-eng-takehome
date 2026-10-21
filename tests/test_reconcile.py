import unittest
from pathlib import Path

from morning_rounds import contracts, drift, loader, models, reconcile, status

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"


class SuppliedReviewReconciliationTest(unittest.TestCase):
    def setUp(self) -> None:
        manifest = loader.load_manifest(SUPPLIED_FIXTURES)
        self.registry = loader.load_pipeline_registry(SUPPLIED_FIXTURES)
        self.runs = loader.load_runs_log(SUPPLIED_FIXTURES)
        histories = {
            table: loader.load_table_history(SUPPLIED_FIXTURES, manifest, table)
            for pipeline in self.registry.pipelines for table in pipeline.writes
        }
        governed = loader.load_contracts(SUPPLIED_FIXTURES)
        schemas = {
            contract.table: loader.load_table_schema(SUPPLIED_FIXTURES, manifest, contract.table)
            for contract in governed
        }
        drift_findings = drift.find_drift(
            loader.load_job_definitions(SUPPLIED_FIXTURES),
            loader.load_jobs_snapshot(SUPPLIED_FIXTURES),
        ) + contracts.find_contract_drift(governed, schemas, self.registry)
        assessed = status.assess(
            self.registry, self.runs, histories, drift_findings, manifest.captured_at
        )
        self.review = loader.load_agent_review(SUPPLIED_FIXTURES)
        self.verdicts = {
            judged.claim.id: judged
            for judged in reconcile.reconcile(self.review, assessed, self.runs)
        }

    def test_every_claim_the_agent_made_gets_exactly_one_verdict(self) -> None:
        self.assertEqual(len(self.verdicts), len(self.review.claims))
        self.assertEqual(
            sorted(judged.verdict.value for judged in self.verdicts.values()),
            ["contradicted"] * 6 + ["unverifiable", "verified"],
        )

    def test_a_claim_resting_on_a_run_that_does_not_exist_is_contradicted_on_that_alone(self) -> None:
        judged = self.verdicts["C3"]

        self.assertEqual(judged.verdict, models.ClaimVerdict.CONTRADICTED)
        self.assertIn("882177", judged.why)
        self.assertIn("workspace/runs.jsonl: no run with run_id 882177", judged.evidence)
        # The failure it describes is real, and the reader has to be able to see that too.
        self.assertTrue(any("run_id 882174" in line and "FAILED" in line for line in judged.evidence))

    def test_a_claim_whose_run_succeeded_is_still_contradicted_when_the_data_did_not_move(self) -> None:
        judged = self.verdicts["C1"]

        self.assertEqual(judged.verdict, models.ClaimVerdict.CONTRADICTED)
        self.assertIn("the claim says healthy; the evidence says broken", judged.why)
        self.assertIn("what it got wrong is the conclusion, not the citation", judged.why)
        self.assertTrue(any("run_id 882184" in line and "SUCCESS" in line for line in judged.evidence))

    def test_a_claim_about_a_table_nobody_can_read_is_unverifiable_and_not_contradicted(self) -> None:
        judged = self.verdicts["C8"]

        self.assertEqual(judged.verdict, models.ClaimVerdict.UNVERIFIABLE)
        self.assertIn("was not captured", judged.why)

    def test_a_claim_counting_runs_is_answered_with_what_the_window_actually_holds(self) -> None:
        judged = self.verdicts["C6"]

        self.assertEqual(judged.verdict, models.ClaimVerdict.CONTRADICTED)
        # The agent said 25 of 25 succeeded. They did — after 9 of them were retried.
        self.assertTrue(any("25 runs captured, 25 succeeded, 9 of them only after a retry" in line
                            for line in judged.evidence))

    def test_a_claim_the_evidence_agrees_with_is_verified(self) -> None:
        self.assertEqual(self.verdicts["C2"].verdict, models.ClaimVerdict.VERIFIED)

    def test_a_claim_about_a_job_that_ran_fine_is_contradicted_by_what_it_wrote(self) -> None:
        # C7 calls deltek_helix_daily_refresh healthy. Its run did succeed, and the table it
        # wrote no longer carries the money column its contract promises.
        judged = self.verdicts["C7"]

        self.assertEqual(judged.verdict, models.ClaimVerdict.CONTRADICTED)
        self.assertTrue(any("deployed_schema_breaks_its_contract" in line
                            for line in judged.evidence))

    def test_the_agents_own_vocabulary_is_judged_rather_than_translated(self) -> None:
        judged = self.verdicts["C5"]

        self.assertEqual(judged.claim.status, "late")
        self.assertEqual(judged.verdict, models.ClaimVerdict.CONTRADICTED)
        self.assertIn("the claim says late; the evidence says healthy", judged.why)

    def test_the_pipeline_the_agent_never_mentioned_is_named(self) -> None:
        self.assertEqual(
            reconcile.unreviewed_pipelines(self.review, self.registry),
            ("dashboard_parity_daily",),
        )

    def test_a_claim_about_a_pipeline_the_registry_does_not_declare_cannot_be_judged(self) -> None:
        invented = models.AgentClaim(
            id="C9",
            pipeline="a_pipeline_nobody_registered",
            assertion="Healthy.",
            status="healthy",
            evidence=(),
        )

        judged = reconcile.judge_claim(invented, None, self.runs)

        self.assertEqual(judged.verdict, models.ClaimVerdict.UNVERIFIABLE)
        self.assertIn("not a pipeline the registry declares", judged.why)


if __name__ == "__main__":
    unittest.main()
