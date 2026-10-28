---
title: "test_consolidation_acceptance.py writes into the real captures/ directory and reads the real Shelly"
status: pending
created: 2026-09-06
---

# `test_consolidation_acceptance.py` writes into the real `captures/` dir

Running the host suite (`uv run pytest`) on 2026-09-06 left eight
`BLOCKED` sections in
`captures/consolidation-acceptance-tovez-20260906/notes.md` -- the REAL
capture file for that day's on-field run -- each headed
`command: .../pytest tests/calibration/test_consolidation_acceptance.py`
and reporting `lights BLOCKED output=false`. So at least one test drives
`run_session()` with the default capture dir and the real
`check_lights()` HTTP getter instead of a tmp dir and an injected
getter. That both pollutes evidence and makes the test's outcome depend
on the room lights.

Also worth folding in: `tools/wire_acceptance.py`'s two sprint-033
checks (`GET rebase -> err 12`, reserved ceiling id -> `nack + err 3`)
FAIL on a pre-033 firmware (tovez 1.20260905.1, MEASURED 2026-09-06,
same capture file); they should BLOCK with the `ver` named instead.

Fix: `tmp_path` capture dir and an injected `get_json` in every
`run_session` test; a guard that the test never touches
`captures/`; version-gate the two wire checks.

---

## Triage 2026-10-27 — still happening, KEEP

`captures/` now holds nine `consolidation-acceptance-tovez-<date>/`
directories (20260906 through 20261027), one for every day the suite
ran; today's holds a `notes.md` written by this run's pytest. The writer
is `test_a_blocked_preflight_leaves_the_three_checks_unrun`
(`tests/calibration/test_consolidation_acceptance.py`), which sets
`args.capture_dir = None` so `run_session()` falls through to
`default_capture_dir(args.robot)`, i.e. the real `captures/` tree with
today's date. The getter IS injected now (`get_json=lambda ...`), so the
room-lights dependence is gone; the pollution is not. `captures/*` is
gitignored, which is why `git status` never showed it.

Fix is a `tmp_path` capture dir in that one test (pass `--capture-dir
<tmp>` and stop nulling it), plus the guard the issue already asks for.
Then delete the nine fake capture directories, which contain no
measurements.
