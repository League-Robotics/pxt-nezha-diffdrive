---
id: '007'
title: Encoder PoseSource fallback for GO_TO_W
status: in-progress
use-cases:
- SUC-006
depends-on:
- '004'
- '005'
github-issue: ''
issue: no-encoder-odometry-posesource-fallback.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Encoder PoseSource fallback for GO_TO_W

## Description

`motion-api.md` §3.6 specifies `go_to_w`'s pose source as pluggable —
OTOS when fitted, encoder odometry otherwise. Sprint 003 built the
pluggable half properly (`diffDrive::PoseSource` is a 3-method port,
`OtosPort` implements it, `FakePoseSource` makes `goToW()`
host-testable), but only the OTOS side was wired: `engineGoToW()`
(`src/shims.cpp`) answers `Wire::Result::kUnimplemented` whenever no
OTOS is connected — which is most of the fleet (the OTOS is on vevov;
tovez, gopiv, zeguz have none). `GO_TO_W`, one of the six headline
motion verbs, is currently a no-op on most robots the extension will
run on.

The odometry itself already exists — `odomUpdate()` in `shims.cpp`
maintains a dead-reckoned pose from encoder counts, and the block
API's `poseX`/`poseY`/`heading` already expose it. What is missing is
an adapter presenting it as a `PoseSource`, plus the selection rule.

**Depends on ticket 004** (heading-wrap/`PoseSource` contract
cleanup) and **ticket 005** (encoder glitch-armor rebaseline): this
ticket shares the `PoseSource` interface seam ticket 004 clarifies,
and inherits ticket 005's rebaseline guarantee rather than
re-implementing epoch-tracking of its own (see below) — do not start
this ticket before both are done.

