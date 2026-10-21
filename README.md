# Morning Rounds

## Running it

No install, no virtualenv, no third-party packages:

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
