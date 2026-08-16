# Dev Context

Implementation-level notes for working in this codebase. Demand-loaded (not auto-read every session) - read this before touching `daemon.py`'s state/classification logic.

## Consume-once suppression flags in `_classify()`

`daemon.py`'s `_classify()` distinguishes "user-caused, expected transient state" from "genuine fault" via consume-once suppression flags set on the daemon instance and cleared on the very next heartbeat (see `_sab_just_enabled`/`sab_suppress_issue` and `_manual_restart_pending`/`restart_suppress_issue`). If a future feature deliberately causes a brief, expected dip in a signal `_classify()` watches (OBS state, SAB pause state, etc.), reuse this pattern rather than assuming the resulting ISSUE flash is unavoidable - add a new `_<feature>_pending` flag, consume it in `_print_heartbeat()`, and thread it through `_classify()`/`_format_heartbeat()` as an additional parameter, scoped narrowly enough that it doesn't suppress the daemon's own genuine auto-recovery fault detection for the same signal.
