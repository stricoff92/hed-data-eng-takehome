# Runbook

One alert rule, written against the telemetry in `telemetry.ndjson`.

## Alert: tier-1 pipeline serving data past its freshness SLO

| | |
|---|---|
| **Expression** | `max by (pipeline, tier) (pipeline_slo_breach{tier="1"}) == 1` |
| **Threshold** | any sample equal to `1`, held for `15m` (one `rounds` publish interval, so a single late run does not page) |
| **Severity** | **high** — tier 1 is "business hours, same morning" in `repo/docs/platform-standards.md:27-33` |
| **Runbook** | [Response: tier-1 freshness breach](#response-tier-1-freshness-breach) |

**What a recipient reads at 08:00:**

> Tier-1 pipeline `workday_bronze_daily` is serving data older than its 26h freshness SLO
> (currently 73h). Consumers are reading stale data now. Runbook: Response — tier-1 freshness
> breach.

### Companion rule, and why it is needed

| | |
|---|---|
| **Expression** | `absent(pipeline_slo_breach{pipeline="<id>"}) and on(pipeline) pipeline_status{status="unmeasured"} == 1` |
| **Severity** | medium |

`rounds` publishes **no** `pipeline_slo_breach` sample for a pipeline it could not measure,
because a `0` there would read as "measured, and fine". The absence is deliberate and it means
the first rule can never fire for an unmeasured pipeline. Without this companion rule, a pipeline
whose evidence has gone missing goes quiet rather than alerting — which is exactly how
`use_case_tracking_scheduled` would disappear today.

## Response: tier-1 freshness breach

### What it means

The last write that **changed data** in a table this pipeline owns is older than the pipeline's
own declared SLO in `repo/platform/pipelines.json`. It does **not** mean the job failed. A job
that succeeds and writes nothing trips this alert, and that is the case it exists for: run status
is a claim about the job, not about the data.

### How to tell a real firing from a false one

1. **Check the rounds actually ran.** Every sample is stamped with the as-of instant, not wall
   clock time. Find the most recent `rounds_completed` log event. If it is older than the alert
   window, the series is stale and the alert is reporting a frozen number — fix the rounds job
   first, not the pipeline.
2. **Read the finding, not the gauge.** In `report.md`, find the pipeline and read its findings.
   `table_write_changed_no_data` and `table_older_than_its_freshness_slo` together mean the job
   ran and delivered nothing. `table_older_than_its_freshness_slo` alone with a `job_did_not_run`
   finding means the job is not running at all — a different fix.
3. **Check for a paused schedule.** A `deployed_settings_differ_from_git` finding naming
   `schedule.pause_status` means somebody paused the job by hand in the workspace.
4. **False firing to expect:** a weekly pipeline inside its own 192h SLO is *not* breaching even
   though it looks days old. The alert is per-pipeline against its declared SLO, so if you are
   eyeballing hours rather than the SLO you will mis-read it.

### What to do

1. Open `report.md` and read the finding's evidence. Every line names a file, a table version or
   a run id you can check directly.
2. If the newest write moved zero rows, the problem is upstream of the job, not in it. Check the
   source system first. For the Workday jobs, `repo/docs/runbooks/workday-ingestion.md` lists the
   known failure modes — an expired ISU password returns HTTP 200 with an empty report and no
   exception to catch.
3. Fix the cause, re-run the job from the Jobs UI, and confirm `numOutputRows > 0` in the table
   history before declaring it done.
4. If consumers read the affected tables (`repo/platform/lineage.json` lists them by field), send
   the notice before the next business-hours refresh. See `NOTICE.md`.

### When to escalate

- **Within 1 hour** if the affected table feeds a tier-1 consumer and the cause is not yet
  identified: page the owning team named in `pipelines.json` (`data-platform`).
- **Immediately** if the fix needs a credential rotation or a permission grant — those sit with
  the platform owner, not the on-call engineer, and the Workday ISU rotation needs a request
  through the HRIS queue.
- **Next business day** for a tier-3 pipeline, per the standards table. Do not page overnight
  for `dashboard_parity_daily`.
