---
id: '001'
title: Frozen-encoder read holds the previous velocity instead of manufacturing a
  zero
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: frozen-encoder-read-becomes-a-phantom-zero-velocity-and-the-pid-overreacts.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Frozen-encoder read holds the previous velocity instead of manufacturing a zero

## Description

A failed or frozen encoder I2C read gets silently reinterpreted as
"wheel stopped," not "read failed," and the velocity PID lunges toward
the rail chasing a fabricated error. MEASURED gopiv 2026-09-01,
`captures/gopiv-profile-sweep-20260901/tour_tight.json` frames 185-191:
`posr` frozen, `vr` reported 0 while the wheel was actually doing
~309 mm/s, duty stepped 3300→4500, wheel overshot to 420 mm/s.

Investigation during sprint planning traced this precisely (see sprint
028's `design/DESIGN.md` §7 overlay for the full write-up):
`DifferentialDrive::refreshSample()` (vendored kernel,
`src/core/diffdrive.cpp`) already holds `sample.velocity` correctly
when `motor.sampleTime()` fails to advance — and
`NezhaMotorPort::collect()` (`src/platform/nezha_port.cpp`) already
withholds a fresh `sampleTimeUs_` stamp on an outright I2C read
failure (`readEncoderRaw()` returns `false`), so that specific case is
already correct today. The actual gap: a *successful* read
(`readEncoderRaw()` returns `true`) that returns the SAME raw counts
as the previous tick while the wheel is under active drive
(`appliedDuty()` nonzero) — one documented mechanism is the "encoder
wedge" (`src/DESIGN.md` §7: an instant H-bridge flip latching the 0x46
readback), though the fix does not need to identify the cause.
`collect()`'s success branch advances `sampleTimeUs_` unconditionally
today, so `refreshSample()` computes `(pos - lastPos) / dt = 0` — an
honestly-derived-but-wrong zero from stale data.

