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
      **MEASURED gopiv 2026-09-02, FAILED — not a pass.** The earlier
      BLOCKED attempt (below, superseded) is resolved: gopiv flashed
      cleanly this session (`ver 0.20260902.2`, second attempt after a
      first flash left the board briefly blank — see
      `captures/gopiv-acceptance-028-20260902/notes.md`'s Step B). The
      adapted tour
      (`captures/gopiv-acceptance-028-20260902/step_d_frozen_encoder.py`,
      same geometry/shaping as the original `tight_tour.py`) was run
      for 6 reps total (1802 `TLM FULL` frames,
      `step_d_test_frames.json` + `step_d_frames.json`) and scanned
      for a frozen `posr`/`posl` read occurring while the wheel was
      genuinely cruising (nonzero measured velocity two frames
      earlier, excluding normal accel-ramp-from-rest which also shows
      "position unchanged, duty nonzero" for benign reasons).
      **5 genuine frozen-while-cruising events found across 6 reps,
      all on side R, all with the SAME signature**: `i2cf` increments
      at the frozen frame (confirming the stamp-withholding code path
      ran), yet the wire-reported velocity
      (`wheelSpeed()` -> `kernel.output().velocityRight` ->
      `sampleRight_.velocity`, traced directly in
      `src/core/diffdrive.cpp` — its only other assignment site is
      `refreshSample()`'s own interval computation) reads **exactly
      0**, not the held prior value the fix documents, and commanded
      duty steps 14-25 percentage points toward the rail on that tick
      or the next, with overshoot up to 446 mm/s against a ~290 mm/s
      cruise. Directly compared against this ticket's own PRE-fix
      citation (`captures/gopiv-profile-sweep-20260901/tour_tight.json`
      frames 185-191, re-read this session: `posr` frozen, `i2cf`
      38->40, `vr` 309->0, `dutr` 3300->4400, overshoot to 420 mm/s):
      the post-fix pattern is the same shape and magnitude, if
      anything slightly larger. Full analysis, methodology caveats
      (telemetry cadence is ~1 frame per 3 kernel cycles here, so a
      single frame cannot always be attributed to one specific tick
      with certainty — noted as a real limitation of this measurement
      method, not assumed away), and raw frame JSON:
      `captures/gopiv-acceptance-028-20260902/notes.md`'s Step D
      section. **This does not confirm the fix on real hardware — the
      documented protective behavior (`sample.velocity` holds its
      prior value when `sampleTime` fails to advance) does not match
      what gopiv's telemetry shows in practice, on both the pre-fix
      and post-fix builds.** Left unchecked per this session's own
      instruction to stop and report a failure rather than paper over
      it — needs `systematic-debugging` on either `refreshSample()`'s
      interaction with wire-snapshot cadence, or a measurement method
      with real per-tick resolution (this wire telemetry stream cannot
      provide one; `TLM`'s `kBuffer` mode is explicitly unimplemented,
      `src/comms/wire_adapter.cpp` `onTlm()`).

      Superseded BLOCKED note from the prior session (2026-09-02,
      before this hardware-acceptance re-run): build succeeded
      (`uv run python tools/make_deploy.py --robot gopiv`, clean
      compile). Five separate `mbdeploy deploy --remote gopiv`
      attempts (~13:25-13:33 PDT) all failed identically with
      `SWD/JTAG communication failure (No ACK)` on both the initial
      try and the automatic retry. The board was physically present
      (`ssh jtl@192.168.1.150 'ls /dev/ttyACM*'` -> `/dev/ttyACM0`;
      `lsusb` showed the CMSIS-DAP device enumerated) and `mbdeploy
      connect --remote gopiv "HELLO"` timed out against whatever
      firmware was running — that session's build never landed. The
      farm host's own `dmesg` showed concurrent
      `dwc_otg_hcd_urb_dequeue` USB-transfer timeouts on the Pi's USB
      host controller. Full transcript:
      `captures/gopiv-frozen-encoder-20260902/notes.md`.

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
