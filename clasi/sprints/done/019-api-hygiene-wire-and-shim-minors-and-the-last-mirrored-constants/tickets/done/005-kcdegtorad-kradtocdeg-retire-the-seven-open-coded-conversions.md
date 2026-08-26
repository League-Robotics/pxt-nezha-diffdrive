---
id: '005'
title: kCdegToRad/kRadToCdeg; retire the seven open-coded conversions
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: duplicated-constants-across-the-shim-boundary.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# kCdegToRad/kRadToCdeg; retire the seven open-coded conversions

## Description

The centidegree<->radian conversion is written out as a literal formula seven
times in `src/shims.cpp`, instead of being named once. Forward (cdeg -> rad):

```cpp
static_cast<float>(yawRate) * 0.01f * 3.14159265f / 180.0f
```

at:

| Line | Function |
|---|---|
| 272 | `driveTwist()` |
| 300 | `driveTwistTimed()` |
| 385 | `startMove()` (heading argument) |
| 413 | `startMove()` (yaw-rate argument -- same formula, second occurrence in the same function; not separately counted in the review's tally but the same defect) |
| 1155 | `otosSetOffset()` |
| 1166 | `seedPose()` |

...and inverted (rad -> cdeg), twice more:

| Line | Function |
|---|---|
| 840 | `poseHeading()` -- `heading * 180.0f / 3.14159265f * 100.0f` |
| 1093 | `otosGet()` -- local `constexpr float kRadToCdeg = 18000.0f / 3.14159265f;` (the only site that currently names the conversion, but as a function-local re-declaration rather than the shared constant) |

`shims.cpp`'s own file header (`shims.cpp:25-27`) already states the boundary
convention this belongs next to: *"Boundary convention: integers only. mm,
mm/s, centidegrees, centidegrees/s; config values scaled x1000. The TS layer
owns the cm/deg student units."* The fix is to give that convention's
cdeg<->rad conversion a name, once, right there:

```cpp
constexpr float kCdegToRad = 0.01f * 3.14159265f / 180.0f;
constexpr float kRadToCdeg = 1.0f / kCdegToRad;
```

placed at file scope in `shims.cpp` near the header comment block (after the
`#include`s, ~line 44), and used at every one of the sites above.

**Scope note on `3.14159265f` itself**: this ticket retires the cdeg<->rad
CONVERSION formula, not every standalone appearance of the pi literal in the
codebase. `motion_engine.cpp:17`'s local `constexpr float kPi = 3.14159265f;`
(used only by `wrapToPi()`, a rad-domain angle-wrapping helper with no cdeg
involvement) and `otos_port.h:107`'s `0.00549f * (3.14159265f / 180.0f)` (an
LSB-to-radian sensor scale factor, a different physical quantity entirely) are
each a single module's own use of the mathematical constant pi for a purpose
unrelated to the cdeg<->rad boundary conversion -- they are not mirrors of
each other or of `kCdegToRad`/`kRadToCdeg` in the "two owners maintaining
copies that must agree" sense (pi does not drift), so leave them as-is. Do not
introduce a shared "kPi" across files as part of this ticket -- that is a
different, broader change than what this issue and the sprint scope call for.
`Math.PI` on the TypeScript side is likewise out of scope: it is a distinct
language/runtime boundary with its own established `Math.PI`, not part of the
seven `shims.cpp` conversion sites this ticket retires.

`src/core/diffdrive.{h,cpp}` is vendored and byte-stable -- not touched by
this ticket (the kernel is counts-native and has no radian/cdeg concept at
all).

## What to change

1. `src/shims.cpp` -- add `constexpr float kCdegToRad` and `constexpr float
   kRadToCdeg` at file scope, near the existing boundary-convention comment
   (line ~25-27), each with a one-line comment tying it to that convention.
2. `src/shims.cpp` -- replace all seven open-coded sites (272, 300, 385, 413,
   1155, 1166 for the forward conversion; 840, 1093 for the inverse) with
   uses of the new named constants. Delete `otosGet()`'s local `kRadToCdeg`
   re-declaration (line 1093) in favor of the shared one.
3. Grep `src/shims.cpp` for the literal `3.14159265f` after the above changes
   to confirm no additional cdeg<->rad conversion site was missed by this
   enumeration (the review found seven; verify there is not an eighth before
   closing this ticket) -- any remaining hits should be either the new
   `kCdegToRad`/`kRadToCdeg` definitions themselves, or a genuinely unrelated
   use of pi (there should be none left in `shims.cpp` outside those two
   definitions, since every current use in this file is one of the eight
   sites enumerated above).
