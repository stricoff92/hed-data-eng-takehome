# Platform standards

The rules the platform is held to. Each one exists because it was broken at least once.

## Git is the source of truth for jobs

Every scheduled job is defined in `databricks/jobs/*.json` and deployed from `main`.
The workspace is a deployment target, not an editing surface. A job whose deployed
settings differ from Git, or a job that exists in the workspace and not in Git, is
**drift**. Drift is fixed by changing Git and redeploying — or by committing the
workspace change to Git with a reason — never by a second workspace edit.

## Clusters

Job clusters use the Standard **DSv5** family (`Standard_D4s_v5`, `D8s_v5`,
`D16s_v5`, `D32s_v5`) on runtime **14.3.x or newer**. Older families (DSv2, DSv3,
DSv4) draw on a 10-core regional quota and fail job clusters with
`AZURE_QUOTA_EXCEEDED_EXCEPTION` once a few run at the same time.

## Freshness

`platform/pipelines.json` declares each pipeline's cadence and its freshness SLO: the
maximum age of the last write that **changed data** in each table the pipeline
writes. A table rewritten with nothing in it, or touched only by maintenance, has
not been refreshed.

## Tiers

| Tier | Meaning | Response |
|---|---|---|
| 1 | Feeds business-facing reporting or an application | Business hours, same morning |
| 2 | Feeds internal tooling or a tier-1 pipeline's inputs | Same day |
| 3 | Internal checks and comparisons | Next working day |

## Governed tables

A table with a file in `contracts/` is governed. Its deployed schema must match the
contract. A change to a governed table ships with an updated contract and a notice to
the consumers listed in `platform/lineage.json` within 24 hours of the change.
