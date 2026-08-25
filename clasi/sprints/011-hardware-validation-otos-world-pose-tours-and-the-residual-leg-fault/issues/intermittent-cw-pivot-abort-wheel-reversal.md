---
status: in-progress
sprint: '011'
tickets:
- 011-002
- 011-003
- 011-004
- 011-006
---

# Residual intermittent leg fault in square tours (successor issue)

> **2026-08-20 rewrite.** This issue originally blamed a CW-pivot
> wheel-reversal failure; every theory it contained has since been
> tested on instrumented hardware. RETIRED THEORIES (with the evidence
> that killed each): battery sag (stakeholder-confirmed fine),
> tick-loop starvation (GAP telemetry: worst inter-tick gap 48 ms in
> both passing and failing runs), encoder 0x46 latch (wpk streak
> instrumentation: max driven identical-read streak 2 ticks across all
> campaigns), direction mirroring (fixed by the port swap, camera-
> verified), track/scrub calibration (measured and applied).
>
> ROOT CAUSE FOUND AND FIXED for the dominant failure (commit 3e919e5):
> move completion never delivered the kernel's neutral to the motors --
> the completing tick's caller exits its while(tickDrive()) loop, the
> staged zero needs one more step, and the wheels coasted at full duty
> until the starvation watchdog's ~100-150 ms port stop. Intermittency
> came from the protocol fiber's co-ticking (also removed, ownership
> flag) sometimes delivering the missing step by luck. The
> through-zero reversal-dwell hole (wedgelab (20,50] ms latch window)
> was also closed the same day.

## What remains

After the fixes: turn overshoot is gone (headings close within ~7 deg
consistently), tours complete ~70% with near-misses at the 60 mm
threshold. The residual: occasional distance-leg errors (a straight
overrunning or a tour truncating mid-leg, e.g. finals (-275,141) or
(471,671,273deg) in the 2026-08-20 warm campaign). Signature differs
from the fixed class: heading usually still closes. Instrumentation in
place for the hunt: GAP (tick gaps), wpk (encoder streaks), DIAG over
radio at 1 Hz, per-run radio/USB TLM traces.

Next probes: per-leg believed-vs-target logging at move end (what did
serviceMove think it hit?); check the moveDeadline path (duration
math) for legs that truncate; first-move-after-boot special-casing
(ADDRESSED below, ticket 011-004).

## 2026-08-25 finding: first-move-after-boot special-casing (ticket 011-004)

**Status: CODE-REVIEW FINDING, NOT HARDWARE-CONFIRMED.** Read-only trace
of `src/nezha_port.cpp`, `src/nezha_port.h`, `src/shims.cpp` (`Rig`,
`ensure()`, `tickDrive()`, `odomUpdate()`), `src/diffdrive.cpp`/`.h`
(`begin()`, `start()`/`run()`, `step()`, `controlStep()`, `fastPid()`,
`positionError()`), and `src/otos_port.cpp`. No hardware was run for
this ticket (none required per its acceptance criteria). Ticket 006's
bench campaign is where any of this gets tested against reality.

**Mechanism found: one real, confirmed, boot-specific special case.**
`NezhaMotorPort::writeRawDuty()` (`nezha_port.cpp:212`, sentinel
`kNeverWritten = -128` at `nezha_port.h:68`/`123`) skips slew-rate
limiting on the literal first write of a motor port's lifetime -- an
intentional fix, per its own comment, for a previously-observed
wrong-direction-first-command wedge trigger. Normally a `kNeverWritten`
sentinel like this is expected to get "used up" harmlessly by an early
idle zero-write, before anything that matters reads it. That is NOT
what happens here:

- The kernel's own free-running fiber pacer (`DifferentialDrive::
  start()`/`run()`) is deliberately left **unwired**: `shims.cpp`'s
  `ensure()` has `// rig->kernel.start();` commented out, with an
  explicit "TICK MODEL" comment stating every control cycle now runs
  only on whichever fiber calls `tickDrive()`.
