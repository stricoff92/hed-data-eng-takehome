# Morning Rounds

Time spent: ~4 hours.

## Running it

```
python3 rounds.py check
```

`--fixtures` defaults to `takehome-packet/fixtures`. On Windows, use `py rounds.py check`.

Writes `report.json`, `report.md` and `telemetry.ndjson` to `--out` (default: the working
directory) and a summary to stdout. Diagnostics go to stderr; there is no log file. An `--out`
inside the fixture pack is refused, because the pack is read-only.

"Now" is `captured_at` from `workspace/manifest.json`. `--as-of TIMESTAMP` overrides it, and must
carry a timezone and not predate the snapshot, which would report negative ages.


## Running the tests

```
python3 -m unittest discover -v
```


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
| `contracts.py` | Rule 5: a governed table's deployed schema against the contract it promises |
| `status.py` | The run log, and exactly one status per registered pipeline |
| `reconcile.py` | A verdict on every claim in the agent's review |
| `report.py` | The three artifacts. Decides nothing |

Rules take parsed data and never a path, so every branch is tested with literal inputs and nothing
is mocked. `manifest.json` is the gate: a file it records as `error` becomes an unreadable marker
in the loader before any disk read, so a pipeline whose evidence is missing comes out
**unmeasured** rather than crashing or being guessed at.

- **Precedence is `broken > unmeasured > degraded > healthy`** (`status.STATUS_PRECEDENCE`).
  *Degraded* asserts the data is fine for now, which missing evidence makes unknowable.
- **A measured zero and an unmeasured one are different samples.** An unmeasured pipeline
  publishes `pipeline_status` and no age or breach gauge, and `schema_contract_violations` counts
  only tables whose schema could be read. Zero means checked and kept; silence means not checked.

## What I did not build

- **`RUNBOOK.md` and `NOTICE.md`** (deliverables 6 and 7), and the buy-vs-build and sunset-trigger
  sections of `DECISIONS.md`. I hit the time box with the tool, the reconciliation and the tests
  done. The alert would have fired on `pipeline_slo_breach` and `pipeline_status`; the notice would
  have covered `gold.fact_project_financials` dropping `net_fee` and `fee_currency`, which
  Finance's report reads by name.
- **Blast radius from `lineage.json`.** Findings cite files, versions and run ids, not the
  downstream tables and consumers affected. So `gold_dim_employees_daily` reads healthy — its own
  writes are fine, but its source silver table has had no new data since 2026-10-17, which leaves
  the Staffing Report stale — and the contract finding on `gold.fact_project_financials` never says
  that `pbi-project-financials` reads both missing fields by name.
- **The contract's declared writers.** `contracts.py` compares columns only; a contract also names
  the job allowed to write the table and with which statements.
- **The concurrent-writer cause.** `mm_rapid_pipeline_30min` is reported as succeeding only on
  retry. That `mm_segments_backfill` (job 1188, no Git definition) writes the same table on the
  same 30-minute cron is in the evidence, not in the rule.
- **The expired credential.** `runbooks/workday-ingestion.md` puts the ISU password expiry at
  2026-10-17, the day `workday_bronze_daily` started writing zero rows. The tool reports the
  symptom; it does not read runbooks, so it does not name the cause.
- **Fixture validation.** A malformed pack raises from the loader with the file named, rather than
  being validated up front.



## Type checking

Annotations target **basedpyright strict**, set in the editor rather than the repo; the checker is
not a project dependency. Clean under `strict`: 0 errors, 0 warnings. To reproduce:

```
python3 -m venv /tmp/tc && /tmp/tc/bin/pip install basedpyright
printf '{"typeCheckingMode":"strict","include":["rounds.py","morning_rounds","tests"]}' > pyrightconfig.json
/tmp/tc/bin/basedpyright; rm pyrightconfig.json
```

The CLI default, `recommended`, reports 17 errors and 274 warnings I did not chase. 121 of the 160
`reportAny` are in `loader.py`, where untyped JSON enters the program: validating a read-only
fixture pack buys nothing. All 17 errors are uninitialised instance variables in test `setUp`.
