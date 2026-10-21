# Morning Rounds

## Running it

```
python3 rounds.py check --fixtures takehome-packet/fixtures
```

On Windows, use `py rounds.py check --fixtures takehome-packet\fixtures`.

`--fixtures` already defaults to `takehome-packet/fixtures`, so plain
`python3 rounds.py check` works from the repository root.

## Running the tests

```
python3 -m unittest discover -v
```

## Type checking

Annotations target **basedpyright strict**, set in `.vscode/settings.json`. The checker is
not a project dependency; nothing needs installing to run `rounds` or the tests.

To check from a shell, with the venv outside the repo:

```
python3 -m venv /tmp/tc && /tmp/tc/bin/pip install basedpyright
printf '{"typeCheckingMode":"strict","include":["rounds.py","morning_rounds","tests"]}' > pyrightconfig.json
/tmp/tc/bin/basedpyright; rm pyrightconfig.json
```

Clean under `strict`. The CLI defaults to `recommended`, which is stricter again and flags
`reportAny` where JSON enters the program (`loader.read_json`, `Job.settings`) — deliberate:
validating a read-only fixture pack buys nothing.