**Scope decision (binding, do not revisit mid-ticket without going
back to the sprint's Architecture section): this fix lives entirely in
`src/platform/nezha_port.cpp`. `src/core/diffdrive.{h,cpp}` (the
vendored kernel, synced byte-for-byte with radio-robot-firm's own copy
per `src/DESIGN.md` §2) must NOT be touched.** The existing
`sampleTime != sample.sampleTime` gate in `refreshSample()` already
does the right thing once the platform layer stops advancing the
stamp on this one additional case.

## Acceptance Criteria

- [x] `NezhaMotorPort::collect()`'s success branch withholds a fresh
      `sampleTimeUs_` stamp when the newly-read raw counts equal the
      previous sample's raw counts AND `appliedDuty()` is nonzero
      (reusing the existing wedge detector's "driven" signal, at a
      single-tick threshold — not the multi-tick `kWedgeThreshold` the
      `wedgeLatched_`/`wedgeSuspect_` flags use).
- [x] `src/core/diffdrive.{h,cpp}` are byte-identical to their state
      before this ticket (`git diff` empty on both files at ticket
      close).
- [x] A wheel legitimately at rest (zero applied duty, unchanged
      position across many ticks) still reports velocity 0 every tick
      — the fix must not defeat a genuine stop.
- [x] The held tick still increments `i2cFaultCount_`/`i2cf` — the
      failure stays visible in telemetry and `STATUS`, not smoothed
      away (this is a net IMPROVEMENT over today: this specific
      frozen-but-acked case does not currently increment `i2cf` at
      all, since `sampleTime` currently DOES advance for it).
  - [x] This ticket does not change `i2cf`'s behavior on a genuinely
        idle bus (`i2c-fault-count-climbs-on-idle-bus` is a separate,
        out-of-scope issue) — a host test proves an idle, undriven
        wheel with unchanged position does NOT tick `i2cf`.
- [x] Host test (`tests/host/motion_engine_shim.cpp`'s existing
      `meMotorArmPosition`/`meArmSettleProfile` scripting, extended if
      needed) scripts a repeated raw encoder position under nonzero
      commanded duty and asserts commanded duty does not step toward
      the rail on the frozen tick or the tick immediately after.
      Implemented as `tests/host/test_frozen_encoder_hold.py` against
      `tests/host/kernel_shim.cpp` instead of `motion_engine_shim.cpp`
      — `motion_engine_shim.cpp` exposes no `Kp`/PID-gain setters (its
      own header comment states its baseline config is deliberately
      "pure feedforward, no PID contribution"), so it cannot exercise
      the actual mechanism (a proportional-gain PID reacting to a
      phantom zero-velocity error) this ticket's bug depends on.
      `kernel_shim.cpp` already exposes `kdSetKp`/`kdMotorArmPosition`/
      `kdOutI2cFaultCount` (the last of these newly bound in
      `test_kernel_harness.py`'s `_bind()` — it existed in the shim
      but was never wired to ctypes before this ticket). Three tests:
      the fixed contract (duty holds, `i2cf` still increments), a
      counterfactual for the pre-fix contract (duty spikes, `i2cf`
      does NOT increment for that tick — methodology check, proves the
      first test isn't vacuous), and the genuinely-idle case.
- [ ] Hardware acceptance: re-run
      `captures/gopiv-profile-sweep-20260901/tight_tour.py` on gopiv
      (MEASURED citation required, naming the fresh capture file) and
      confirm no speed excursion in the 1-2 ticks following an `i2cf`
      increment, across the tour shapes the original capture used.
      **BLOCKED, not attempted-and-passed.** Build succeeded
      (`uv run python tools/make_deploy.py --robot gopiv`, clean
      compile). Five separate `mbdeploy deploy --remote gopiv`
      attempts (~13:25-13:33 PDT 2026-09-02) all failed identically
      with `SWD/JTAG communication failure (No ACK)` on both the
      initial try and the automatic retry. The board is physically
      present (`ssh jtl@192.168.1.150 'ls /dev/ttyACM*'` ->
      `/dev/ttyACM0`; `lsusb` shows the CMSIS-DAP device enumerated)
      and `mbdeploy connect --remote gopiv "HELLO"` times out against
      whatever firmware is currently running — this ticket's build
      never landed. The farm host's own `dmesg` shows concurrent
      `dwc_otg_hcd_urb_dequeue` USB-transfer timeouts on the Pi's USB
      host controller, a plausible root cause external to this
      ticket's code. Full transcript:
      `captures/gopiv-frozen-encoder-20260902/notes.md`. No MEASURED
      claim is made about on-hardware behavior of this fix — retry
      once the farm host's USB/probe connection to gopiv is recovered
      (needs physical or `sudo` access to the meili Pi, neither
      available to this session).

## Implementation Plan

**Approach.** Add the "driven and unchanged" condition to
`NezhaMotorPort::collect()`'s existing success branch (around
`src/platform/nezha_port.cpp:409-417`), guarding the `sampleTimeUs_ =
nowUs;` stamp. Reuse `appliedDuty()` (already a `NezhaMotorPort`
method) and a simple raw-counts-equal check against the last
successfully-read raw value — this does not need `EncoderGlitchArmor`
(`encoder_glitch_armor.h`), which handles implausible JUMPS, a
different failure shape from an unchanged reading.

**Files to modify.**
- `src/platform/nezha_port.cpp` — `collect()`'s success branch.
- `src/platform/nezha_port.h` — if a new member is needed to remember
  "last raw counts seen" separately from `lastPosition_` (which is
  already offset-adjusted; check whether comparing `pos ==
  lastPosition_` is equivalent to comparing raw values before adding a
  new field — it should be, since `encOffset_` is constant across
  these two ticks, but confirm before assuming).
- `tests/host/motion_engine_shim.cpp` and/or `tests/host/fake_ports.h`
  — extend scripting if the existing `meArmSettleProfile` shape cannot
  already express "repeat the same encoder position for N ticks under
  nonzero duty."

**Testing plan.** Host tests as listed in Acceptance Criteria above,
run scoped (`uv run pytest tests/host/ -k encoder or velocity`, or the
project's equivalent scoped invocation — confirm the actual test file
name during implementation). Hardware acceptance on gopiv per the
Success Criteria in sprint.md, with a MEASURED citation
(`.claude/rules/measurement-citations.md`) naming the fresh capture
file, board, and date.

**Documentation updates.** None beyond this ticket and the sprint's
`design/DESIGN.md` overlay (already written during planning) — no
separate doc file to touch. If implementation reveals the raw-vs-`pos`
equivalence assumption above is wrong, note the correction in this
ticket's own file, not by editing `core/diffdrive.{h,cpp}`.

**Implementation note (raw-vs-`pos` equivalence, resolved during
implementation).** The plan's assumption does NOT hold in one case:
`kAcceptAsRebaseline` deliberately re-anchors `encOffset_` so that
`pos == lastPosition_` by construction even though the RAW value
genuinely jumped (a counter-restart recovery, not a frozen read) — so
comparing `pos` alone would misclassify that tick as frozen. Rather
than adding a new "last raw counts" member to `nezha_port.h`, the fix
captures `glitchArmor_.lastGoodRaw()` into a local BEFORE calling
`glitchArmor_.evaluate(raw)` (which mutates it), and gates the new
condition on `decision == EncoderGlitchArmor::Decision::kAccept` (never
`kAcceptAsRebaseline`) plus `raw == previousGoodRaw`. No new member,
no header change.
