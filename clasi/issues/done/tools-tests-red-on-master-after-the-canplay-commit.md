---
status: done
---

# `tests/tools` is red on master after the canplay commit

Found 2026-10-27 while running sprint 042 ticket 001's scoped tests on a
branch whose `tools/` and `tests/tools/` are identical to master
(`git diff master -- tools tests/tools` empty). With
`tests/tools/test_field_dance_accel_bake.py` ignored (it cannot be
collected without a live camera daemon; separate issue), 8 tests fail:

- `test_tools_design_inventory.py` (7): `tools/DESIGN.md`'s inventory
  does not list the files commit 7cd5c8d added under `tools/canplay/`
  (`duo.py`, `matcam.py`, and others) and `tools/canplay` has no
  `DESIGN.md`.
- `test_angle_wrap_ownership.py` (1).
- `test_ruff_clean.py` (1): ruff findings in the new tools.

Pre-existing on master, not a sprint 042 defect. Sprint 042's close runs
the full suite, so these must either be fixed first (an out-of-process
inventory/ruff pass on master) or the close must document them as known
failures. Recorded here so the decision is explicit.
