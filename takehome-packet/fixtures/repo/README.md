# platform (fixture)

A trimmed copy of the platform repository the snapshot in `../workspace/` was
deployed from.

```
databricks/jobs/      job definitions — the source of truth for what should be deployed
platform/pipelines.json  pipeline registry: cadence, freshness SLO, tier, tables written and read
platform/lineage.json    which tables are built from which, and which consumers read which fields
contracts/            schema contracts for governed tables
docs/                 platform standards and runbooks
```
