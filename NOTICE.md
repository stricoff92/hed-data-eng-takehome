# Workforce data in the Staffing Report has not changed since 17 October

**Who this is for:** anyone reading the **Staffing Report** or using **Attendance Accuracy**.
**As of:** 20 October 2026, 07:30 America/New_York.

## What changed

The nightly load that brings Workday worker records into the platform has been running and
reporting success every morning, but it has been bringing back **no records at all** since
Saturday 17 October. The last load that actually changed anything ran on 17 October at 06:06.

Because the load succeeds, nothing looked wrong. The employee tables are rebuilt every morning
from the same unchanged records, so both the report and the app show a fresh timestamp over
three-day-old data.

## What it means for the numbers you have been looking at

- Headcount, worker status and office assignments reflect **Workday as of 17 October**, not
  today. Anyone hired, moved, put on leave or terminated since Saturday is **not** reflected.
- Nothing shown to you is wrong for 17 October. It is not a calculation error and no figures
  have been restated. The data is simply older than the report's own timestamp suggests.
- Attendance Accuracy compares meeting attendance against the employee list, so a person who
  joined after 17 October will not be matched and may appear as an unknown attendee.

## The fields affected, and what the Data Dictionary says about them

| Field | What the Data Dictionary says |
|---|---|
| `employee_id` | "Unique Workday employee identifier." Approved, owned by People Analytics — S. Patel |
| `home_office` | "Office the employee is assigned to in Workday, not the office they badge into." Approved, same owner |
| `employment_status` | "Workday worker status (Active, Leave, Terminated) as of the last snapshot." Approved, same owner |
| `display_name` | **Nobody has written a definition down.** The row is marked *Needs Review* and has no business owner (`dictionary/data-dictionary.csv:3`) |

We have not guessed at what `display_name` means. If how that field is produced matters to a
decision you are about to make, **People Analytics needs to confirm it first** — there is
currently no owner recorded to ask.

## What happens next

1. The platform team is treating the stalled Workday load as the first thing to fix this
   morning. The cause is being confirmed against the ingestion runbook.
2. Once records flow again, the employee tables rebuild on the next nightly run and the report
   catches up without any action from you.
3. We will send a short follow-up on this thread confirming the date the data is current to.

**Until then:** treat workforce figures as current to **17 October**. If you need today's
position for a specific person or team, ask People Analytics directly rather than reading it
from the report.

Questions: the data platform team (`data-platform`).
