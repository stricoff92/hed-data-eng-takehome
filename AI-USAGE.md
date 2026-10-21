# AI usage

## Tools

- Claude Code (Opus 5), from the terminal.


## What I delegated

- cross-platform encoding details
- coding/implementing features
- the testing harness
- writing tests
- running the tests
- Claude put together the tiage order, again I did not have time to review.

## What I kept for myself
- entries in `DECISIONS.md`
- git add/commit/push
- repo layout
- tooling choices (claude model, IDE setup)
- designing  app data model: `files` -> `data` -> `logic`
- designing test data model `test_data` -> `logic`
- claude.md prose (mostly)
- coding standards
- reviewing type issues (these were invisible to claude (no cli for basedpyright))
- "dev roadmap"

## shared
 - code review
 - designing tests
 - Discovery: figuring out what all the fixtures mean


## What the tool got wrong that I caught

- brittle handling of string formatted timestamps (sorting timestamps as strings)
- unreadable function/class/variable names
- --as-of with no timezone crashed. --as-of 2026-10-21T07:30:00 died with TypeError
- --as-of before the snapshot yields negative data ages
- bad formatting in report.md
- initial stub written by claude required a `pip install`
- It recommended the Pylance extension for type checking and wrote the matching. I use VSCodium, where Pylance is unavailable, so the setting did nothing. Switched to basedpyright.