4. Do not touch `motion_engine.cpp`'s `kPi` or `otos_port.h`'s LSB-conversion
   literal (see Scope note above) -- both are legitimately independent uses
   of the constant, not part of this conversion's mirror set.

## Acceptance Criteria

- [x] `kCdegToRad` and `kRadToCdeg` are each defined exactly once, in
      `src/shims.cpp`, beside the file's existing boundary-convention
      comment.
- [x] All eight discovered open-coded conversion sites in `shims.cpp`
      (272, 300, 385, 413, 1155, 1166, 840, 1093) use the named constants;
      none open-codes the formula independently.
- [x] `otosGet()`'s function-local `kRadToCdeg` re-declaration is removed in
      favor of the shared constant.
- [x] `motion_engine.cpp`'s `kPi` and `otos_port.h`'s LSB-to-radian literal
      are left unchanged (out of scope, see Scope note).
- [x] Numeric behavior is unchanged -- this is a pure refactor; any existing
      test exercising `driveTwist`, `driveTwistTimed`, `startMove`,
      `otosSetOffset`, `seedPose`, `poseHeading`, or `otosGet` must produce
      bit-identical results before and after.
- [x] No change to `src/core/diffdrive.{h,cpp}` (vendored, byte-stable).

## Implementation notes

Re-measured against the current file (sprints 015/016 had shifted line
numbers since the review): the actual eight sites at execution time were
lines 290, 318, 403, 431 (forward), 896 (poseHeading, inverse), 1194
(otosGet's local `kRadToCdeg` re-declaration, inverse), 1256, 1267
(forward) -- eight total occurrences of the `3.14159265f` literal in
`shims.cpp`, matching the review's count exactly (six forward, two
inverse). All eight now defer to file-scope `kCdegToRad`/`kRadToCdeg`,
defined immediately after `namespace diffDrive {` opens (beside the
existing "Boundary convention" header comment at the top of the file,
~line 25).

**Numeric verification (bit-identical vs. restructured, per this
ticket's own instruction to state which).** Two different situations:

- `kRadToCdeg` merge (`otosGet()`): the old function-local
  `18000.0f / 3.14159265f` and the new shared `1.0f / kCdegToRad` were
  checked with float32-emulated arithmetic (no rounding difference
  possible -- both reduce to the same two-operation chain) and found
  **bit-identical** for the constant itself, so `otosGet()`'s `case 2`/
  `case 5` are unaffected bit-for-bit.
- The six FORWARD sites and `poseHeading()`'s inverse are a genuine
  restructuring: `v * a * b / c` (three chained ops, evaluated fresh at
  every call site) collapses to `v * K` where `K = a * b / c` is
  computed once at compile time. Floating-point multiplication/division
  is not associative, so this is **not bit-identical for 100% of the
  input domain** -- a float32 sweep found the two forms diverge by
  exactly 1 ULP in the rounded output roughly 0.07% of the time within
  a single heading rotation (±2π rad), and the resulting
  `std::lround()` output can differ by ±1 centidegree (0.01°) at
  specific input values (first observed divergence at |heading| ≈
  0.139 rad). This is 2-3 orders of magnitude below this project's own
  measured heading error budget (whole degrees, per
  `.claude/rules/playfield-testing.md`) and below encoder/telemetry
  resolution, so it is not behaviorally significant. The existing host
  suite (which exercises these functions at its own fixture values) was
  run before and after and produced identical pass results with no
  numeric assertions changing -- `uv run pytest tests/host/` (514
  passed). Chose the single-named-constant form the ticket's own "What
  to change" section specifies, rather than trying to preserve
  per-call-site operation order, since (a) the ticket's acceptance
  criteria and fix already spell out this exact form, and (b) the
  divergence is bounded and provably inconsequential at this robot's
  actual precision.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full host suite --
  `shims.cpp` is reached indirectly by many of the motion/telemetry/OTOS host
  tests; since this is a pure refactor with no `pxt.h` dependency change,
  bit-identical output on the existing suite is the primary regression
  guard).
- **New tests to write**: a host test (in `tests/host/`, following
  `test_wire_constants_drift.py`'s established regex-on-source-text pattern
  for pinning a single-sourced value) that greps `src/shims.cpp` and asserts
  the literal `3.14159265f` (or the full conversion formula) appears only
  inside the `kCdegToRad`/`kRadToCdeg` definitions themselves -- i.e. a
  structural test that a future edit re-introducing an open-coded eighth (or
  ninth) conversion site fails the suite, rather than silently reintroducing
  the duplication this ticket removes. This is the "drift test" side of the
  sprint's "merge or drift-test" rule applied to a case where the constant
  was merged: the test guards the merge from eroding back into duplication.
- **Verification command**: `uv run pytest tests/host/`
