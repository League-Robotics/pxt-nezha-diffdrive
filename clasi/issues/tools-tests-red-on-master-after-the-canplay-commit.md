---
status: pending
---

# `tests/tools` is red on master: `tools/DESIGN.md` inventory lags the sprint 043 tools

Found 2026-10-27 while running sprint 042 ticket 001's scoped tests. The
original eight failures were the `tools/canplay/` files commit 7cd5c8d
added without a `tools/DESIGN.md` row, plus one ruff finding and one
`test_angle_wrap_ownership` failure. Those are fixed on master as of
sprint 043's close (`tools/canplay/DESIGN.md` exists, ruff is clean).

Re-run at the 2026-10-27 triage (`uv run pytest tests/tools
--ignore=tests/tools/test_field_dance_accel_bake.py`): 716 passed,
**2 failed**, both `test_tools_design_inventory.py::
test_every_tools_file_is_named_in_design_md`:

- `tools/square_closure.py` (sprint 043 ticket 004)
- `tools/square_progress.py` (sprint 043 ticket 004 follow-up)

Neither has an Inventory row in `tools/DESIGN.md`. Same defect class,
new files: a sprint adds a tool and the inventory gate catches it only
at the NEXT suite run, after the sprint has closed.

Fix: two Inventory rows in `tools/DESIGN.md` saying what each tool is
for (the test's own message says: not what sprint added it). Then the
suite is green with the field-dance file ignored; that file is
`field-dance-test-needs-a-live-camera-daemon-to-collect.md`.

Worth folding into the same out-of-process pass: run the inventory test
as part of every sprint close's checklist so the next tool-adding sprint
does not leave master red.
