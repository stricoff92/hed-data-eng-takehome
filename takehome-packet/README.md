# Morning Rounds — take-home exercise

Thank you for making time for this. This page tells you what the exercise is,
how long it should take, and what happens after you send it back. The
assignment itself is in **[`BRIEF.md`](BRIEF.md)**. Read that next.

---

## Who we are

We are HED's Data & AI team. We run a lakehouse on Databricks: source systems
such as Workday, Deltek and Microsoft 365 land in Bronze, are cleaned in
Silver, and reach Gold, where the reports people open before 9 a.m. and a
growing set of AI tools read from them. We build with AI every day, and AI
agents already help run the platform, including a monitoring agent that reviews
the night's jobs and writes up what it thinks happened.

The person we are looking for keeps that system honest: keeps data flowing,
notices when it stops before anyone else does, and makes sure the answer to
"where does this number come from?" is written down rather than held in one
person's head.

## What we are asking you to do

It is 07:30 on a Tuesday and you have just taken over our data platform. You
have the agent's overnight review and a read-only snapshot of the platform:
what is deployed, what ran, what each table's history says, the repository it
was all deployed from, and the Data Dictionary.

You will build a **small tool** that works out from that evidence what is
actually true about each pipeline this morning and checks the agent's review
against it. Then you will write what an owner writes that morning: what you
would fix first and why, a runbook for one alert, a short notice for the people
affected, and a note on how you used AI.

The snapshot is **one or two steps ahead of where our platform is today**. It
shows where we are heading, and the work is building it.

## Time

- **Two to four hours of work, and we mean it.** If you hit four hours, stop
  and write down what you were about to do next. That reads as a strong
  submission, not a weak one. Twelve polished hours do not score better than
  four honest ones, and usually score worse.
- **Return it within 7 calendar days** of receiving it. If that does not work
  for you, tell the recruiter. A few extra days are not a problem.
- **Tell us how long you actually spent**, in one line. We use it to keep this
  exercise honest at four hours, and it never counts against you.

## What to expect

- **Use AI tools.** Claude, Copilot, Cursor, whatever you normally use. We
  expect it and do not penalise it. We ask for a short note on what you used,
  what you kept for yourself, and anything the tool got wrong that you caught.
- **Any language.** Use whatever you are fastest in.
- **Nothing to set up.** Everything is synthetic JSON, CSV and Markdown. There
  is no network, no account, no credentials and no Databricks workspace. If you
  have not used Databricks before, that is fine; everything you need is in this
  folder.
- **Partial is fine.** A submission that says clearly what it left out beats a
  complete one that fudges. `BRIEF.md` gives the order to spend your time in if
  you run short.
- **Ambiguity is deliberate in places.** Make a call, write the assumption
  down, and keep moving. We will ask you about it, and "I decided X because Y"
  is a good answer.
- **Small is a feature.** A strong submission is a few hundred lines of code
  plus short write-ups. If you are heading past that, you are probably building
  something the brief did not ask for.

## What happens after you send it

1. **Panel review**, about five business days. Several people read your
   submission against the same published dimensions: evidence and honest
   status, platform ownership, documentation and communication, monitoring,
   judgement and triage, and restraint and AI use.
2. **A 60-minute conversation.** Every question is anchored to something you
   wrote. Part of it is a short "what would your tool do if…" walk-through on a
   variation of the snapshot, talked through against your own code. There is no
   live coding and there are no puzzles. Roughly a third of the hour is yours,
   for questions about the team, the platform and the work.
3. **A decision with the reasoning**, within three business days of the
   conversation, whichever way it goes.

The one thing that does not survive the conversation is submitted work you
cannot explain.

## What is in this folder

```
takehome-packet/
├── README.md     this page
├── BRIEF.md      the assignment: what to build, the platform's rules, what to hand in
└── fixtures/     the synthetic platform snapshot your tool reads (fixtures/README.md
                  describes every file)
```

Leave `fixtures/` exactly as you received it. We compare it against the
original, so put your work alongside it, not inside it.

## Sending it back

Send one repository link or one archive to the recruiter, with your
deliverables at the top level and your one-line time note.

**Questions are welcome**, before you start or while you work, and they count
in your favour. Send them to the recruiter and you will have an answer within
one business day. If you need a different format, more time, or any
accessibility adjustment, ask. The answer is yes in principle, and asking never
reaches the review panel.
