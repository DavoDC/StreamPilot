#!/bin/bash
# PreToolUse guard - delegates all checks to guard.py
# Python in a .py file has no shell-quoting constraints - any string content is safe.
# Exit 0 = allow, Exit 2 = block with message

PY=$(command -v python3 || command -v python) || exit 0
SCRIPT="$(dirname "$0")/guard.py"

# If guard.py has a syntax error: fail-open so Claude can self-repair without human intervention.
# Print a clear warning so the broken state is visible.
if ! $PY -m py_compile "$SCRIPT" 2>/tmp/guard_pyc_err.txt; then
    echo "WARNING: guard.py has a syntax error - safety checks bypassed until fixed:" >&2
    cat /tmp/guard_pyc_err.txt >&2
    exit 0
fi

$PY "$SCRIPT" || exit 2
