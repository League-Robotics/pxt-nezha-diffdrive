---
id: '001'
title: Raw-duty pulse primitive (engine + diagnostic exposure)
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: nudge-mode-settle-gated-pulse-stepper-for-sub-floor-micro-moves.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Raw-duty pulse primitive (engine + diagnostic exposure)

## Description

The kernel already has a PID-free raw-duty mode (`DiffDrive::driveDuty()`,
`kModeRawDuty`, `src/core/diffdrive.h:69,204`) that bypasses PID, the
speed floor, the crawl dither and twist-hold, while still honoring
E-stop and lease expiry. Nothing exposes it today above the kernel.
This ticket adds the diagnostic substrate the go/no-go characterization
(ticket 003) needs: a `MotionEngine`-level primitive that fires one
bounded-amplitude, bounded-width duty pulse per wheel, hard-zeros, and
reports the encoder counts each wheel moved once settled — no
automatic looping, no settle-gating beyond the single report.

This is groundwork only. Do not build the settle-gated stepper here —
that is ticket 004, gated on ticket 003's verdict.

## Scope

- New `MotionEngine` method(s), e.g. `pulseWheels(ampLeft, ampRight,
  widthTicks)` returning the per-wheel encoder-count delta once both
  wheels read at rest (reuse the rest test `settleToRest()` already
  uses, `kSettleRestCountsPerS`/`kSettleMaxSteps`,
  `src/motion/motion_engine.h:211-212`).
- Diagnostic exposure so the characterization gate (a human/script on
  the floor) can drive it: either a new sequenced wire verb or a
  RUN-accessible path. Per `.claude/rules/playfield-testing.md`'s v6
  sequencing rule, anything whose correctness depends on stream
  position or that mutates the robot needs `#<id>`; the cleartext
  `RUN:`/`DIAG` vocabulary is a separate, unsequenced parser path.
  Choose whichever fits the existing wire_adapter.cpp/shims.cpp
  patterns better and document the choice in this ticket's
  implementation notes.
- Report units in BOTH encoder counts and mm (vevov: ~0.79 mm/count
  straight, ~0.8 deg/count per wheel in a pivot — travel_calib
  0.79324), since the characterization gate's own acceptance test
  (ticket 003, SUC-001) is stated in both.
- A single-tick pulse cannot exceed ~25% duty and a two-tick pulse
  ~50%, per the port's own 25%/tick slew (`src/platform/
  nezha_port.cpp:291` area) — this is a hardware constraint on the
  primitive's own amplitude/width arguments, not something to work
  around; document it in the primitive's own comment.

## Acceptance Criteria

- [x] `MotionEngine` exposes a pulse-fire primitive taking per-wheel
      amplitude (duty %) and width (kernel ticks), driving the kernel
      via `driveDuty()`, then hard-zeroing.
- [x] The primitive reports each wheel's encoder-count delta, measured
      only once both wheels read at rest afterward.
- [x] The primitive is reachable from a host script/wire client without
      requiring a full nudge-mode loop.
- [x] Host tests pin: a pulse of a given amplitude/width drives exactly
      that shape into a fake motor port, the primitive hard-zeros
      afterward, and the reported delta matches the fake motor's
      simulated encoder movement.
- [x] No edit to `src/core/diffdrive.{h,cpp}`.
- [x] Every new yield point (if any) goes through
      `diffDrive::vfpSafeSleep()`/`vfpSafeYield()`
      (`.claude/rules/fiber-yield-safety.md`) — most likely none is
      needed since this reuses `driveDuty()` + the existing settle
      loop, but confirm before closing.
- [x] No unit suffix in any new identifier; units are `// [unit]`
      trailing comments (`.claude/rules/no-units-in-identifiers.md`).
- [x] `execPulse()`'s wire reply uses integer-only formatting (no
      `%f`/`%.Nf`/`%g`/`%e` conversion anywhere in `src/comms/`) — added
      2026-09-16 after the hardware-only defect below; pinned by
      `tests/host/test_no_float_format_specifier_in_wire_layer_source_pin.py`.

## Hardware defect found and fixed (2026-09-16)

**Reopened by team-lead during ticket 003's hardware session.**
`WireAdapter::execPulse()` (`src/comms/wire_adapter.cpp`, the
`std::snprintf` originally near line 987) formatted its `ret` reply
with `%.1f`/`%.2f`. The micro:bit target's newlib-nano printf has no
float conversion support — not truncated, not wrong digits, the whole
conversion comes back EMPTY.

MEASURED vevov 2026-09-16, team-lead session, over the farm serial link
(null.local:41285), firmware `vevov-nudgehang0915`:

    TX  RUN pulse 25 0 1 #21
    RX  ack 21 9 stop
    RX  ret left_counts= right_counts= left_mm= right_mm= #21

