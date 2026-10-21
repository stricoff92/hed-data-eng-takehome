"""A verdict on every claim the agent made, against the evidence the snapshot actually holds."""

from __future__ import annotations

from morning_rounds import models

THE_RUN_LOG = "workspace/runs.jsonl"
OUR_OWN_ROUNDS = "rounds"


def runs_by_id(runs: models.RunsLog) -> dict[int, models.Run]:
    return {run.run_id: run for run in runs.runs}


def describe_cited_run(run_id: int, runs: dict[int, models.Run]) -> str:
    cited = runs.get(run_id)
    if cited is None:
        return f"{THE_RUN_LOG}: no run with run_id {run_id}"

    return (f"{THE_RUN_LOG}: run_id {run_id} of {cited.job_name} started {cited.start_time}, "
            f"{cited.result_state} after {cited.retries} retries")


def describe_cited_window(evidence: models.ClaimEvidence, runs: models.RunsLog) -> str:
    captured = tuple(run for run in runs.runs if run.job_id == evidence.job_id)
    retried = tuple(run for run in captured if run.retries)
    succeeded = tuple(run for run in captured if run.result_state is models.ResultState.SUCCESS)
    return (f"{THE_RUN_LOG}: job_id {evidence.job_id} over {evidence.window}, {len(captured)} runs "
            f"captured, {len(succeeded)} succeeded, {len(retried)} of them only after a retry")


def describe_claim_evidence(claim: models.Claim, runs: models.RunsLog) -> tuple[str, ...]:
    by_id = runs_by_id(runs)
    described: list[str] = []
    for evidence in claim.evidence:
        if evidence.type is models.ClaimEvidenceType.RUN:
            described.append(describe_cited_run(evidence.run_id or 0, by_id))
        elif evidence.type is models.ClaimEvidenceType.RUNS:
            described.append(describe_cited_window(evidence, runs))
        else:
            raise NotImplementedError(f"unhandled claim evidence type: {evidence.type}")

    return tuple(described)


def fabricated_run_ids(claim: models.Claim, runs: models.RunsLog) -> tuple[int, ...]:
    by_id = runs_by_id(runs)
    return tuple(
        evidence.run_id for evidence in claim.evidence
        if evidence.type is models.ClaimEvidenceType.RUN
        and evidence.run_id is not None and evidence.run_id not in by_id
    )


def describe_our_finding(assessed: models.PipelineStatus) -> tuple[str, ...]:
    described = [f"{OUR_OWN_ROUNDS}: {assessed.pipeline.id} is {assessed.status}"]
    described.extend(f"{OUR_OWN_ROUNDS}: {finding.code}, {finding.what}" for finding in assessed.findings)
    return tuple(described)


def judge(
    claim: models.Claim,
    assessed: models.PipelineStatus | None,
    runs: models.RunsLog,
) -> models.ClaimVerdict:
    cited = describe_claim_evidence(claim, runs)
    fabricated = fabricated_run_ids(claim, runs)

    if assessed is None:
        verdict = models.Verdict.UNVERIFIABLE
        why = (f"{claim.pipeline} is not a pipeline the registry declares, so there is nothing to "
               f"judge the claim against")
        ours: tuple[str, ...] = (f"repo/platform/pipelines.json: no pipeline with id {claim.pipeline}",)
    elif fabricated:
        verdict = models.Verdict.CONTRADICTED
        missing = ", ".join(str(run_id) for run_id in fabricated)
        why = (f"the claim rests on run {missing}, which the run log has no record of. Whatever "
               f"else it asserts cannot be checked against the evidence it chose to cite")
        ours = describe_our_finding(assessed)
    elif assessed.status is models.Status.UNMEASURED:
        verdict = models.Verdict.UNVERIFIABLE
        why = (f"the evidence needed to judge {claim.pipeline} was not captured, so the claim can "
               f"be neither confirmed nor contradicted")
        ours = describe_our_finding(assessed)
    elif claim.status == assessed.status:
        verdict = models.Verdict.VERIFIED
        why = f"the evidence supports {claim.status}, which is what the claim asserts"
        ours = describe_our_finding(assessed)
    else:
        verdict = models.Verdict.CONTRADICTED
        why = (f"the claim says {claim.status}; the evidence says {assessed.status}. The runs it "
               f"cites are real and say what it says they say, so what it got wrong is the "
               f"conclusion, not the citation")
        ours = describe_our_finding(assessed)

    return models.ClaimVerdict(
        claim=claim,
        verdict=verdict,
        why=why,
        evidence=(f"{claim.id} claims {claim.status}: {claim.assertion}",) + cited + ours,
    )


def reconcile(
    review: models.AgentReview,
    assessed: tuple[models.PipelineStatus, ...],
    runs: models.RunsLog,
) -> tuple[models.ClaimVerdict, ...]:
    by_pipeline = {one.pipeline.id: one for one in assessed}
    return tuple(judge(claim, by_pipeline.get(claim.pipeline), runs) for claim in review.claims)


def unreviewed_pipelines(
    review: models.AgentReview,
    registry: models.PipelineRegistry,
) -> tuple[str, ...]:
    reviewed = {claim.pipeline for claim in review.claims}
    return tuple(
        pipeline.id for pipeline in registry.pipelines if pipeline.id not in reviewed
    )
