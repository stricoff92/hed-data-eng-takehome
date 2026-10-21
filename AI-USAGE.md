# AI usage

## Tools

- Claude Code (Opus 5), from the terminal.


## What I delegated

- cross-platform encoding details
- coding/implementing features
- the testing harness
- writing tests
- running the tests


## What I kept for myself
- entries in `DEV-LOG.md`
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


## What the tool got wrong that I caught

- initial stub written by claude required a `pip install`
- It recommended the Pylance extension for type checking and wrote the matching. I use VSCodium, where Pylance is unavailable, so the setting did nothing. Switched to basedpyright.
