
# DECISIONS



## Least Sure
 - How to manage time. Without AI I have no choice but to fully digest concepts before I can implement and move on. with AI it's possible to build without fully digesting. with a 4 hour time limit and a bunch of unfamiliar data structures and terms: tough choices need to be made.

## Triage order

tier first, then whether consumers are reading wrong data right now:

  1. workday_bronze_daily (t1) — succeeding while writing zero rows for 3 days. Start first because the fix is a credential rotation through the HRIS queue, so it blocks on other
     people.
  2. deltek_helix_daily_refresh (t1) — the financials table dropped net_fee/fee_currency; Finance's report reads both by name.
  3. dim_projects_daily (t1) — hard failure, 0.1h inside its SLO, about to breach. Fast and self-contained.
  4. mm_rapid_pipeline_30min (t1) — stop job 1188; one action closes the retry storm and the undeclared-job finding.
  5. use_case_tracking_scheduled (t2) — a permission grant, not an engineering fix. Blind until it lands.
  6. dashboard_parity_daily (t3) — worst staleness in the pack (8.4× SLO) but tier 3 is next-working-day.




## What kind of static type checking should I use for python?
- A python package like `mypy` or an IDE extension.
- I decided to use an IDE extension (not part of the repo) in order to satisfy contraints in the brief (checkout then run), and to get the project running ASAP.

## what data model does the tool use? How are tests structured
 - the CLI: `FILES` -> `loader` -> `DATA` -> `logic` -> `outputs`
 - unit tests: `DATA` -> `logic`
 - e2e "smoke" tests: same as the cli, zero mocked data.

## Should we leave Claude in Auto mode?
 - YES, because
   - 2 to 4 hour time constraint
   - git is in place as a backup
   - relatively low stakes (no one is going to die or lose $ 10M)
   - the chance of a claude induced disaster is low
   - claude settings protect certain files
   - I expect claude will understand the project very clearly

## Do we validate the fixture files?
 - no, out of scope


## Do we check for drift between the cron format and the cadence string format (pipeline.json vs databrick)
 - no, claude spot checked and said they match


