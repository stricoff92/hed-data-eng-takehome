# Fixture pack — shapes and file map

Everything here is synthetic and self-contained. Nothing reaches a network, a
Databricks workspace, or a real repository. The shapes mirror the ones the
Databricks APIs and our platform repository use, trimmed to what this exercise
needs.

```
fixtures/
├── workspace/                     read-only snapshot of the Databricks workspace
│   ├── manifest.json              what the snapshot captured, and when
│   ├── jobs.json                  the jobs deployed in the workspace
│   ├── runs.jsonl                 recent job runs, one line per attempt
│   └── tables/<catalog.schema.table>/
│       ├── history.jsonl          Delta table history
│       └── schema.json            deployed table schema
├── repo/                          trimmed copy of the platform repository the workspace was deployed from
│   ├── README.md
│   ├── databricks/jobs/*.json     job definitions — the source of truth
│   ├── platform/pipelines.json    pipeline registry
│   ├── platform/lineage.json      table lineage and consumers
│   ├── contracts/*.json           schema contracts for governed tables
│   └── docs/                      platform standards and runbooks
├── agent/morning-review-2026-10-20.json   the agent's overnight review
├── dictionary/data-dictionary.csv         Data Dictionary extract
└── gauges.json                    the gauge catalog, with the ownership column
```

All timestamps are ISO-8601 UTC (`...Z`). Schedules and cadences are stated in
`America/New_York`.

## As-of

"Now" for this exercise is `workspace/manifest.json` → `captured_at`
(`2026-10-20T11:30:00Z`, 07:30 in New York). Compute ages against it, not
against your clock.

## `workspace/manifest.json`

What the snapshot export captured.

| Field | Type | Meaning |
|---|---|---|
| `export` | string | Export name |
| `captured_at` | string | The as-of instant |
| `captured_by` | string | The principal that ran the export |
| `workspace` | string | Workspace identifier |
| `files` | array | One entry per file the export attempted |

Each `files[]` entry: `path` (relative to `fixtures/`), `status` (`"ok"` or
`"error"`), and either a `note` (on `ok`) or a `message` (on `error`). A file
whose status is `error` was not captured and is not on disk.

## `workspace/jobs.json`

`{ captured_at, jobs[] }`. Each job is the Jobs API job object, with the
`last_modified` field joined from the workspace audit log:

| Field | Type | Meaning |
|---|---|---|
| `job_id` | number | Workspace job id |
| `creator_user_name` | string | Who created the job |
| `created_time` | string | When |
| `settings` | object | The deployed settings — the same shape as a file in `repo/databricks/jobs/` (`name`, `tags`, `schedule`, `job_clusters`, `tasks`, `git_source`, `email_notifications`, …) |
| `last_modified` | object | `{ by, at }` — the last principal to change the job, and when |

`settings.schedule` is `{ quartz_cron_expression, timezone_id, pause_status }`
with `pause_status` `"PAUSED"` or `"UNPAUSED"`. Cluster settings live in
`settings.job_clusters[].new_cluster` (`spark_version`, `node_type_id`,
`num_workers`).

## `workspace/runs.jsonl`

Jobs API `runs/list`: the last 25 runs per job, **newest first**, **one line per
attempt**. A retried run appears as several lines that share a `run_id`, with
increasing `attempt`.

| Field | Type | Meaning |
|---|---|---|
| `job_id` | number | Workspace job id |
| `job_name` | string | Job name |
| `run_id` | number | Shared by every attempt of the same run |
| `attempt` | number | `0` for the scheduled attempt, then `1`, `2`, … |
| `trigger` | string | `PERIODIC` (scheduled) or `RETRY` |
| `start_time`, `end_time` | string | Attempt start and end |
| `result_state` | string | `SUCCESS` or `FAILED` — for this attempt |
| `state_message` | string | Empty on success; the error on failure |

## `workspace/tables/<catalog.schema.table>/history.jsonl`

`DESCRIBE HISTORY`: up to the last 30 versions, **newest first**, one object per line.

| Field | Type | Meaning |
|---|---|---|
| `version` | number | Delta table version |
| `timestamp` | string | Commit time |
| `userName` | string | Committing principal |
| `operation` | string | `WRITE`, `MERGE`, `OPTIMIZE`, or `CREATE OR REPLACE TABLE AS SELECT` |
| `operationParameters` | object | As Delta reports them |
| `job` | object | `{ jobId, runId }` of the job run that committed — **strings**, as Delta reports them |
| `operationMetrics` | object | Per-operation counters — **string values**, as Delta reports them |

