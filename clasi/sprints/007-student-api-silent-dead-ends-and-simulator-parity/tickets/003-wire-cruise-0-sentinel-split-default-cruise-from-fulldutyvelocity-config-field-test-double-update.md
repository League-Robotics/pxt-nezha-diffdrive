---
id: '003'
title: 'Wire cruise==0 sentinel: split default_cruise from fullDutyVelocity (config
  field + test-double update)'
status: open
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: cruise-zero-sentinel-full-duty-lunge.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire cruise==0 sentinel: split default_cruise from fullDutyVelocity (config field + test-double update)

## Description

The wire grammar documents `0` as "use the configured default" for
cruise/speed on all four motion verbs (`WHEELS_X`/`MOVE_X`/`GO_TO_R`/
`GO_TO_W`). `engineDefaultCruiseMmS()` (`shims.cpp`) currently
resolves it to `fullDutyVelocity / countsPerMm` ≈ 875 mm/s — the
kernel's own 100%-duty rail — so a spec-following host sending
`MOVE_X 500 0 0 5000` gets a flat-out lunge, ~1.5× the 60 cm/s the
project's own bench notes record as "unusable" (code review
R-11/BLK-03/API-03, CONFIRMED, 874.6 mm/s independently re-derived).

**The crux is that this reuses a field with an unrelated, conflicting
meaning.** Verified in `diffdrive.cpp`'s `checkCommandable()`:
`if (needsVelocityCalibration && staged_.fullDutyVelocity <= 0.0f)
return Status::kRefusedUnconfigured;` — at the kernel layer, `0` on
`fullDutyVelocity` means "uncalibrated, refuse VELOCITY commands
entirely." The wire layer's convenience sentinel and the kernel's
calibration-refusal sentinel are two different meanings of zero,
collapsed onto the same field. Upstream's original (truncated in
vendoring) comment on `fullDutyVelocity` said exactly this — recovered
during the code review's comment audit.

## Implementation Plan

1. **Add a new field, do not reinterpret the old one.** In
   `shims.cpp`'s `Rig` struct, add `float defaultCruiseMmS_ = 150.0f;`
   — seeded to match the block layer's own `defaultSpeed` (15 cm/s =
   150 mm/s, `main.ts`), not derived from any kernel constant.
2. Rewrite `engineDefaultCruiseMmS()` to `return
   ensure().defaultCruiseMmS_;` — delete the `fullDutyVelocity`/
   `countsPerMm` derivation entirely.
3. **Do not touch** `onWheelsX`/`onMoveX`/`onGoToR`/`onGoToW`
   (`wire_adapter.cpp`) — their existing `resolvedCruise <= 0.0f ?
   kRange : ...` refusal logic already does the right thing for an
   unconfigured/zero default; only the value `engineDefaultCruiseMmS()`
   returns changes.