Every field name present, every value empty. The pulse itself EXECUTED
correctly — the camera measured ~1.55 cm of arc over 21 single-wheel
pulses (about 0.74 mm each), and `cyc` advanced normally. Only the
reporting was broken, which made the verb useless for ticket 003's
characterization gate (it depends on the encoder counts).

Every other wire formatter in this codebase already uses integer
conversions only (`%d`/`%ld`/`%lu`/`%x`/`%u`/`%s`) for exactly this
reason — see `wire_handler.cpp`'s `formatConfigValue()` and its own
"no %f" comment. `execPulse()` was the one holdout that reached
hardware before anyone noticed a host test (linked against the desk's
own libc, which DOES support `%f`) could not catch.

**Fix**: `execPulse()` now rounds the encoder deltas to the nearest
count (`left_counts`/`right_counts`, unchanged field names) and reports
travel as hundredths of a millimetre via new integer-scaled fields
`left_mm_x100`/`right_mm_x100` (replacing the old float `left_mm`/
`right_mm` fields), formatted with `%ld`. A pulse's ~0.7 mm
displacement now resolves to tens of counts of the `_x100` field,
enough for the gate to distinguish 0.3 mm from 2.0 mm.

**New reply format** (host-visible, exact):

    ret left_counts=<int> right_counts=<int> left_mm_x100=<int> right_mm_x100=<int> #<id>

**Regression guard**: `tests/host/test_no_float_format_specifier_in_wire_layer_source_pin.py`
(new) source-pins `src/comms/` against any `%f`/`%.Nf`/`%g`/`%e`
conversion specifier, modeled on `test_no_percent_z_format_specifier_source_pin.py`
and `test_vfp_guard_source_pin.py` — a normal host test cannot catch
this class of defect because the host's own libc formats floats
correctly, which is exactly why this one reached hardware.
`tests/host/test_wire_motion_verbs.py::test_run_pulse_fires_and_reports_encoder_delta_in_counts_and_mm`
updated to pin the new integer field names/format.

Verified: `uv run python tools/make_deploy.py --robot vevov
--profile-suffix=-pulsefix0916` builds a hex with `wire_adapter.cpp`
compiled cleanly (1,804,661-byte `built/binary.hex`). Not reflashed —
team-lead runs hardware.

## Implementation Notes

- **Diagnostic exposure choice: a new C++-native, synchronous `RUN`
  handler (`RUN pulse <ampLeft> <ampRight> <widthTicks> #<id>`), not a
  RUN-accessible TypeScript path.** This project's cleartext `RUN:name`
  bridge and the v6 `RUN name #id` verb both dispatch exclusively to
  handlers a MakeCode/TS program registers with `onRun()`
  (`blocks/run.ts`); this extension itself registers none of its own,
  and `WireAdapter::onRun()`'s reply is void by construction for that
  whole path. The characterization gate needs a result in the SAME
  round trip, so `"pulse"` is intercepted directly inside
  `WireAdapter::onRun()` (`wire_adapter.cpp`) before the registry
  lookup, entirely in C++ -- no template/consumer-repo TypeScript
  changes needed, and no change to `WireHandler`'s own v6 grammar
  mechanics (`RUN`'s existing raw-argv/result-buffer contract already
  fits this exactly; only `WireAdapter`'s own `onRun()` implementation
  changed). `externalOwner_` is checked first, same as the six motion
  verbs, since this drives the wheels.
- New wire-layer forwards: `enginePulseWheels()` (shims.cpp, wraps the
  whole call in the same `BusGuard` `tickDrive()` itself uses, since
  `pulseWheels()` drives its own `kernel.step()` loop synchronously,
  outside the tick engine) and `countsPerMm()` (named identically to
  `MotionEngine::countsPerMm()`, the allow-listed conversion-function
  name, since the usual `engineXxx` prefix would itself carry the
  forbidden `Mm` suffix).
- No `config_fields.h` changes -- out of this ticket's scope (nudge
  amplitude/width/settle-time config rows are ticket 004's).
- Confirmed no new yield point needed: `pulseWheels()`'s only yields are
  inside `kernel.step()`'s own two settle sleeps, already VFP-guarded
  per `fiber-yield-safety.md`'s own note on `settleToRest()`.

## Testing

- **Existing tests to run**: `tests/host/` motion-engine and shim
  suites touching `MotionEngine`/`Rig` (scope to modules this ticket
  touches, per `.claude/rules/source-code.md`).
- **New tests to write**: a fake-motor-port test for the pulse
  primitive (amplitude/width -> commanded duty shape, hard-zero after,
  reported delta correctness); a test confirming E-stop/lease-expiry
  still force neutral during a pulse.
- **Verification command**: the project's host test runner, scoped to
  the touched modules (see `source-code.md`).

