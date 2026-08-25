---
id: '003'
title: Investigate moveDeadline duration math for truncating legs
status: open
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: intermittent-cw-pivot-abort-wheel-reversal.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Investigate moveDeadline duration math for truncating legs

## Description

The residual-fault issue's second next-probe: check the `moveDeadline`
path (duration math) for legs that truncate. Nothing in sprint 006's
fix list touches this — it is squarely this sprint's own thing to
check (see `design/src-root-DESIGN.md` §15 for the full framing).

`MotionEngine`'s `move_.deadline` is set to `nowMs() + timeoutMs` at
both call sites (`motion_engine.cpp:156` inside `moveX()`'s pivot phase
and `:221` inside its straight-phase/second-call path) and checked for
expiry in `serviceMove()` as `static_cast<int32_t>(now -
move_.deadline) >= 0` (`motion_engine.cpp:344`). `test.ts`'s tours pass
timeouts computed from the leg's expected duration; the question is
whether any realistic combination of tick cadence, rounding, or the
32-bit signed-difference expiry check can end a move's deadline before
its commanded distance is actually reached under normal (not
starved) conditions — as opposed to being a deliberate, correctly
functioning backstop.

`motion_engine.{h,cpp}` has no `pxt.h` dependency
(`src/DESIGN.md` §1's layering table) and is already compiled into the
host test harness via the `_SHIM_SOURCES` pattern used across
`tests/host/test_motion_engine_reductions.py`,
`tests/host/test_cxx11_syntax_gate.py`,
`tests/host/test_wire_motion_verbs.py`, and others (confirmed during
this sprint's planning). This investigation is therefore a host test
at the deadline-expiry boundary, not a bench measurement.

## Acceptance Criteria

- [ ] A host test in `tests/host/` exercises `serviceMove()`'s deadline
      expiry at the boundary — a move whose true completion (by
      distance/yaw margin) would land close to `timeoutMs`, under
      realistic tick-cadence quantization (the kernel's ~24 ms step,
      per `docs/design/design.md`'s tick-model convention) — and
      asserts whether the move completes normally or is cut short by
      the deadline first.
- [ ] **If the boundary is clean** (the deadline never fires before a
      move that is genuinely progressing toward completion): no source
      change lands. The finding — what was tested, what margin exists
      between typical move duration and its timeout — is written into
      `intermittent-cw-pivot-abort-wheel-reversal.md` as a ruled-out
      theory, with the host test kept as a permanent regression guard.
- [ ] **If a genuine defect is found** (the deadline can fire before a
      move that would otherwise complete, under conditions plausible
      during a real tour): it is fixed in `motion_engine.cpp`, with the
      new host test pinning the fix, and the finding is written into
      the issue file as a confirmed cause (fully or partially — state
      honestly whether this alone explains the observed ~30% failure
      rate or only some of it).
- [ ] Either way, `design/src-root-DESIGN.md` §3's inline "Sprint 011"
      annotation and §15 are updated to reflect the actual outcome
      (not left describing "outcome not yet known" once it is known) —
      re-run `clasi.design.overlay`'s diff step by hand (see the
      `architecture-authoring` skill's in-place revision convention) if
      the overlay content changes.
- [ ] No robot required — entirely host-testable, per this sprint's
      hard constraint.
- [ ] `uv run pytest` (full suite) passes.

## Implementation Plan

**Approach:** Trace the deadline math by reading, then write a host
test that constructs a `MoveState` scenario at the boundary (e.g. via
the existing `motion_engine_shim.cpp` ctypes surface / whichever test
helper `test_motion_engine_reductions.py` already uses to drive
`serviceMove()` tick-by-tick) rather than guessing from inspection
alone — the whole point of this ticket is to have a test that can fail
if the boundary is wrong, not just a written opinion.

**Files to modify (conditional on findings):**
- `src/motion_engine.cpp` / `.h` — only if a real defect is found.
- `clasi/sprints/011-.../issues/intermittent-cw-pivot-abort-wheel-reversal.md`
  — the finding, either way.
- `clasi/sprints/011-.../design/src-root-DESIGN.md` (+ regenerate its
  `.diff.md`) — update §3's annotation and §15 to reflect the actual
  outcome.

**Testing plan:**
- New: a host test at the deadline-expiry boundary in
  `tests/host/` (exact filename implementer's choice — a new file or
  an addition to an existing `motion_engine`-focused test file).
- Existing: the full `uv run pytest`, since this ticket may touch a
  shared kernel file.
- **Verification command:** `uv run pytest`.

**Documentation updates:** see Acceptance Criteria above — the issue
file and the `src-root-DESIGN.md` overlay both get the actual finding,
not a placeholder.

## C++11 Gate Coverage

- **If no source change lands:** not applicable — investigation only.
- **If a fix lands in `motion_engine.cpp`:** already inside the C++11
  syntax gate's coverage (`tests/host/test_cxx11_syntax_gate.py`'s
  `_SHIM_SOURCES` list includes `motion_engine.cpp` — confirmed during
  this sprint's planning) — no gate-coverage change needed, the fix is
  automatically checked by the existing gate.
