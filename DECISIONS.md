

## What kind of static type checking should I use for python?
- A python package like mypy that's part of the repo is robust.
- I decided to use an IDE extension (not part of the repo) in order to satisfy contraints in the brief (checkout then run), and to get the project running ASAP.

## what data model does the tool use? How are tests structured
 - the CLI: `FILES` -> `loader` -> `DATA` -> `logic` -> `outputs`
 - unit tests: `DATA` -> `logic`
 - e2e "smoke" tests: same as the cli, zero mocked data.