**Fix, at the module level** (see `design/DESIGN.md` §7/§9 for the
full write-up): a new, host-portable `EncoderPoseSource` implementing
`diffDrive::PoseSource` over the Rig's existing `x`/`y`/`heading`
floats (same three-method shape as `OtosPort`, heading reported
**unwrapped** — matching `Rig`'s existing odometry contract and
motion-api.md §3.6's explicit requirement for the encoder-based
source, per ticket 004's contract cleanup). `engineGoToW()` selects
`OtosPort` when connected, `EncoderPoseSource` otherwise, in this one
place — it no longer refuses outright. `EncoderPoseSource` needs **no
new epoch-tracking code of its own** for motion-api.md §3.6's
"epoch-guarded rebaseline" requirement: it reads the same Rig-local
state `odomUpdate()` already produces, and ticket 005's
`EncoderGlitchArmor` already makes that state continuous across a
detected brick-reset discontinuity — the guarantee is inherited, not
re-implemented. `EncoderPoseSource` must be constructed with a
lifetime tied to `Rig`'s own lazy-singleton, process-lifetime instance
(e.g. as a `Rig` member) — it holds const references to `Rig`'s
fields, and a shorter-lived instance would dangle.

Worth stating plainly in whatever ships: encoder odometry drifts and
OTOS does not, so a `GO_TO_W` served by encoders is a materially
weaker promise than one served by the OTOS. This difference is not
currently surfaced back through `GO_TO_W`'s own return value — a
caller must check STATUS's `otos=` flag beforehand to know which
promise it is getting. Document this plainly (doc comment and/or
`src/DESIGN.md`, already noted in this sprint's overlay's Open
Questions) rather than leaving the two cases looking identical;
building an actual signal for this is out of scope for this ticket
(flag it as a follow-on if it seems small enough to also fit here, but
do not silently expand scope).

**C++11 gate coverage:** `encoder_pose_source.h` has no `pxt.h`
dependency and should be added to
`tests/host/test_cxx11_syntax_gate.py`'s coverage via a small
dedicated syntax-check translation unit. The selection-rule wiring in
`shims.cpp::engineGoToW()` is **not** covered by that gate (it
includes `pxt.h`). The `wire_adapter.cpp` comment update (below) is in
a gate-covered file but is comment-only — no behavioral coverage
either way.

## Acceptance Criteria

- [x] A host test calls `MotionEngine::goToW()` through
      `EncoderPoseSource` with no OTOS anywhere in the link (mirroring
      `tests/host/test_motion_engine_gotow.py`'s existing
      `FakePoseSource` pattern) and asserts the move dispatches and
      reaches its target under scripted odometry.
- [x] `EncoderPoseSource::heading()` returns the unwrapped value
      verbatim (no wrap applied) — a host test confirms this
      explicitly, since it is easy to accidentally "fix" this to match
      `OtosPort`'s wrapped convention, which would violate
      motion-api.md §3.6's requirement for this specific
      implementation.
- [x] A host test asserts `engineGoToW()`'s selection rule picks
      `EncoderPoseSource` when `OtosPort::connected()` is false, and
      `OtosPort` when true. (This likely needs a seam to control
      `OtosPort::connected()` from a host test, or to test the
      selection logic in isolation from `OtosPort`'s own
      non-host-testability — design this seam as part of the ticket,
      not as an afterthought.)
- [x] `wire_adapter.cpp`'s comment describing GO_TO_W's
      `kUnimplemented`-without-OTOS behavior is corrected (it currently
      reads "GO_TO_W with no connected OTOS answers `kUnimplemented`
      (recognized, not wired on this build)"). NOTE: that exact quoted
      string turned out to live in `src/DESIGN.md:229-231` (the
      persistent design doc), not literally in `wire_adapter.cpp` --
      see this ticket's implementation report for where it actually is
      and why it is deliberately left untouched here. The real,
      differently-worded comments in `wire_adapter.h`/`wire_adapter.cpp`
      describing this same stale behavior are corrected.
- [x] `encoder_pose_source.h` is added to
      `tests/host/test_cxx11_syntax_gate.py`'s covered-files list.
- [x] `EncoderPoseSource`'s construction/lifetime relative to `Rig` is
      documented in a code comment (not just this ticket) — the next
      reader must not be able to construct a shorter-lived instance by
      accident without a comment warning them off it.

## Implementation Plan

**Approach:**
1. Create `src/encoder_pose_source.h`: `EncoderPoseSource : public
   diffDrive::PoseSource`, holding `const float&` (or equivalent)
   references to the fields `odomUpdate()` maintains, returning them
   verbatim from `x()`/`y()`/`heading()`.
2. Wire it into `Rig` (`shims.cpp`) with a lifetime tied to `Rig`
   itself.
3. In `engineGoToW()`, replace the early `if (!otos.connected())
   return false;` with a selection: pass `otos` if connected, the
   `EncoderPoseSource` otherwise, to `r.engine.goToW(...)`; always
   return `true` (or otherwise signal dispatch, matching whatever the
   function's existing return-value contract needs to stay compatible
   with `wire_adapter.cpp`'s caller).
4. Update the `wire_adapter.cpp` comment.
5. Add `encoder_pose_source.h` to the C++11 syntax gate.

**Files to modify:**
- `src/encoder_pose_source.h` (new).
- `src/shims.cpp` — `Rig` composition; `engineGoToW()` selection logic.
- `src/wire_adapter.cpp` — comment update only (verify no behavioral
  change is actually needed there; if `engineGoToW()`'s return-value
  contract is unchanged — bool "dispatched or not" — `wire_adapter.cpp`
  needs no code change, only the stale comment).
- `tests/host/test_cxx11_syntax_gate.py` — add `encoder_pose_source.h`.
- `tests/host/` — new `goToW()`-through-encoder test; selection-rule
  test.

**Testing plan:** host-only, against `encoder_pose_source.h` and
`MotionEngine::goToW()` directly, following
`test_motion_engine_gotow.py`'s existing pattern.

**Documentation updates:** `wire_adapter.cpp` comment (above);
`src/DESIGN.md` §10's "known limitation" bullet on the missing
fallback is already resolved in this sprint's `design/DESIGN.md`
overlay — this ticket implements that write-up, it does not change it
further unless implementation reveals a discrepancy (report it if so,
do not silently diverge from the approved overlay).
