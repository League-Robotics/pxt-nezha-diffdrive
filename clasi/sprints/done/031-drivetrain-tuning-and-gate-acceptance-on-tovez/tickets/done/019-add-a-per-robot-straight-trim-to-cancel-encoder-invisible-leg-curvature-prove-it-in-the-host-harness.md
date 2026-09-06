---
id: 019
title: Add a per-robot straight_trim to cancel encoder-invisible leg curvature; prove
  it in the host harness
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Add a per-robot straight_trim to cancel encoder-invisible leg curvature; prove it in the host harness

Type (b): programmer-implementable; hardware acceptance is done
separately by the team-lead, not part of this ticket.

## Description

`docs/sprint-031-postmortem.md` §2.2 establishes, from
`captures/session-b-20260905/ticket016/g3-600/g3-legs.csv` (six
alternating +-600 mm legs at 100 mm/s), that tovez's forward legs curve
uniformly by ~3.4 deg over 600 mm — 1.1% differential ground travel on
a 114.2 mm track — and that twist hold
(`src/core/diffdrive.cpp` ~lines 615-641) cannot correct it when the
curvature is invisible to the encoders, because it holds ENCODER twist

```
measuredTwist = 0.5 * ((posR - posR0) - (posL - posL0))   // [encoder counts]
```

to a reference integrated from the COMMANDED twist. If the encoders
report both wheels traveling the same distance while the ground
distances differ (a ~1% effective wheel-radius mismatch, or asymmetric
scrub), twist hold's error is zero at any gain — this is why sprint
031 tickets 012 and 015 retuning `twistHoldGain` moved the number from
2.88 to 2.10 to 3.19 deg without resolving the mechanism.

Add a config field `straight_trim` // [1] (dimensionless fraction,
default 0), wire-settable via the existing `kFields` table in
`src/comms/wire_adapter.cpp` using the same x1000 int wire convention
as the other config fields, and gettable the same way. When nonzero,
bias the twist REFERENCE integration by
`straight_trim * commanded_forward_velocity * dt` (in the same count
units the reference already integrates in), so the encoders are
deliberately driven to twist by the fraction that cancels a ground-side
mismatch.

Sign convention: **positive `straight_trim` makes the RIGHT wheel
travel further than the left in encoder space.** Document this
explicitly in the field's trailing comment at its declaration and in
`DESIGN.md` (whichever `DESIGN.md` documents `src/core/diffdrive.cpp`'s
twist-hold behavior).

Follow `.claude/rules/no-units-in-identifiers.md`: name the field for
what it is (`straight_trim`), unit in a trailing `// [1]` comment, not
in the identifier.

Keep the change minimal and inside the existing twist-hold block in
`diffdrive.cpp` — do not restructure the kernel or touch unrelated
control paths.

**Host harness proof** (the important half of this ticket, and what
makes the change mergeable without hardware): add
`tests/host/test_straight_trim.py`, extending `kernel_shim.cpp` /
the existing Kernel wrapper in `test_kernel_harness.py` only as needed.
The harness already exposes `arm_motor_sample(side, position,
sample_time_us)`, `motor_last_staged_duty(side)`, `set_clock`, `drive`,
and `step` — use those, per §1a of the postmortem which lays out
exactly this plant-in-the-loop pattern (`FakeMotor` has no physics; the
plant is a Python-side per-wheel first-order motor integration).

Write a small plant-in-the-loop in Python:
- Each step, take the two staged duties, integrate a first-order
  per-wheel motor (same gain/time-constant both sides) into ENCODER
  counts, and `arm_motor_sample` them.
- Separately integrate GROUND travel per wheel, where the ground radius
  may differ per wheel by an injectable fraction (the mismatch under
  test).
- Compute ground heading as `(groundR - groundL) / trackWidth`.

Use the C++11 syntax gate that already exists in `tests/host` (see
`tests/host/DESIGN.md`) for any shim changes.

Do **not** bake a tovez value in this ticket — default 0 everywhere.
The team-lead measures tovez's actual trim on hardware (postmortem
§3, P2: one `--mode g3 --legs 6 --leg-mm 600` run) and bakes it
separately, after this ticket lands with default-0, no-behavior-change
semantics.

## Acceptance Criteria

- [x] `straight_trim` exists as a config field in the kernel, default
      0, settable via `SET straight_trim` and gettable via
      `GET straight_trim` over the wire (`kFields` table in
      `wire_adapter.cpp`), using the existing x1000 int convention.
- [x] Host test 1: with a 1.1% injected per-wheel ground-radius
      mismatch and `straight_trim` 0, over a 600 mm straight `drive()`
      the ENCODER twist stays ~0 (within a tight tolerance) while
      integrated ground heading drifts by ~3.4 deg — assert BOTH
      halves (this is the mechanism proof: twist hold is blind to the
      mismatch).
- [x] Host test 2: with the same 1.1% mismatch and the matching
      `straight_trim`, ground heading at the end of the same leg is
      < 0.3 deg.
- [x] Host test 3: with no mismatch and `straight_trim` 0, ground
      heading stays < 0.05 deg over the leg (no regression on a
      matched robot).
- [x] Host test 4: `GET straight_trim` reads back exactly what
      `SET straight_trim` wrote (wire round-trip, via the existing
      wire test shim if one already covers config fields; otherwise a
      shims-level test of the same round trip).
- [x] With `straight_trim` 0, the kernel's behavior is bit-for-bit
      unchanged: the existing host suite passes with no modified
      expected values.
- [x] `DESIGN.md` documents the field, its sign convention, and why it
      exists, citing `docs/sprint-031-postmortem.md` §2.2 in one
      paragraph.
- [x] Scoped tests pass (the host suite covering `diffdrive.cpp`,
      `wire_adapter.cpp`, and the new test file — not the full suite,
      which runs once at `close_sprint`).

## Testing

- **Existing tests to run**: the full existing `tests/host/` suite
  (diffdrive/twist-hold and wire_adapter config-field tests in
  particular) to confirm zero-trim bit-for-bit equivalence; any
  existing wire round-trip test covering `kFields` config gets/sets.
- **New tests to write**: `tests/host/test_straight_trim.py` with the
  four cases above (mechanism proof, correction, no-regression, wire
  round-trip); any `kernel_shim.cpp` / harness extension needed to
  support the per-wheel ground-radius injection described above.
- **Verification command**: `uv run pytest tests/host/ -k
  "straight_trim or diffdrive or wire_adapter"` (adjust to the actual
  scoped path/markers once the test file exists), through the C++11
  syntax gate in `tests/host/DESIGN.md`.
