# Claude Code conventions for smartdoc

## Running temporary test scripts

Write throwaway scripts to `_tmp.py` in the project root and run with:

```bash
.venv/bin/python3 _tmp.py 2>&1
```

This ensures the correct virtualenv is used and both stdout and stderr are captured.

## Running one-off commands

Always use `_tmp.py` for quick checks (dependency availability, data exploration, etc.) instead of running Python one-liners directly in the shell.

## Handling external reviews

When reacting to an external review of the implementation:

1. **First** — write a `REVIEW_RESPONSE_<phase>.md` file with analysis of each finding (agree/disagree, root cause, impact).
2. **Second** — write a `REVIEW_PLAN_<phase>.md` file with the concrete fix plan (what to change, where, in what order).
3. **Stop and present both files** to the user for approval before implementing any fixes.