4. Add `DefaultCruise = 15` to `main.ts`'s `ConfigField` enum (`//%
   block="default cruise speed"`), `{"default_cruise", 15}` to
   `wire_adapter.cpp`'s `kFields`, and a case 15 in both
   `setKernelValue()` (`if (v > 0.0f) r.defaultCruiseMmS_ = v;` —
   same `>0` silent-ignore validation style as `setGeometry()`) and
   `getConfigValue()` (`v = r.defaultCruiseMmS_;`) in `shims.cpp`.
5. **Required co-edit, not optional**:
   `tests/host/wire_motion_verb_shim.cpp`'s `engineDefaultCruiseMmS()`
   test double currently mirrors the OLD derivation
   (`fullDutyCountsPerS / cpm`, reading
   `g_activeWaHandle->kernel.config().fullDutyVelocity`) — this is
   the same shape the real function had, correctly mirrored, until
   this ticket changes the real one. Add a settable
   `defaultCruiseMmS` field to `WaHandle` (default 150.0f, mirroring
   the real seed) and a `wa.set_default_cruise(v)` Python binding
   (mirroring `set_full_duty_velocity`'s existing pattern), and change
   the test double's `engineDefaultCruiseMmS()` to return it instead
   of deriving from `fullDutyVelocity`. **If this step is skipped,
   the existing cruise-zero tests (next item) silently keep testing
   the OLD, wrong contract and pass anyway** — this is the ticket's
   single highest-risk item.
6. Rewrite the three existing test pairs that currently assert the OLD
   contract: `test_wheels_x_cruise_zero_uses_configured_default`/
   `test_wheels_x_cruise_zero_without_configured_default_is_range_error`,
   and their `MOVE_X`/`GO_TO_R` siblings
   (`tests/host/test_wire_motion_verbs.py`) — change each "uses
   configured default" test to set `default_cruise` via the new
   `wa.set_default_cruise(150.0)` (or similar) and assert the
   resolved cruise is 150 mm/s, not `fullDutyVelocity`-derived. The
   "without configured default" tests should set `default_cruise` to
   `0` (its own no-op-if-`<=0` path — confirm `Rig`'s field starts at
   150.0f by default in production, so this test must explicitly
   force it to `0` via the test double, unlike before where merely
   never calling `set_full_duty_velocity` sufficed) and assert
   `kRange`.
7. **Add the missing fourth pair**: `test_go_to_w_speed_zero_uses_
   configured_default`/`..._without_configured_default_is_range_error`
   — `test_wire_motion_verbs.py` currently has pairs for `WHEELS_X`/
   `MOVE_X`/`GO_TO_R` but none for `GO_TO_W`, even though issue text
   explicitly asks for coverage on "all four verbs." Follow the
   `GO_TO_R` pair's pattern, accounting for `GO_TO_W`'s pose-source
   gating (`waSetPoseSourceAvailable`).
8. `docs/design/specification.md` §4.8's `ConfigField` table gains the
   `DefaultCruise`/15 row. Direct edit on the sprint branch — not part
   of this project's canonical design-doc-overlay set.
9. **Due diligence, not a blocking task**: grep `tools/` for a literal
   `cruise 0`/` 0 ` fourth-field pattern that might be relying on the
   old full-duty behavior. None is expected (not confirmed) — note
   findings in the PR/commit message either way; fixing any such tool
   is sprint 013's tooling-consolidation scope, not this ticket's.

## Acceptance Criteria

- [ ] `engineDefaultCruiseMmS()` no longer references
      `fullDutyVelocity` or `countsPerMm` in its body; returns the new
      `defaultCruiseMmS_` Rig field.
- [ ] The four `onWheelsX`/`onMoveX`/`onGoToR`/`onGoToW` handlers in
      `wire_adapter.cpp` are diff-empty for this ticket (confirm via
      review — their refusal logic was already correct).
- [ ] `wire_motion_verb_shim.cpp`'s test double is updated in the same
      commit/PR as the real `engineDefaultCruiseMmS()` change — not a
      follow-up.
- [ ] All three existing cruise-zero-default test pairs pass against
      the NEW contract (asserting ~150 mm/s, not ~875 mm/s) — verify
      by reading the diff, since a stale, unedited assertion for the
      old value would also "pass" if the test double were
      inadvertently left unchanged (the exact risk item 5 above
      exists to prevent).
- [ ] A new `GO_TO_W` cruise/speed-zero-default test pair exists and
      passes.
- [ ] `default_cruise` is settable/gettable via `SET`/`GET` and via
      the generic `set config` block (no new dedicated block needed).
- [ ] Full existing host suite passes.

## C++11 Gate Coverage

- **Inside the gate**: `wire_adapter.cpp`/`.h` (the new `kFields` row;
  the four verb handlers, confirmed unchanged); the host test file
  itself is C++20 test infrastructure, not target code.
- **Outside the gate**: `shims.cpp` (`defaultCruiseMmS_`,
  `engineDefaultCruiseMmS()`'s rewrite, the `setKernelValue`/
  `getConfigValue` case-15 bodies — `shims.cpp` includes `pxt.h`,
  never host-compiled) and `main.ts` (the `ConfigField` entry — no
  host-test coverage of `main.ts` exists at all). The host suite
  proves the wire-layer contract (via the test double, which is
  written to mirror the real function's behavior but is not the real
  function) and the kernel's own refusal logic; it does not prove
  `shims.cpp`'s actual `defaultCruiseMmS_`/`engineDefaultCruiseMmS()`
  compile for either real embedded target, or that 150 mm/s is what
  actually ships to the robot. No robot is required to complete this
  ticket — a PXT build plus code review covers the `main.ts`/
  `shims.cpp` pieces the host suite cannot reach.

## Testing

- **Existing tests to run**: full `tests/host/test_wire_motion_verbs.py`.
- **New tests to write**: rewritten cruise-zero pairs for `WHEELS_X`/
  `MOVE_X`/`GO_TO_R` (existing tests, new assertions); a new pair for
  `GO_TO_W`.
- **Verification command**: `pytest tests/host/test_wire_motion_verbs.py -k "cruise or speed_zero"`
  plus a full `pytest tests/host/` run before marking this ticket done.
