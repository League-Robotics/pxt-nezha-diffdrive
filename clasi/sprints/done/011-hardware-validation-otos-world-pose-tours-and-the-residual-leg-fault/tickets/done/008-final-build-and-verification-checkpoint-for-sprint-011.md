---
id: 008
title: Final build and verification checkpoint for sprint 011
status: done
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
github-issue: ''
issue: ''
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

- [x] All prior tickets (001-007) are done.
      **Done:** confirmed via `list_tickets(sprint_id="011")` — all
      seven (001-007) report `status: done` with paths already under
      `tickets/done/`. Not taken on faith: verified independently.
- [x] `uv run pytest` (the full suite) passes.
      **Done:** `583 passed in 28.38s`, run in the foreground.
- [ ] If, and only if, ticket 003 landed a `motion_engine.cpp`/`.h`
      change: `uv run python tools/make_deploy.py` produces a flashable
      hex, retrying once on the documented benign abort shapes
      (`tools/DESIGN.md`'s triage classification) before treating a
      failure as real. Record the hex's path/size in this ticket's own
      notes.
      **N/A — condition false.** Confirmed via `git diff
      master...HEAD --stat -- src/` (empty output) and ticket 003's own
      closed notes: ticket 003 found the `moveDeadline` boundary CLEAN
      and landed no `src/` change. This criterion's own trigger
      condition never fires this sprint; see the next criterion (and
      its **Done** note) for the build that was actually run.
- [x] If no `src/` file changed this sprint (the expected case if
      ticket 003 finds a clean boundary and ticket 004 finds no
      concrete mechanism): this ticket's notes state that explicitly,
      and the `make_deploy.py` run is still performed as a sanity
      check that nothing else in the tree (e.g. a `pxt.json` change,
      though none is planned) broke target viability — the full-suite
      host-test pass plus a green build remain this ticket's bar
      either way.
      **Done — no `src/` file changed this sprint** (verified above).
      Ran the build anyway, per this dispatch's explicit instruction to
      treat it as cheap insurance rather than skip it on the
      technicality — this project has twice shipped a fully-green host
      suite with a firmware build that could not produce a hex (a
      `pxt.json` `files` omission and a C++11 aggregate-init
      regression), and host tests structurally cannot catch either
      because they never read `pxt.json` and compile at a newer
      standard than the target. Removed the pre-existing primary hex
      (`.tmp/deploy-head/built/mbcodal-binary.hex`) before building, so
      a fresh success could not be confused with a stale leftover, then
      ran `uv run python tools/make_deploy.py` (build only, no
      `--flash`). The log showed both documented-benign shapes in
      sequence — the legacy V1 `bbc-microbit-classic-gcc` hex-merge
      failure (`srec_cat: ... contradictory ... value`) and a `TS9200`
      packaging abort — but the codal-microbit-v2 hex already existed
      by the time `classify_attempt()` ran, so the verdict was
      `SUCCESS` on **attempt 1, no retry needed** (triage rule: a
      compile-diagnostic check runs first and found none; hex
      existence alone then decides, before the benign-shape checks are
      even consulted). Result: `.tmp/deploy-head/built/mbcodal-binary.hex`,
      **1,395,296 bytes**, mtime `2026-08-25 09:00:05` — freshly
      written (verified via `ls`/`stat`, not merely "exists," since
      `TS9283`-style aborts are documented to delete this file on
      failure and an `ls` alone cannot distinguish a fresh build from a
      stale survivor).
- [x] This ticket's own notes state explicitly, in writing, that no
      flashing and no hardware/bench validation of any kind was
      performed as part of closing this ticket or this sprint — three
      bench sessions (tickets 005, 006, 007) are handed off separately
      and are the stakeholder's own follow-up.
      **Stated explicitly: no flashing (no `--flash`, no `mbdeploy`
      call) and no hardware/bench validation of any kind was performed
      in closing this ticket or this sprint.** This was a build/host-
      suite checkpoint only. The three bench sessions this sprint's
      tooling and procedures were built for — ticket 005's OTOS
      world-pose campaign, ticket 006's residual leg-fault campaign,
      and ticket 007's brick-reset handoff (all folded into one
      combined bench sitting per the issue files' procedures) — remain
      entirely unrun and are the stakeholder's own follow-up, exactly
      as scoped.
- [x] `design/tools-root-DESIGN.md` and `design/src-root-DESIGN.md`
      are re-read against what this sprint's tickets actually shipped;
      confirm both overlays' content matches (particularly ticket
      003's conditional outcome, once known) before this ticket closes
      — if either overlay still describes a planned-but-not-actual
      outcome, correct it and regenerate its `.diff.md` by hand.
      **Done — staleness found and corrected in both files.**
      `src-root-DESIGN.md`'s §15 and its own header status line still
      described ticket 004's `shims.cpp` first-move-after-boot review
      as "outcome still pending as of this edit" / "code-review only,"
      even though ticket 004 is done and its issue-file finding is
      final (a real, confirmed-by-code-review mechanism — the
      `kNeverWritten` slew-rate sentinel — not hardware-confirmed, no
      source change landed, deferred to ticket 006's bench probe).
      Corrected the header status line, §15's intro sentence, the
      `shims.cpp` Sprint Changes bullet, and the Open Questions section
      to state that resolved outcome instead. `tools-root-DESIGN.md`
      had the mirror problem: its header status line and the
      `tour_capture.py`/`leg_analysis.py` bullets were still written
      prospectively ("planned," "still selects its tour with a numeric
      verb") even though ticket 001 (the retarget) and ticket 002
      (`leg_analysis.py`) are both done; corrected to past tense/"done"
      status, and the "Sprint 011 update" paragraph's "will speak named
      verbs" future tense corrected to "now speaks." Both `.diff.md`
      files regenerated via `clasi.design.overlay.generate_diffs()`
      (run against this sprint's `design/` directory), then each
      intro paragraph hand-rewritten afterward (the tool itself only
      emits a generic "Comparison of..." line) to describe the final,
      actual content — same convention ticket 003 used. Deliberately
      left the incidental sprint-005-status mentions elsewhere in
      `src-root-DESIGN.md` (e.g. "roadmapped, not yet detail-planned"
      in the pre-existing telemetry-gap prose) untouched — those
      predate sprint 011's own scope and are a different sprint's
      status, not "this sprint's tickets," so correcting them is out of
      this ticket's scope per its own "stay focused" convention.
- [x] `clasi design validate` / `validate_design` (with `overlay_dir`
      pointed at this sprint's `design/` directory) returns `ok: true`
      as this ticket's own final check before the sprint closes.
      **Done:** `validate_design(overlay_dir="clasi/sprints/011-.../design")`
      returned `{"ok": true, "messages": []}` (three unrelated `info`
      notices about non-subsystem top-level docs, no effect on `ok`).

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