- `tickDrive()` is caller-driven only -- confirmed by grepping every
  call site in `src/main.ts`: all seven are inside `while (_tickDrive())`
  loops tied to an actual move/drive block (`tickedMove()`, the
  continuous-drive helpers, `updateMove()`'s poll). There is no
  `basic.forever` background loop stepping the kernel.
- `ensure()` calls `rig->kernel.begin()` once (`left_.begin();
  right_.begin();` in `diffdrive.cpp`), which zeroes each motor's
  encoder baseline via READ-ONLY I2C transactions -- it never calls
  `tick()`/`writeRawDuty()`, so it never touches `lastWrittenPct_`.
  The starvation watchdog (the one background fiber `ensure()` does
  launch) also can't consume the sentinel at boot: `commandLooksActive()`
  is false when idle (no move, `appliedDutyLeft/Right` both read 0 --
  `appliedDuty()` returns 0 exactly when `lastWrittenPct_ ==
  kNeverWritten`), so the watchdog `continue`s instead of calling
  `emergencyStop()`.
- `stopAll()`/`estopAll()` (which *would* consume the sentinel early,
  via `deliverStopNow()`'s direct `emergencyStop()` calls, bypassing
  `tick()`) are wired only to explicit STOP/ESTOP wire commands
  (`wire_adapter.cpp:499,547`) and the `stop`/`emergency stop` blocks
  (`main.ts:661,670`) -- nothing in the traced files calls either one
  automatically at boot or on connect. (Caveat: if some host/tour
  script issues a STOP before the first move as a defensive habit,
  that would consume the sentinel first and this whole mechanism
  would not fire on that boot -- not visible from code alone.)

Net: `lastWrittenPct_` is still `kNeverWritten` at the moment of the
very first real move's very first control cycle. **Both wheels' first
duty write of the robot's life lands on the brick in one shot, with no
slew-rate ramp** (`slewRate_` = 25 pct/tick normally caps how fast
duty can change per ~24 ms cycle). Every subsequent move, for the rest
of that boot, ramps normally, because `lastWrittenPct_` now holds a
real percent (typically 0, from the prior move's stop) instead of the
sentinel.

**Checked whether the commanded duty itself is also inflated on cycle
1, not just unramped -- it is not, in this project's actual config.**
Traced `controlStep()`/`fastPid()`/`positionError()` for the kernel's
first-ever `step()` (`everCycled_` false -> `measuredPeriodUs = 0` ->
`dt = 0`): `positionError()` returns 0 whenever `dt <= 0`, so the
integral term is 0; `cmdAccelLeft_/Right_` only update `if (dt > 0.0f)`,
so the feedforward-accel term is 0; and `shims.cpp`'s `ensure()` sets
`cfg.kp = 0.0f` in this project's actual runtime config, so the
proportional term is 0 regardless of how large the velocity error
reads (and it does read large -- `sampleLeft_.velocity` defaults to 0
before the first sample, so `errLeft = speedLeft - 0`). All three
`fastPid()` terms are zero on cycle 1. The only nonzero contributor is
`correctedCommand()`'s feedforward, computed with `lastSpeedLeft_ = 0`
-- but that is the SAME "starting from rest" formula every move uses
after a neutral stop (`controlStep()`'s neutral branch resets
`lastSpeedLeft_/Right_` to 0 on every stop), not something unique to
the first move. So the *magnitude* commanded on cycle 1 is ordinary;
only the *write path* (motor port slew) is boot-special.

**Relation to the issue's signature.** Both wheels carry their own
independent `kNeverWritten` sentinel and (for a straight leg, equal
commanded speeds) would jump together -- symmetric, not a differential
effect -- consistent with "heading usually still closes." The plausible
effect is distance/timing-only: leg 1's wheels reach commanded duty
faster than every subsequent leg's ramp-limited start. Whether that is
large enough to show up as a measurable distance error depends on
whether move completion is governed by closed-loop position feedback
(self-correcting, likely no residual effect) or by a fixed duration
budget -- **exactly ticket 011-003's scope (moveDeadline duration
math)**, not re-derived here. Flagging the cross-reference rather than
guessing at the interaction: if `moveDeadline` assumes a ramp-limited
acceleration profile when budgeting a leg's expected duration, a
first-leg-only faster ramp would make the robot cover more ground than
that budget assumed in the same elapsed time -- a plausible contributor
to "a straight overrunning," not obviously to a truncation. Ticket
011-003 should check whether its duration math makes any
ramp-profile assumption before concluding this interacts with it.

**Other first-call special cases considered and ruled out (benign, not
contributors):**

- `NezhaMotorPort::collect()`'s `hasLastTick_` gate: the first-ever
  `collect()` reports `velocity_ = 0.0f` (no delta computed) rather
  than a measured value. Harmless: this happens on the same cycle the
  sentinel already covers, and `collect()` runs before this cycle's own
  duty write takes physical effect, so no real motion is misreported.
- `shims.cpp`'s `odomUpdate()` `odomPrimed` gate: the Rig's odometry
  primes silently (no delta applied) on its first-ever call. This
  looked like a candidate for "lost first-tick distance" but is ruled
  out: `odomUpdate()` now runs unconditionally every `tickDrive()`
  cycle, immediately after `kernel.step()` (the sprint 006 ticket 003
  fix for `continuous-mode-odometry-chord-error.md`), so its first-ever
  call always coincides with the kernel's first-ever step, when
  accumulated position is still ~0. Nothing is silently dropped in the
  current code.
- `DifferentialDrive`'s `WheelSample` defaults (`connected = false`)
  before the first `refreshSample()`: skips the twist-hold-trim term
  and the stall/deficit detectors for cycle 1 only (their guards
  require `sampleLeft_.connected && sampleRight_.connected`). Real, but
  affects turning-trim/fault-latching, not raw commanded distance.
- `DifferentialDrive::begin()`'s `stopEnforceCountdown_` (30 ticks):
  forces zero-duty writes through even when the software cache thinks
  the wheels are "already quiet," for defensive reasons (guards against
  booting with a brick already latched non-zero). Read as unrelated to
  leg length -- it only affects redundant *zero* writes.
- `NezhaMotorPort::begin()`'s median-of-3 encoder baseline zeroing:
  runs once, before any move, via read-only I2C. Every move after boot
  reads from the same anchored `encOffset_` through the ordinary
  `collect()` accept path -- no first-move-vs-steady-state difference
  found here.

**Connection to the 2026-08-25 vevov hardware evidence (per the
dispatcher's brief -- vevov runs the older 12-column POSE firmware, not
confirmed on master).** Two separate observations were flagged:

1. *ox/oy/oh stayed byte-identical through an entire drive.* Nothing in
   this ticket's traced files (`nezha_port.cpp`, `shims.cpp`'s
   `Rig`/`ensure()`, `diffdrive.cpp`) contains a caching layer that
   would freeze a telemetry value across an entire drive while a
   parallel live-read path (`logFix`) updates correctly -- that pattern
   is a projection/snapshot-building concern, not a boot-state one.
   This is out of this ticket's scope; sprint 004/005 already has a
   ticket tracking the WireAdapter telemetry projection/`buildSnapshot()`
   path, which is the right place for it.
