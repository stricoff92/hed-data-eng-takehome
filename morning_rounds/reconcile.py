"""A verdict on every claim the agent made, against the evidence the snapshot actually holds."""

from __future__ import annotations

from morning_rounds import models

THE_RUN_LOG = "workspace/runs.jsonl"
THIS_TOOL = "rounds"


def runs_by_id(runs: models.RunsLog) -> dict[int, models.Run]:
    return {run.run_id: run for run in runs.runs}


def describe_cited_run(run_id: int, runs: dict[int, models.Run]) -> str:
    cited = runs.get(run_id)
    if cited is None:
        return f"{THE_RUN_LOG}: no run with run_id {run_id}"

    return (f"{THE_RUN_LOG}: run_id {run_id} of {cited.job_name} started {cited.start_time}, "
            f"{cited.result_state} after {cited.retries} retries")


def describe_cited_window(evidence: models.AgentClaimEvidence, runs: models.RunsLog) -> str:
    captured = tuple(run for run in runs.runs if run.job_id == evidence.job_id)
    retried = tuple(run for run in captured if run.retries)
    succeeded = tuple(run for run in captured if run.result_state is models.RunResultState.SUCCESS)
    return (f"{THE_RUN_LOG}: job_id {evidence.job_id} over {evidence.window}, {len(captured)} runs "
            f"captured, {len(succeeded)} succeeded, {len(retried)} of them only after a retry")


def describe_claim_evidence(claim: models.AgentClaim, runs: models.RunsLog) -> tuple[str, ...]:
    by_id = runs_by_id(runs)
    described: list[str] = []
    for evidence in claim.evidence:
        if evidence.type is models.AgentClaimEvidenceType.RUN:
            described.append(describe_cited_run(evidence.run_id or 0, by_id))
        elif evidence.type is models.AgentClaimEvidenceType.RUNS:
            described.append(describe_cited_window(evidence, runs))
        else:
            raise NotImplementedError(f"unhandled claim evidence type: {evidence.type}")

    return tuple(described)


def fabricated_run_ids(claim: models.AgentClaim, runs: models.RunsLog) -> tuple[int, ...]:
    by_id = runs_by_id(runs)
    return tuple(
        evidence.run_id for evidence in claim.evidence
        if evidence.type is models.AgentClaimEvidenceType.RUN
        and evidence.run_id is not None and evidence.run_id not in by_id
    )


def describe_our_own_assessment(assessed: models.AssessedPipeline) -> tuple[str, ...]:
    described = [f"{THIS_TOOL}: {assessed.pipeline.id} is {assessed.status}"]
    described.extend(f"{THIS_TOOL}: {finding.code}, {finding.what}" for finding in assessed.findings)
    return tuple(described)


def judge_claim(
    claim: models.AgentClaim,
    assessed: models.AssessedPipeline | None,
    runs: models.RunsLog,
) -> models.JudgedClaim:
    cited_evidence = describe_claim_evidence(claim, runs)
    fabricated = fabricated_run_ids(claim, runs)

    if assessed is None:
        verdict = models.ClaimVerdict.UNVERIFIABLE
        why = (f"{claim.pipeline} is not a pipeline the registry declares, so there is nothing to "
               f"judge the claim against")
        our_assessment: tuple[str, ...] = (
            f"repo/platform/pipelines.json: no pipeline with id {claim.pipeline}",
        )
    elif fabricated:
        verdict = models.ClaimVerdict.CONTRADICTED
        missing = ", ".join(str(run_id) for run_id in fabricated)
        why = (f"the claim rests on run {missing}, which the run log has no record of. Whatever "
               f"else it asserts cannot be checked against the evidence it chose to cite")
        our_assessment = describe_our_own_assessment(assessed)
    elif assessed.status is models.PipelineStatus.UNMEASURED:
        verdict = models.ClaimVerdict.UNVERIFIABLE
        why = (f"the evidence needed to judge {claim.pipeline} was not captured, so the claim can "
               f"be neither confirmed nor contradicted")
        our_assessment = describe_our_own_assessment(assessed)
    elif claim.status == assessed.status:
        verdict = models.ClaimVerdict.VERIFIED
        why = f"the evidence supports {claim.status}, which is what the claim asserts"
        our_assessment = describe_our_own_assessment(assessed)
    else:
        verdict = models.ClaimVerdict.CONTRADICTED
        why = (f"the claim says {claim.status}; the evidence says {assessed.status}. The runs it "
               f"cites are real and say what it says they say, so what it got wrong is the "
               f"conclusion, not the citation")
        our_assessment = describe_our_own_assessment(assessed)

    return models.JudgedClaim(
        claim=claim,
        verdict=verdict,
        why=why,
        evidence=(f"{claim.id} claims {claim.status}: {claim.assertion}",) + cited_evidence + our_assessment,
    )


def reconcile(
    review: models.AgentReview,
    assessed_pipelines: tuple[models.AssessedPipeline, ...],
    runs: models.RunsLog,
) -> tuple[models.JudgedClaim, ...]:
    assessed_by_pipeline = {assessed.pipeline.id: assessed for assessed in assessed_pipelines}
    return tuple(
        judge_claim(claim, assessed_by_pipeline.get(claim.pipeline), runs)
        for claim in review.claims
    )


def unreviewed_pipelines(
    review: models.AgentReview,
    registry: models.PipelineRegistry,
) -> tuple[str, ...]:
    reviewed = {claim.pipeline for claim in review.claims}
    return tuple(
        pipeline.id for pipeline in registry.pipelines if pipeline.id not in reviewed
    )
