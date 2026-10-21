# Technical Assessment — Morning Rounds

**What is actually true about the platform at 07:30**

Time box: **2–4 hours.** We mean it. Read [Scope and time](#scope-and-time)
before you start.

---

## Why we are asking you to build this

It is **07:30 in New York on Tuesday 20 October 2026**. You are the new owner of
our data platform: the Databricks jobs, the Delta tables they write, the
contracts on the governed ones, the Data Dictionary, and the alerts. Reports
that people open before 09:00 are built from these tables.

Overnight, an agent — `pipeline-health-monitor` — did the morning review and
left it on your desk. It says what it checked, what it found, and that no
action is required beyond one weekly job. Like every agent, it will tell you
things that are true, things that are partly true, and things it has no basis
for. Reading its prose for reassurance is not ownership.

You also have a read-only snapshot of the platform as it stood at 07:30 (11:30
UTC): what was deployed, what ran, what each table's history says, and the
repository it was all deployed from. Four principles hold the platform
together, and you will see all four in this exercise:

| Principle | What it means here |
|---|---|
| **Run status is a claim about the job, not the data** | "The job succeeded" says nothing about whether consumers are reading new, correct data |
| **Never misreport** | A pipeline that **failed**, one that **did not run**, one that **ran and wrote nothing**, and one that **cannot be measured** are four different findings, and must reach the reader as four different sentences |
| **Git is the source of truth** | What is deployed should be reproducible from the repository; anything else is drift, and the fix goes through Git |
| **Every alert gets a runbook** | An alert without a runbook is a tax on whoever opens the email |

**What you are building is the tool that does the morning review from
evidence**, and checks the agent's review against it. We call it `rounds`.

You are not being asked to build a pipeline, call a model, or connect to
Databricks. You are being asked to build the part that refuses to be
reassured — which, in our experience, is most of owning a platform.

---

## Where this is going

This packet is **one or two steps ahead of where HED is today**. The job you
would be hiring into is building it.

| Today | In this packet |
|---|---|
| Job definitions in Git; per-job metrics in Grafana | A declared **pipeline registry** with cadence, freshness SLO and tier (`repo/platform/pipelines.json`) |
| Lineage known by the people who built the tables | **Field-level lineage** down to the consumers that read each field (`repo/platform/lineage.json`) |
| One schema-drift contract test per governed write path | **Contracts as data** (`repo/contracts/*.json`) |
| A human does the daily review | **An agent does the morning review, and its claims are verified by code** — not believed |

Where the packet is more organised than a real platform would be, that is
deliberate: it is the shape we want, so you can spend your time on the
judgement rather than on archaeology.

---

## What you are building

A command-line tool, in any language. We call ours `rounds`:

```
rounds check --fixtures ./fixtures
```

`--fixtures` points at the fixture pack wherever you keep it, unmodified.
"Now" is `workspace/manifest.json` → `captured_at`. An `--as-of` override is
optional.

### 1. A status for every registered pipeline

For each pipeline in `repo/platform/pipelines.json`, exactly one of:

| Status | Meaning |
|---|---|
| **healthy** | The evidence supports that consumers are reading current, correct data |
| **degraded** | The data is fine for now, but something is wrong that will bite |
| **broken** | Consumers are, or will shortly be, reading wrong or old data — or the job failed |
| **unmeasured** | The evidence needed to judge is missing. Not healthy, not broken |

Each non-healthy pipeline carries **findings**. A finding says:

- **what** is wrong, and **why** — the cause where the evidence supports one,
  marked as inference where it does not;
- the **evidence** it rests on — a `run_id`, a file and line or table version,
  a field;
- its **blast radius** — the downstream tables and consumers affected, from
  lineage;
- the pipeline's **tier**.

### 2. Platform findings

Some findings belong to the platform rather than to one pipeline. Report them
too, with the same discipline. Whether a given finding degrades a pipeline or
belongs only to the platform is your call: be consistent, and say which you
chose in `DECISIONS.md`.

### 3. Agent reconciliation

For each claim in `agent/morning-review-2026-10-20.json`, a verdict of exactly
one of the following, citing the evidence:

| Verdict | Meaning |
|---|---|
| **verified** | Everything the claim asserts, including any status it gives, is supported by the evidence |
| **contradicted** | The evidence contradicts any part of the claim. Say which parts are true |
| **unverifiable** | The evidence needed to judge the claim is missing |

Then list the registered pipelines the agent did not mention.

### 4. Telemetry

Emit the gauges your tool owns as newline-delimited JSON in the envelope
described in `fixtures/README.md`. `gauges.json` says who owns what. Some of
the catalog belongs to other producers, and some of it is not wired yet — a
priced cost source, for instance.

### Output

A machine-readable report (`report.json`), a human-readable one
(`report.md`), and the telemetry (`telemetry.ndjson`). Every reason in them
must cite an artifact. A reason a reviewer cannot check against a file is not a
reason.

---

## The rules of the platform

These are the rules of the platform you are joining. Each one exists because
it was broken at least once.

1. **Run status is a claim about the job, not about the data.** Freshness is
   measured from writes that changed data.
2. **A table touched only by maintenance has not been refreshed.**
3. **Freshness is judged against each pipeline's own declared cadence and
   SLO**, not a global window.
4. **Git is the source of truth for jobs.** Anything deployed that differs from
   Git — or is not in Git — is drift.
5. **A governed table's deployed schema must match its contract.**
6. **A finding names its blast radius from lineage**, down to the field where
   lineage allows.
7. **An agent's claim is verified against evidence or labelled as
   unverifiable.** A cited artifact that does not exist contradicts the claim.
8. **Missing evidence is `unmeasured`**, never `healthy` and never `broken`.
9. **A gauge nobody measured is not published; gauges owned by another
   producer are not republished.**

We have not told you which pipelines violate which rule. That is the exercise.

---

## Deliverables

| # | Deliverable | Notes |
|---|---|---|
| 1 | **Working tool** | `rounds check`, run from a README instruction that works on a clean checkout |
| 2 | **Tests** | A few tests for the rules you would least want to regress. We are looking for judgement about what deserves a test, not a coverage number |
| 3 | **The report for the shipped snapshot** | `report.json`, `report.md` and `telemetry.ndjson`, committed |
| 4 | **`README.md`** | How to run it, how it is put together, what you did not build |
| 5 | **`DECISIONS.md`** | The architecture note. See below |
| 6 | **`RUNBOOK.md`** | One alert rule written against your telemetry — expression, threshold, severity, the sentence a recipient reads at 8am, and the runbook link (any form that resolves inside your submission; a relative link to an anchor is fine) — plus its response section: what it means, how to tell a real firing from a false one, what to do, when to escalate |
| 7 | **`NOTICE.md`** | The notice to consumers for the most consumer-visible problem your rounds turned up. See below |
| 8 | **`AI-USAGE.md`** | See [Using AI tools](#using-ai-tools) |

### `DECISIONS.md`

Short — a page, maybe two. We are reading for judgement, not volume:

- The decisions you made and what you traded away for them.
- **Triage order**: it is 07:30. What do you fix first, second, third — and why
  in that order?
- **Buy vs build**: what you would not have written yourself on a real
  platform — Databricks-native options, third-party data-observability tools —
  and what each would cost you. Include a **sunset trigger**: the observation
  that would tell you this tool has outlived its design.
- **The thing you are least sure about.** One honest paragraph on where your
  judgement could be wrong, and what evidence would settle it. This section
  carries real weight with us.
- What you would do with another day, in priority order.

### `NOTICE.md`

One page at most, written for **the people who read the affected report** —
not for engineers. Choose the problem whose consumers most need to hear from
you this morning, and say in `DECISIONS.md` why that one. Plain language: what
changed, since when, what it means for the numbers they have been looking at,
and what happens next.

Say what the Data Dictionary does and does not say about the affected fields.
**Never invent a definition.** Where nobody has written one down, say so, and
say who needs to confirm it. A blank beats a guess.

---

## Scope and time

**Two to four hours.** A partial submission with a clear account of what is
missing scores better than a complete one that fudges. If you reach the time box
mid-thought: stop, and write down what you were about to do.

**If you run short**, spend the time in this order:

1. Pipeline statuses with cited evidence.
2. Agent reconciliation.
3. `DECISIONS.md` — the triage order and the least-sure paragraph first.
4. `NOTICE.md`.
5. Telemetry and `RUNBOOK.md`.
6. Tests.
7. Buy vs build.

A strong human submission is a few hundred lines of code. More is not better.

We are **not** grading you on: language or framework choice (use whatever you
are fastest in), a package published to a registry, containerisation, a web UI,
a database, or test coverage as a percentage. None of that earns a point here.
Building any of it will cost you time you needed elsewhere.

If something in this brief is ambiguous, make a call, write the assumption down,
and keep moving. Recording the assumption *is* the correct answer — we will ask
you about it, and "I decided X because Y" is a strong response.

---

## Using AI tools

**Use them.** Claude, Copilot, Cursor, whatever you work with. We build with
these tools every day and we are not interested in how you perform without them.
Their use will not be held against you.

Note that the morning review you are checking is itself AI output. That is
partly the point: the job is to make the platform legible to agents and to
verify what they claim, and the same discipline applies to the tools you use to
build `rounds`.

We do ask you to keep a short `AI-USAGE.md`: which tools, what you delegated,
what you kept for yourself, and — most usefully — **anything the tool got wrong
that you caught**. We will ask about that last part.

The one thing that does not survive: submitted work you cannot explain. We will
walk through your code with you.

---

## What happens next

1. You send us a repository or an archive.
2. A panel reviews the submission against a published rubric — evidence and
   honest status, platform ownership and contracts, documentation and
   communication, monitoring and signal design, judgement and triage, restraint
   and AI use. Every score we record has to cite something you actually wrote.
3. **60-minute conversation**, and every question in it is anchored to your own
   submission. Part of it is a short "what would your tool do if…" walk-through
   on a variation of the snapshot, talked through against your own code. There
   are no puzzle questions and no live coding. Roughly a third of the hour is
   yours for questions about the team, the platform, and the work.

We will tell you which way the decision went either way, with the reasoning.

---

## Submitting

Include everything in one repository or archive, with the fixture pack left as
you received it (unmodified — we diff it). Please include:

- Your deliverables, at the top level.
- A one-line note of how long you actually spent. We use it to calibrate this
  assessment, and it never counts against a candidate.

Questions before you start are welcome and are not a mark against you. Send them
to the recruiter and we will answer within one business day.
