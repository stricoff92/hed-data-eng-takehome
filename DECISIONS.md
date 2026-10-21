
# DECISIONS

```
Short — a page, maybe two. We are reading for judgement, not volume:

The decisions you made and what you traded away for them.
Triage order: it is 07:30. What do you fix first, second, third — and why in that order?
Buy vs build: what you would not have written yourself on a real platform — Databricks-nativae options, third-party data-observability tools — and what each would cost you. Include a sunset trigger: the observation that would tell you this tool has outlived its design.
The thing you are least sure about. One honest paragraph on where your judgement could be wrong, and what evidence would settle it. This section carries real weight with us.
What you would do with another day, in priority order.
```


## Least Sure


## What kind of static type checking should I use for python?
- A python package like `mypy` or an IDE extension.
- I decided to use an IDE extension (not part of the repo) in order to satisfy contraints in the brief (checkout then run), and to get the project running ASAP.

## what data model does the tool use? How are tests structured
 - the CLI: `FILES` -> `loader` -> `DATA` -> `logic` -> `outputs`
 - unit tests: `DATA` -> `logic`
 - e2e "smoke" tests: same as the cli, zero mocked data.

## Should I leave Claude in Auto mode?
 - YES, because
   - 2 to 4 hour time constraint
   - git is in place as a backup
   - relatively low stakes (no one is going to die or lose $ 10M)
   - the chance of a claude induced disaster is low
   - claude settings protect certain files
   - I expect claude will understand the project without issues
