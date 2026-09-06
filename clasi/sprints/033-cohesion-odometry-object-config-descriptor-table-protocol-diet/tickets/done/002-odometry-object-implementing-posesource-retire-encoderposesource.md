---
id: '002'
title: Odometry object implementing PoseSource; retire EncoderPoseSource
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: odometry-object-and-kernel-rearm-references.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Odometry object implementing PoseSource; retire EncoderPoseSource

## Description

**Verified against current source, 2026-09-05 — this ticket is
narrower than the issue text alone suggests.** The issue's stated
blocker ("depends on kernel-reference-handling K4 and the design's lazy
origin capture") is already satisfied: `DifferentialDrive::
rearmReferences()` shipped in sprint 029 ticket 001
(`src/core/diffdrive.h:213`, `.cpp:393`) and is already called from
`MotionEngine::service()` (`src/motion/motion_engine.cpp:442`); lazy
origin capture shipped the same sprint (`Segment::originPending`,
`src/motion/segment.h`). The "three copies" of the rebase-epoch guard
the issue names are already down to one: `MotionEngine::progress()`
(`motion_engine.cpp:536`) and the pivot-then-straight handoff
(`motion_engine.cpp:372-375`) now branch on `seg_.originPending` (a
plain bool), not an epoch comparison. **Do not re-add or "collapse"
anything in `src/motion/` — that work already landed.** The only
surviving epoch comparison anywhere in the codebase is `odomUpdate()`'s
own `r.odomPositionEpochLeft/Right` vs. `out.positionEpochLeft/Right`
check (`src/shims.cpp:335-352`), and closing that is this ticket's own
job, folded into the new class.

`EncoderPoseSource` (`src/platform/encoder_pose_source.h`) still holds
`const float&` references into `Rig`, with its full ~45-line lifetime
essay intact — this part of the issue is fully live. `Rig::x/y/heading`,
`odomPos*`, `odomPrimed`, `odomPositionEpoch*` (`shims.cpp:121-127`) and
the free function `odomUpdate()` (`shims.cpp:324`) are unmoved.

**Build `Odometry`** (`src/motion/` or `src/platform/` — host-portable,
no `pxt.h`, mirroring `encoder_glitch_armor.h`/`bus_guard.h`'s existing
placement pattern) with `update(const DiffDrive::DifferentialDrive::
Output&)`, `reset()`, `seed(x, y, h)`, implementing `PoseSource`
directly (`x()`/`y()`/`heading()`, unwrapped heading, matching
`EncoderPoseSource`'s existing wrap-convention contract in
`motion_engine.h`). Move `odomUpdate()`'s math into `Odometry::update()`
unchanged; fold the one remaining epoch guard into it. Retire
`EncoderPoseSource` and its lifetime essay entirely. `shims.cpp`'s
`Rig` gains an `Odometry` member (declared with the same lifetime
discipline `EncoderPoseSource` currently documents) instead of the five
scattered fields; `poseX()`/`poseY()`/`poseHeading()`,
`resetPose()`/`seedPose()`, and `SET rebase`'s odometry-side write all
route through it.

**Resolve Architecture §Open Question 1** (does a pose read advance
odometry?): keep the existing "reads mutate" contract — `src/
DESIGN.md` §5 documents it as load-bearing ("nothing else advances
odometry between moves and the 50 ms telemetry tick is what keeps pose
current"). Fold `tickDrive()`'s unconditional call and `updateMove()`'s
`wasActive`-gated call into `Odometry::update()` unchanged from their
current gating; document the "reads mutate" contract explicitly on the
new class rather than leaving it implicit across three call sites.

**Sprint 031 coordination**: this ticket does not need to touch
`motion_engine.cpp`'s `service()`/`wrongWay()` or `segment.h` — the
`PoseSource` interface itself is unchanged (`Odometry` is a new
implementer, not an interface edit) — so collision risk with sprint
031's unmerged branch (which touches exactly those two areas) is LOW.
It also does not touch `wire_adapter.cpp` (that file only forward-
declares `poseX`/`poseY`/`poseHeading`, whose signatures are unchanged).

## Acceptance Criteria

- [x] `grep -n positionEpoch src/motion src/shims.cpp` finds exactly
      one reader (sprint Success Criteria's own bar).
- [x] A host test integrates a known wheel-count path through
      `Odometry::update()` and matches `odomUpdate()`'s pre-refactor
      output within float tolerance.
- [x] `grep -rn EncoderPoseSource src/` finds nothing outside
      `src/DESIGN.md`'s historical narrative (which stays, as a record
      — do not scrub sprint history).
- [x] `platform/encoder_pose_source.h` and its syntax-check
      (`tests/host/encoder_pose_source_syntax_check.cpp`) are deleted.
- [x] `Odometry`'s doc comment states the "reads mutate odometry as a
      side effect" contract explicitly.
- [x] `MotionEngine::goToW()`'s `PoseSource` selection
      (`OtosPort` vs. encoder fallback) is unaffected — same selection
      rule, now selecting `Odometry` instead of `EncoderPoseSource`.
- [x] No change to `motion_engine.cpp`'s `service()`/`wrongWay()`,
      `segment.h`, or `wire_adapter.cpp` — confirm before committing
      that no edit touched those sprint-031-owned regions.

## Testing

- **Existing tests to run**: `tests/host/test_continuous_mode_odometry.py`
  (must still pass — this is the "pose updates every tick" contract
  this ticket must not break); anything exercising `goToW`'s
  `PoseSource` fallback selection.
- **New tests to write**: `tests/host/test_odometry.py` — a known
  wheel-count path through `Odometry::update()`, compared against the
  pre-refactor `odomUpdate()` math; a rebaseline/epoch-guard test
  (feed a changed `positionEpochLeft/Right` and confirm the odometry
  frame holds rather than jumping).
- **Verification command**: `uv run pytest tests/host/`
