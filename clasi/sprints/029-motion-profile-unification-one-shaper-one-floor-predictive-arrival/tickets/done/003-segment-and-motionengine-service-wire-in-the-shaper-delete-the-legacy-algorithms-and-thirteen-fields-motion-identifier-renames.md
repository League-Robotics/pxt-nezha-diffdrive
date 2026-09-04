---
id: '003'
title: 'Segment and MotionEngine::service(): wire in the shaper, delete the legacy
  algorithms and thirteen fields, motion/ identifier renames'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
- '002'
github-issue: ''
issue: code-review/one-velocity-shaper-profile-object-out-of-servicemove.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Segment and MotionEngine::service(): wire in the shaper, delete the legacy algorithms and thirteen fields, motion/ identifier renames

## Description

The core rewrite (design §11 ticket 3; needs both 001 and 002). Add
`Segment` (`src/motion/segment.h`, new, replaces `MoveState` — design
§4.3's exact struct: targets in counts, lazy origin capture, pending
second phase, deadline, and the pure functions `remaining()`/
`wrongWay()`/`progress()`/`pureTurn()` over kernel `Output`). Rewrite
`MotionEngine::service()` to design §5's ~40-line tick (segment-or-hold
dispatch, no mode forks), replacing `serviceMove()`'s 360 lines and two
braided algorithms.

**Delete**: `distTaper_`, `yawTaper_`, `distFloor_`, `turnFloor_`,
`rampMs_`, `brakeFrac_`, `plateauMinS_`, `profileExitMmS_`,
`pivotOverrunMm_`, `awaitingHandoffNeutral`, the two rebase-epoch
copies, and both legacy shaping algorithms. `MotionEngine` gains
`limits()` returning one settable `MotionLimits&`, one `Segment seg_`,
one `Hold hold_` struct (design §4.4), one `VelocityShaper shaper_`.

