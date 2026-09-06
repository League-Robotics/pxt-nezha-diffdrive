---
title: "tests/tools/test_field_dance_accel_bake.py cannot be collected without a live aprilcam daemon"
status: pending
created: 2026-09-06
---

# `test_field_dance_accel_bake.py` needs a live camera daemon just to import

`tests/tools/test_field_dance_accel_bake.py` does `import field_dance`
(the `tools/field_dance.py` shim, which exec-loads
`tests/calibration/field_dance.py`). That module resolves the aprilcam
daemon at import time (`D = _daemon()` at module scope, via
`aprilcam.mcp.connection`), so with no daemon running `uv run pytest`
dies during COLLECTION with `aprilcam.errors.ConnectionFailed: daemon
at 'localhost' did not answer` -- the whole suite is interrupted, not
one test skipped.

Seen 2026-09-06 closing sprint 035: the suite had passed at the sprint
033 and 034 closes only because a daemon happened to be up. Sprint 035
was closed with that file excluded
(`--ignore=tests/tools/test_field_dance_accel_bake.py`); it is the same
defect class sprint 034 ticket 010 fixed for the `tsc` gate (an
environment precondition surfacing as a red suite).

Fix: make `tests/calibration/field_dance.py` resolve the daemon lazily
(inside `main()` / the functions that need it), so importing it for
the accel-bake pure functions costs nothing; or have the test import
the pure helpers from a module that does not touch the daemon; and, as
a belt-and-braces measure, `pytest.skip` with a reason naming the
daemon when the connection fails. Keep the daemon-needing behaviour
for the real calibration run. Verify with the daemon stopped:
`uv run pytest -q` must collect cleanly.