`operationMetrics` keys by operation:

| `operation` | Keys |
|---|---|
| `WRITE`, `CREATE OR REPLACE TABLE AS SELECT` | `numFiles`, `numOutputRows`, `numOutputBytes` |
| `MERGE` | `numSourceRows`, `numTargetRowsInserted`, `numTargetRowsUpdated`, `numTargetRowsDeleted`, `numTargetRowsCopied` |
| `OPTIMIZE` | `numAddedFiles`, `numRemovedFiles`, `numAddedBytes`, `numRemovedBytes` |

## `workspace/tables/<catalog.schema.table>/schema.json`

`DESCRIBE TABLE`: `{ table, captured_at, columns[] }`, each column
`{ name, type, nullable }`.

## `repo/databricks/jobs/*.json`

One file per job, named after the job. Each is a job `settings` object — the
same shape as `settings` in `workspace/jobs.json`. These are what *should* be
deployed.

## `repo/platform/pipelines.json`

`{ registry_version, pipelines[] }`. Each pipeline:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Pipeline id |
| `job` | string | The job that runs it (matches a job `name`) |
| `cadence` | string | Human-readable schedule |
| `cadence_hours` | number | Expected interval between runs |
| `freshness_slo_hours` | number | Maximum acceptable data age |
| `tier` | number | `1` most critical, `3` least |
| `owner` | string | Owning team |
| `writes` | string[] | Tables the pipeline writes |
| `reads` | string[] | Tables or external sources it reads |

## `repo/platform/lineage.json`

`{ tables[], consumers[] }`.

- `tables[]`: `{ table, built_from[] }` — table-to-table edges.
- `consumers[]`: `{ id, name, type, owner, refresh, reads[] }`, each `reads[]`
  entry `{ table, fields[] }` — the fields that consumer reads from that table.

## `repo/contracts/*.json`

One file per governed table:
`{ table, governed, owner, contract_version, columns[], writers[] }`.
`columns[]` is `{ name, type, nullable }` — the same shape as `schema.json`.
`writers[]` is `{ job, statements[] }`.

## `repo/docs/`

`platform-standards.md` (the platform's written standards) and
`runbooks/workday-ingestion.md`. Prose; cite them like any other artifact.

## `agent/morning-review-2026-10-20.json`

The `pipeline-health-monitor` agent's review.

| Field | Type | Meaning |
|---|---|---|
| `agent`, `agent_version` | string | Producer |
| `generated_at` | string | When the review was written |
| `scope` | string | What the agent says it reviewed |
| `summary` | string | The agent's headline |
| `claims` | array | `{ id, pipeline, assertion, status, evidence[] }` |

Each `evidence[]` entry has a `type`: `{ type: "run", run_id }` or
`{ type: "runs", job_id, window }`.

## `dictionary/data-dictionary.csv`

An extract of the Data Dictionary, one row per field, with a header row:
`data_product, table, field, definition, review_status, business_owner, source,
original_upstream_source`. `review_status` is `Approved` or `Needs Review`.
Empty cells are empty — nobody has written that value down.

## `gauges.json`

The catalog: `{ gauges[] }`, each `{ name, type, labels[], owner, description }`.

`pipeline_status`, `pipeline_data_age_seconds` and `pipeline_slo_breach` carry
a `tier` label alongside `pipeline`.

| `owner` | Meaning |
|---|---|
| `rounds` | Your tool is the producer |
| `external` | Another producer publishes it |
| `unowned` | Nothing measures it yet |

The rule that applies is in the brief. The distinction that carries the weight
is between a **measured** zero and an **unmeasured** one.

## Telemetry your tool emits

Newline-delimited JSON (`telemetry.ndjson`), one object per line:

| Field | Type | Notes |
|---|---|---|
| `kind` | `"gauge" \| "log"` | `gauge` carries a numeric `value`; `log` carries `fields` |
| `name` | string | Gauge name (from `gauges.json`) or log event name |
| `value` | number | Gauges only |
| `labels` | object | Gauges only; keys from the gauge's `labels` in `gauges.json` |
| `fields` | object | Logs only; structured payload |
| `ts` | string | ISO-8601 UTC — the as-of instant |

```
{"kind":"gauge","name":"pipeline_status","value":1,"labels":{"pipeline":"<id>","tier":"<tier>","status":"<status>"},"ts":"2026-10-20T11:30:00Z"}
{"kind":"log","name":"<event>","fields":{"...":"..."},"ts":"2026-10-20T11:30:00Z"}
```

Log event names and their `fields` are yours to design.