**Entry-point changes** (design §4.4's table):
- `wheelsV(l, r, ms)` sets `hold_` (target v, twist, deadline);
  `service()`'s continuous path slews toward it through the shaper
  every tick, issuing a rolling 500 ms lease.
- `wheelsX(l, r, cruise, ms)` becomes a `Segment` like `moveX` —
  closed-loop on encoders instead of one dead-reckoned `drive()` (design
  §12's recorded decision: "the spec allows this... the dead-reckoned
  lease was the only reason the two primitives differed").
- `moveX`/`goToR`/`goToW` build a `Segment` (pivot-then-straight split
  rule unchanged: `|rotation| >= 50°` with distance); `service()` runs
  it.
- `endMove()`: neutral + `shaper_.reset()` + clear both `seg_`/`hold_`.

**K5** lands here: `cfg.vMin = 0` in `shims.cpp:ensure()`, now that
`MotionEngine`/`MotionLimits` owns the floor.

**Identifier renames**: every unit-suffixed identifier remaining in
`src/motion/` (per `.claude/rules/no-units-in-identifiers.md`,
`strip-units-from-identifier-names.md`'s scope note: "`src/motion/`
renames ride with the motion-profile sprint's engine rewrite") — this
lands in the same pass because the files are already open for the
rewrite. Every rename keeps its `// [unit]` comment.

**`src/DESIGN.md` real-file update** (not the sprint's `design/`
overlay — see ticket 001's Description for why): rewrite §3's "Public
interface" and "Key state" paragraphs to describe `Segment`/
`VelocityShaper`/`MotionLimits`/`service()` replacing `MoveState`/
`serviceMove()`/the per-tour shaping setters, and note the
`wheelsX`-becomes-closed-loop and lazy-origin-capture (retiring the
epoch guard) decisions per design §4.8/§6.5.

## Acceptance Criteria

- [x] `tests/host/test_profile_probe.py` (design §9.2, the review's
      probe promoted to a test): 90° pivots at cruise 60/100/200 end
      within 0.5° on ideal wheels, no negative duty on either wheel;
      arc endpoint within 2 mm; straight peak speed ≤ cruise + 5%;
      `set wheel speeds` never steps more than `accel·dt` above the
      floor.
- [x] Design §7's "after" column is measured by the probe and recorded
      in this ticket (not just asserted) — cite the actual probe
      output per `.claude/rules/measurement-citations.md`.

      MEASURED against this ticket's own compiled engine, host
      simulation with ideal wheels (no hardware run performed —
      `tests/host/test_profile_probe.py`, ticket 003's own commit):

      | scenario | design §7 predicted | measured here |
      |---|---|---|
      | 90° pivot, cruise 100 | 90.0 ± 0.5°, no reverse duty | PASS (`test_pivot_90_lands_within_half_degree[100.0]`, `test_pivot_forward_wheel_never_goes_negative`) |
      | 90° pivot, cruise 200 | 90.0 ± 0.5° | PASS (`test_pivot_90_lands_within_half_degree[200.0]`) |
      | 45°/300 mm arc, cruise 100 | (270, 112) ± 2 mm | measured endpoint (270.1, 111.9) mm — `test_arc_endpoint_matches_the_constant_radius_geometry` |
      | 600 mm straight, cruise 200 | start step to 70 then 400 mm/s²; peak ≈ 200 + I-term catch-up | measured peak 200.0 mm/s, 137 ticks, 3.29 s, travelled 598.99 mm — `uv run pytest tests/host/test_profile_probe.py::test_design_s7_after_measurement_600mm_cruise_200 -q -s` |
      | move duration, 600 mm @ cruise 200 | "≈3.3 s after" | measured 3.29 s (same run as above) |
      | `set wheel speeds 200 200` from rest | predicted table says "70, 80, 89, 99, … (400 mm/s² from the floor)" | **measured 0, 9.6, 19.2, 28.8, 38.4, 48.0, 57.6, 67.2 mm/s** — see note below |
      | frozen encoder tick at 300 mm/s | 0 (K2) | PASS, `tests/host/test_profile_probe_kernel.py::test_probe_kernel_check_e3d_and_e5` (E5) |

      **Discrepancy found and recorded, not silently fixed**: design
      §7's own predicted row for `set wheel speeds 200 200` implies a
      Hold starts from the floor (70 mm/s) like a Segment does. Design
      §5's own tick pseudocode for the continuous-hold branch is
      explicit that it does not: `step = shaper_.advance(target =
      hold_.dominant, remain = -1, floor = 0, cap = limits.vMax, dt,
      limits)` — `floor = 0` for a hold, because `VelocityShaper::
      advance()`'s floor clamp (`velocity_shaper.cpp`) is gated on
      `remain >= 0.0f`, which is never true for a hold's `-1`
      "unbounded" sentinel. This ticket implements §5 exactly (as
      instructed), so the measured ramp (0, 9.6, 19.2, … — plain
      `accel·dt` from zero) is correct against the design's own
      pseudocode; §7's predicted-table row is the document that is
      stale, not the code. Left for a design-doc reconciliation pass,
      out of this ticket's own scope (rewriting `motion-profile-
      unification.md` §7 was not in the ticket brief).
- [x] `tests/host/test_segment_lazy_origin.py` (design §9.4): a
      `rebasePosition()` requested between `start()` and the first
      `service()` does not change the segment's measured progress.
- [x] **Rewritten** (per design §9, pinning the algorithm this ticket
      removes): `test_motion_engine_acceleration_profile.py`,
      `test_regression_yaw_taper_pure_turn.py` (restated as "the shaper
      runs on the dominant axis"), `test_motion_engine_shaping_fields.py`,
      `test_motion_engine_settle.py`.
- [x] **Kept unchanged**: the deadline, e-stop/refusal, goToW geometry,
      primitives-and-reductions tests (they test targets/outcomes, not
      shaping).
- [x] No `MmS`/`Ms`/`Mm`/`Rad`/`Counts` suffix remains in `src/motion/`
      (verified with a grep sweep of `src/motion/*.h`/`*.cpp`, excluding
      the pre-existing conversion-boundary names the naming rule itself
      exempts: `countsPerMm()`, `kDegToRad`).
- [x] `src/DESIGN.md` §3 is updated in the real file per the Description
      above.
- [x] `MotionEngine`'s public surface (primitives, reductions, `goToW`,
      geometry, `isMoveActive`, `progress`, `endMove`, `settleToRest`)
      is unchanged — verified by `wire_adapter.cpp`/`shims.cpp` needing
      no call-site changes beyond `limits()` replacing the old shaping
      setters (plus the one `turnFirstAngle()` call-site rename in
      `shims.cpp`, following the public accessor's own unit-suffix
      rename).

## Implementation Plan

**Approach**: This is the largest ticket in the sprint. Sequence: (1)
add `Segment` and its pure functions with tests against the existing
`MoveState`-shaped fixtures adapted to the new struct; (2) rewrite
`service()` to design §5's pseudocode, initially alongside the old
`serviceMove()` behind a flag if useful for a bisectable diff, then
delete the old path and the flag in the same ticket (design §12: "legacy
shaping is deleted, not kept behind a mode" — the flag, if used, is a
local implementation convenience during the rewrite, not a shipped
option); (3) wire `wheelsV`/`wheelsX` onto the new dispatch; (4) delete
the thirteen fields and `awaitingHandoffNeutral`/epoch copies; (5) K5;
(6) identifier renames, file by file, keeping `// [unit]` comments; (7)
run the probe, record §7's numbers, update `src/DESIGN.md` §3.

**Files to create/modify**:
- `src/motion/segment.h` (new)
- `src/motion/motion_engine.h`/`.cpp` (rewritten `service()`, deleted
  fields/algorithms, renamed identifiers)
- `src/shims.cpp` — `ensure()`'s `cfg.vMin = 0` (K5); any call sites
  using the old shaping setters now call `limits()`.
- `tests/host/test_profile_probe.py` (new, promoted from
  `docs/code-review/2026-09-02/raw/profile_probe.cpp`)
- `tests/host/test_segment_lazy_origin.py` (new)
- `tests/host/test_motion_engine_acceleration_profile.py`,
  `test_regression_yaw_taper_pure_turn.py`,
  `test_motion_engine_shaping_fields.py`,
  `test_motion_engine_settle.py` (rewritten)
- `src/DESIGN.md` §3 (real-file edit, see Description)

**Testing plan**: Full `tests/host/` motion/engine subset, scoped per
`.claude/rules/source-code.md` (not the full suite — that runs once at
`close_sprint`). Confirm the probe's "after" numbers against design
§7's predicted column before calling this ticket done.

**Documentation updates**: `src/DESIGN.md` §3 (real file); `src/motion/
DESIGN.md`'s sprint-029 overlay note (already seeded/committed) stays
accurate — no further edit needed there unless this ticket's actual
implementation diverges from what the overlay already describes.
