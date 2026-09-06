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