2. *Encoder odometry (497,302) vs. the OTOS-side reading (386,345) --
   ~11 cm apart at rest, before any motion.* The boot-path trace
   explains a real, non-buggy reason these CAN disagree: `rig.x/y/
   heading` (encoder odometry, `EncoderPoseSource`) and `gOtos`'s
   `x_/y_/heading_` (`OtosPort`, `shims.cpp`'s separate `otosRef()`
   lazy singleton) are two INDEPENDENT lazy singletons with no
   automatic mutual sync at boot. The only code path that aligns them
   is the explicit V6 SEED command (`seedPose()`, `shims.cpp:1163-1171`),
   whose own comment states it "writes BOTH pose sources... so the two
   start agreed and their later divergence IS the drift being
   measured." Absent a fresh seed/fix, two independently-drifting
   dead-reckoning-style estimators (odometry scrub/slip vs. OTOS's own
   IMU/optical error) disagreeing at rest is architecturally expected,
   not itself a defect. That said: the specific number (386,345) quoted
   for the "at rest, before motion" OTOS reading is BYTE-IDENTICAL to
   the value reported as frozen through the entire subsequent drive in
   observation 1 above, while a live OTOS fix (RUN:fix) tracked that
   same real drive to within 2 mm. That coincidence is stronger
   evidence the "at rest" (386,345) reading was already the stale
   telemetry-projection cache, not a live OTOS sample -- i.e.
   observation 2 is likely the SAME bug as observation 1, surfacing
   twice, rather than a second, independent disagreement. This ticket
   did not trace `wire_adapter.cpp` to confirm that (out of scope and
   out of this ticket's touched-files list); flagging the coincidence
   for whoever owns the sprint 004/005 telemetry ticket to weigh.

**Follow-up candidate (not implemented here, per this ticket's scope):**
if bench evidence (ticket 006) ever shows the boot-only unramped first
write actually matters, the fix is narrow and low-risk: seed
`lastWrittenPct_` to `0` instead of `kNeverWritten` at construction (or
have `NezhaMotorPort::begin()` write a real zero through the shaping
path once, consuming the sentinel deliberately at boot instead of
leaving it live for the first real move). Do not make this change
without bench confirmation -- the current behavior is intentional
(guards a documented wedge bug), and removing it blind could reopen
that bug. Not attempted here per acceptance criteria.
