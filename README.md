# Morning Rounds

## Running it

```
python3 rounds.py check --fixtures takehome-packet/fixtures
```

On Windows, use `py rounds.py check --fixtures takehome-packet\fixtures`.

`--fixtures` already defaults to `takehome-packet/fixtures`, so plain
`python3 rounds.py check` works from the repository root.

It writes `report.json`, `report.md` and `telemetry.ndjson` into `--out` (default: the current
directory) and prints a summary to stdout. Diagnostics go to stderr; there is no log file. The
run is refused if `--out` points inside the fixture pack, which is read-only.

"Now" is `captured_at` from `workspace/manifest.json`. `--as-of TIMESTAMP` overrides it.

## How it is put together

```
FILES -> loader -> DATA -> rules -> report
```

| Module | Responsibility |
|---|---|
| `loader.py` | The only code that touches disk. Parses all twelve fixture kinds |
| `models.py` | The parsed shapes, and every closed vocabulary the pack documents, as enums |
| `drift.py` | Rule 4: Git against the workspace, in both directions |
| `freshness.py` | Rules 1-3: data age from writes that **changed data**, against each pipeline's own SLO |
| `status.py` | The run log, and exactly one status per registered pipeline |
| `reconcile.py` | A verdict on every claim in the agent's review |
| `report.py` | The three artifacts. Decides nothing |

Rules take parsed data and never a path, so every branch is tested with literal inputs and
nothing is mocked. `manifest.json` is the gate: a file it records as `error` becomes an
unreadable marker in the loader, before any disk read, so a pipeline whose evidence is missing
comes out **unmeasured** rather than crashing or being guessed at.

Two choices worth knowing:

- **Status precedence is `broken > unmeasured > degraded > healthy`** (`status.STATUS_PRECEDENCE`).
  Reporting *degraded* asserts the data is fine for now, which missing evidence makes unknowable.
- **A measured zero and an unmeasured one are different samples.** An unmeasured pipeline
  publishes `pipeline_status` and no age or breach gauge at all. `schema_contract_violations` is
  ours to produce and is **not published**, because the rule behind it is not written.

## What I did not build

- **Rule 5, governed schema against contract.** The violation is real and unreported:
  `gold.fact_project_financials` promises `net_fee DECIMAL(18,2)` and `fee_currency`; the
  deployed table has `net_fee_usd DOUBLE` and no currency column. `pbi-project-financials` reads
  both missing fields. The loaders for both sides are built and tested; the comparison is not.
- **Blast radius from `lineage.json`.** Findings cite files, versions and run ids, but do not yet
  name the downstream tables and consumers affected. This is why `gold_dim_employees_daily` reads
  healthy: its own writes are fine, but it is built from a silver table that has had no new data
  since 2026-10-17, so it serves stale workforce data to the Staffing Report.
- **The concurrent-writer cause.** `mm_rapid_pipeline_30min` is reported as succeeding only on
  retry; that the retries are caused by `mm_segments_backfill` (job 1188, no Git definition)
  writing the same table on the same 30-minute cron is in the evidence but not in the rule.
- **The expired credential.** `runbooks/workday-ingestion.md` dates the ISU password expiry to
  2026-10-17, which is the day `workday_bronze_daily` started writing zero rows. The tool reports
  the symptom with its evidence; it does not read runbooks, so it does not name that cause.
- **Fixture validation.** Out of scope deliberately: a malformed pack raises from the loader with
  the file named, rather than being validated up front.

## Running the tests

```
python3 -m unittest discover -v
```

## Type checking

Annotations target **basedpyright strict**, set in `.vscode/settings.json`. The checker is
not a project dependency; nothing needs installing to run `rounds` or the tests.

To check from a shell, with the venv outside the repo:

```
python3 -m venv /tmp/tc && /tmp/tc/bin/pip install basedpyright
printf '{"typeCheckingMode":"strict","include":["rounds.py","morning_rounds","tests"]}' > pyrightconfig.json
/tmp/tc/bin/basedpyright; rm pyrightconfig.json
```

Clean under `strict`. The CLI defaults to `recommended`, which is stricter again and flags
`reportAny` where JSON enters the program (`loader.read_json`, `Job.settings`) — deliberate:
validating a read-only fixture pack buys nothing.
