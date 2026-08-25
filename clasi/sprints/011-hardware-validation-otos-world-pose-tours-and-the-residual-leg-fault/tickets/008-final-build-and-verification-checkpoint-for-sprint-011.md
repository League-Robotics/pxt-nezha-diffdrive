---
id: "008"
title: "Final build and verification checkpoint for sprint 011"
status: open
use-cases:
- SUC-008
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
- '006'
- '007'
github-issue: ""
issue: ""
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Final build and verification checkpoint for sprint 011

## Description

Per the standing sprint 008 convention (`tools/DESIGN.md`'s "Build
checkpoint triage" section, `docs/design/design.md`'s matching
convention statement): every sprint that touches build-eligible source
includes a mandatory, always-last build-checkpoint ticket. This ticket
is not tied to any single linked issue — it verifies this sprint's
*combined* final state, whichever of tickets 001-007 actually changed
`src/` (most are planned as Python/documentation-only; ticket 003 may
or may not land a `motion_engine.cpp` fix, per its own conditional
scope).

**This is a build/host-suite checkpoint, not a hardware one** — same
posture as sprint 004 ticket 005 and sprint 006 ticket 006. No
flashing, no live telemetry capture, no bench validation is performed
here. That is exactly what tickets 005, 006, and 007 hand off to the
stakeholder separately.

## Acceptance Criteria

- [ ] All prior tickets (001-007) are done.
- [ ] `uv run pytest` (the full suite) passes.
- [ ] If, and only if, ticket 003 landed a `motion_engine.cpp`/`.h`
      change: `uv run python tools/make_deploy.py` produces a flashable
      hex, retrying once on the documented benign abort shapes
      (`tools/DESIGN.md`'s triage classification) before treating a
      failure as real. Record the hex's path/size in this ticket's own
      notes.
- [ ] If no `src/` file changed this sprint (the expected case if
      ticket 003 finds a clean boundary and ticket 004 finds no
      concrete mechanism): this ticket's notes state that explicitly,
      and the `make_deploy.py` run is still performed as a sanity
      check that nothing else in the tree (e.g. a `pxt.json` change,
      though none is planned) broke target viability — the full-suite
      host-test pass plus a green build remain this ticket's bar
      either way.
- [ ] This ticket's own notes state explicitly, in writing, that no
      flashing and no hardware/bench validation of any kind was
      performed as part of closing this ticket or this sprint — three
      bench sessions (tickets 005, 006, 007) are handed off separately
      and are the stakeholder's own follow-up.
- [ ] `design/tools-root-DESIGN.md` and `design/src-root-DESIGN.md`
      are re-read against what this sprint's tickets actually shipped;
      confirm both overlays' content matches (particularly ticket
      003's conditional outcome, once known) before this ticket closes
      — if either overlay still describes a planned-but-not-actual
      outcome, correct it and regenerate its `.diff.md` by hand.
- [ ] `clasi design validate` / `validate_design` (with `overlay_dir`
      pointed at this sprint's `design/` directory) returns `ok: true`
      as this ticket's own final check before the sprint closes.

## Implementation Plan

**Approach:** Run the existing deploy pipeline only if a `src/` change
landed; otherwise this ticket is a full-suite test run plus an overlay
accuracy re-check. Do not touch source.

**Files to modify:** none under `src/` or `tests/`, unless recording
this ticket's own build-verification notes. If `design/` overlay
content needs correcting per the Acceptance Criteria above, that edit
is in scope.

**Testing plan:**
- Run the FULL suite once (`uv run pytest`), matching this project's
  once-per-sprint full-run convention.
- If `src/` changed: run `uv run python tools/make_deploy.py`,
  retrying once on the known nondeterministic abort shapes.
- **Verification command:** `uv run pytest` (and `uv run python
  tools/make_deploy.py` if `src/` changed this sprint).

**Documentation updates:** this ticket's own bench-handoff summary
(pointing at tickets 005/006/007's procedures as the stakeholder's next
step) plus whatever `design/` overlay corrections the Acceptance
Criteria's re-check surfaces.

## C++11 Gate Coverage

- If ticket 003 landed a `motion_engine.cpp` fix: already inside
  `tests/host/test_cxx11_syntax_gate.py`'s existing coverage (confirmed
  during this sprint's planning) — no new gate wiring needed.
- If no `src/` change landed this sprint: not applicable — this
  ticket's own `make_deploy.py` run is still a valid target-viability
  sanity check regardless, per the Acceptance Criteria above.
