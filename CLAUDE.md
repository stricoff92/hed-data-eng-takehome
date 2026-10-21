
# Datapipeline Rounds CLI Tool

# Rules:
 - `takehome-packet/` is readonly. claude settings should enforce this.
 - Do not write any high level parts until directed. The user will carve up the code writing and ask you to implement parts.
 - testing should use unittest module.
 - No third-party libraries.
 - Script should work on Mac / Linux / Windows
 - target Python 3.11 or newer
 - use pathlib over os.path
 - all file reading lives in the loader. Rules take parsed data, never paths,
   so they can be tested with literal inputs and never need mocking
 - findings must carry their provenance (file and line, run id, or table version):
   the brief rejects any reason a reviewer cannot check against a file
 - always pass encoding="utf-8" and newline="\n" when writing to stdout/stderr
 - script outputs go to stdout
 - errors and diagnostics go to stderr. there is no log file
 - never use wildcard imports (`from module import *`). Naming what you import is fine:
   `from pathlib import Path` is correct, `from pathlib import *` is not
 - alphabetize python imports. standard module first, one vertical space, app imports second.

# Terseness
Creating thick abstractions for the sake of extensibility or OOP correctness is not worth it. Solve problems with the simplest, most readable, terse code possible. A human will help highlight verboseness issues when it pops up.

# code style:
 - four space indentation
 - always use type annotations for function signatures
 - maximum line length is 110 characters

# clean code:
- Code Readability must be maintained
- Always follow industry clean code standards. follow the zen of python `python3 -c 'import this'`
- Follow established patterns in the codebase
- Suggest changes to existing patterns when there is a big improvement to readability
- Comments: forbidden by default. Only add one when it documents non-obvious why — hidden constraint, a subtle invariant, a workaround for a specific bug. Never describe what the code does. No section dividers, no method preambles, no JSDoc prose;
- Always follow defensive coding patterns:
```python
# BAD
if foo == bar:
    foobar()
else:
    foobaz()

# GOOD
if foo == bar:
    foobar()
elif foo == baz:
    foobaz()
else:
    raise NotImplementedError(f"unhandled foo: {foo}")
```

- Do not let errors pass silently. If the error is fatal, log the traceback and crash the program. If the error can be handled: handle it. If it cannot be handled and it's not fatal: log it.
- Do not use abbreviations, unless the object is locally scoped. even when locally scoped prefer to avoid abbreviations
- No magic numbers, or magic string. Use constants, enums.
- Use C style naming convention for constants: `CUSTOMER_TYPE_PREMIUM = "premium"`
- Each unittest and integration test should tell a story about how the app works. If a code comment helps tell that story add a comment. Prefer to write extremely readable tests instead of writing comments in tests.
- Test names should be very long and descriptive, for example: "test_the_name_validator_raises_a_validation_error_when_the_name_starts_with_illegal_character"
- Function names should be descriptive. A long function name is better than a cryptic one.
- in python code: use the following casing
```python
# Pascal Case for classes
class MyClass: ...

# snake case for functions and variables
def my_func(): ...

# Capitalized snake case for global constants
MY_CONST = 67
```
