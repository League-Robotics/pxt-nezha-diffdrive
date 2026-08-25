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
serviceMove think it hit? -- SHIPPED, ticket 011-002's
`tools/leg_analysis.py`, see the Bench Campaign Procedure below); check
the moveDeadline path (duration math) for legs that truncate (RULED
OUT, ticket 011-003 -- see finding below: host-tested at ~24 ms tick
cadence against the real engine, deadline never fires before a
genuinely-progressing move, 59-74% margin across every leg shape the
tours issue); first-move-after-boot special-casing (ADDRESSED below,
ticket 011-004).

## 2026-08-25 finding: moveDeadline duration math RULED OUT (ticket 011-003)

**Status: HOST-TEST CONFIRMED, NO DEFECT FOUND.** The issue's own
second next-probe -- whether `MotionEngine`'s `move_.deadline` (set at
both `moveX()` call sites, `motion_engine.cpp:156` inside the pivot
phase and `:221` inside the straight-phase/second-call path, and
checked for expiry in `serviceMove()` via `static_cast<int32_t>(now -
move_.deadline) >= 0`, `motion_engine.cpp:344`) can truncate a move
that is genuinely still progressing toward its commanded target -- is
closed. `tests/host/test_motion_engine_deadline_boundary.py` (5 tests,
all passing) drives the real, unmodified `motion_engine.cpp` at ~24 ms
tick cadence, physically closing the loop on the engine's own staged
duty (no simulated physics, no shortcuts), for the three leg shapes
`test.ts`'s tours actually issue: pure pivot, pure straight, and the
blended split leg that hits `moveX()`'s internal pivot-then-straight
split under one shared deadline.

Timeout source: `src/shims.cpp::startMove()` (lines 379-439) --
`timeoutMs = max(distance/speed, yaw/yawRate) * 1000 + 1500`.

| Leg | shims.cpp timeout | actual (unbounded) | overhead | margin left |
|---|---|---|---|---|
| pure pivot 90 deg | 2500ms | 1464ms | 464ms | 1036ms (69%) |
| split leg 350mm/70deg | 3250ms | 2352ms | 602ms | 898ms (60%) |
| split leg 300mm/50deg (near-threshold) | 3000ms | 2112ms | 612ms | 888ms (59%) |
| split leg 800mm/150deg | 5500ms | 4608ms | 608ms | 892ms (60%) |
| pure straight 600mm | 4500ms | 3384ms | 384ms | 1116ms (74%) |

In every case the real-timeout run finished at the same tick and the
same final encoder position as an unbounded baseline -- the deadline
never fired early. A negative control that stripped the `+1500ms`
margin confirmed the same leg genuinely IS truncated then, proving the
harness can detect real truncation and that the margin is load-bearing
(not just untested slack that happens never to matter). **No defect
found; no source change landed.** Margins run 59-74% across every leg
shape the tours actually command, including the near-threshold
300mm/50deg split -- comfortably clear of the boundary.

**Relation to the issue's residual signature.** This closes the "check
the moveDeadline path" next-probe outright: a leg cannot be truncated
by this mechanism while it is still genuinely progressing, under
normal (non-starved) tick cadence. It does not by itself explain the
residual straight-overrun/mid-leg-truncation fault -- it only rules out
one specific candidate mechanism for it. If the bench campaign below
(ticket 011-006) ever observes a leg whose truncation point lines up
suspiciously close to that leg's own computed `timeoutMs` (rather than
looking like an abrupt stop mid-progress at an arbitrary point), that
would be a NEW signature worth re-opening this finding against real
tick-cadence conditions the host harness may not fully capture (e.g.
genuine I2C-driven tick starvation on hardware) -- but absent that
specific evidence, this mechanism stays ruled out per this ticket's own
host-test result.

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

## Bench Campaign Procedure (ticket 011-006)

**This section is a procedure, not a result.** No campaign has been run
against it yet. It exists so the next bench sitting is one repeatable
session instead of an improvised one, and so its output is scored the
same way every time. Nothing below requires -- or claims -- a robot
result; ticket 011-006's own acceptance criteria forbid that, and this
section is written to satisfy them, not to report a finding.

### Scope limit -- read this first

Everything grounding this procedure's hardware specifics (camera
practicalities, the OTOS-cache freeze, the `RUN:fix` quirk, the `i2cf`
drift) was observed on **vevov, which runs the older 12-column POSE
telemetry frame and does not answer STATUS.** That is confirmed on
vevov's current build, **not** on current master's 20-column FULL
frame. Nothing here should be read as "confirmed on master" until a
campaign is actually run against master-flashed hardware. If master
answers STATUS and/or emits the 20-column frame, note that difference
in the evidence template rather than silently assuming the older
frame's quirks (or lack of them) carry over.

### RETIRED THEORIES -- do not re-test these

Restated inline, per this sprint's own "do not re-test any RETIRED
THEORY" rule (`sprint.md`) and this issue's own 2026-08-20 rewrite.
These five are closed, with the evidence that closed them:

1. **Battery sag** -- stakeholder-confirmed fine.
2. **Tick-loop starvation** -- GAP telemetry: worst inter-tick gap 48 ms
   in both passing and failing runs.
3. **Encoder 0x46 latch** -- wpk streak instrumentation: max driven
   identical-read streak 2 ticks across all campaigns.
4. **Direction mirroring** -- fixed by the port swap, camera-verified.
5. **Track/scrub calibration** -- measured and applied.

**If a symptom during this campaign looks like one of these five
again** (e.g. a suspiciously large tick gap, a frozen encoder read, a
mirrored direction), **do not re-run the original experiment that
closed it.** Record the observation as a new finding against this
procedure's evidence template instead, note which retired theory it
superficially resembles and why it is not simply a recurrence (or, if
it genuinely looks like a regression of a fixed class, say so plainly
and flag it for the team-lead -- but do not spend campaign budget
re-deriving evidence this project already has).

### Pre-session setup (once per bench sitting, before the first run)

1. **Camera recalibration.** Both main-playfield cameras currently
   report `calibration_stale: true`. Relative displacement within one
   run tolerates staleness (a run's own start/end delta doesn't need
   absolute accuracy); the absolute corner coordinates this campaign
   scores against (`leg_analysis.py`'s `DEFAULT_CORNERS_CM`, and the
   start/end bracket fixes below) do not. Recalibrate
   `arducam-ov9782-usb-camera` (not `ov9281` -- that one has been
   observed returning "no frame available") before anything else, via
   the aprilcam MCP `calibrate` tool or the daemon's own calibration
   flow. Confirm `calibration_stale: false` before proceeding.
2. **Tag re-registration.** Tag mount parameters (`tools/camlink.py`'s
   `MOUNTS`) do NOT survive a daemon restart -- an unregistered tag
   reads plausible but wrong (6.4 cm parallax + 3.6 cm lever error for
   vevov's tag, per `camlink.py`'s own module docstring). vevov is
   AprilTag **53**, tovez is **52**. Either construct `camlink.py`'s
   `Cam()` (its `__init__` calls `ensure_registered()` automatically)
   or explicitly re-register both tags via the aprilcam MCP tools if
   driving the camera directly rather than through `camlink.py`. Do
   this every session, not just the first time a daemon comes up.
3. **Floor vs. stand -- record explicitly, every run.** Runs for this
   campaign are over **RADIO** (`tour_capture.py --radio`), robot on
   the mat -- never USB-tethered on the bench stand. A stand run yields
   a complete, plausible-looking, worthless record: the wheels spin
   freely, the encoders integrate a phantom trajectory, and nothing in
   the resulting CSV distinguishes it from a real drive
   (`tools/robotlink.py`'s module docstring makes this exact
   distinction). Every evidence-template row below has a `floor` /
   `stand` field for this reason -- fill it truthfully even though this
   procedure only intends `floor` runs to be scored. A `stand` run that
   sneaks into the sample would look like clean data and silently
   corrupt the failure rate.
4. **First-move-after-boot probe.** Ticket 011-004's code-review
   finding identified one real, confirmed boot-specific special case:
   `NezhaMotorPort::writeRawDuty()`'s `kNeverWritten` sentinel
   (`nezha_port.h:68`) means the very first duty write of a power
   cycle skips slew-rate ramping, while every subsequent move that
   boot ramps normally. That finding was code-review only, not
   hardware-confirmed -- this is the step that would expose it if
   real. Immediately after a fresh power cycle (before any other
   move), run one identical leg twice in direct succession: e.g.
   `RUN:tour:wheels` for a single open-loop leg, or a single `RUN:tour:
   world` leg pulled out of the pose CSV as leg 1. Compare **leg 1 of
   the first tour after power-on** against **the same leg shape run
   again immediately after** (same commanded distance/heading, second
   attempt, same boot). Record both in the evidence template's
   `first-move` field. A first-move distance delta from the repeat that
   is larger than `leg_analysis.py`'s own 6 cm tolerance, when the
   repeat is on-target, is the specific signature ticket 011-004
   predicted (symmetric on both wheels, since each wheel carries its
   own independent sentinel -- so heading should still close even if
   this fires); anything smaller is noise-level and does not confirm
   the hypothesis.

### Main repetition loop

5. **Repetition count.** The 2026-08-20 warm campaign's own record
   (this issue's "What remains" section, `sprint.md`'s Architecture
   section) states a completion rate -- **~70% tours complete, with
   near-misses at the 60 mm threshold** -- but this repo does not
   preserve that campaign's raw run count (`N`), only the rate. Rather
   than inventing a precise number the record doesn't support, derive
   the minimum from the rate itself: at a ~30% per-tour failure rate,
   **n = 20 repetitions per tour type** (`RUN:tour:world` and
   `RUN:tour:robot` scored as separate 20-run samples, 40 runs total,
   4 legs per tour so >=80 legs scored per tour type) expects ~6
   failures at the OLD rate -- enough to see the straight-overrun vs.
   mid-leg-truncation split as a real distribution, not one anecdote.
   If sprint 006's fixes have genuinely dropped the rate, 20 runs with
   zero observed failures still only bounds the true rate at roughly
   <=15% (rule-of-three, 3/n) at 95% confidence -- **this procedure
   explicitly does not claim "zero failures in n runs" means "fixed";
   see the confirmed/ruled-out criteria below for the actual bar.**
   **n = 20 per tour type is this procedure's named minimum; a smaller
   sample never counts as a completed campaign pass.** More is better
   if bench time allows -- 20 is a floor, not a target.
6. **Exact commands, per run** (increment the `--out-prefix` suffix
   every repetition so nothing overwrites):
   ```
   uv run python3 tools/tour_capture.py --radio --tour world \
       --out-prefix .tmp/leg006_world_r01
   uv run python3 tools/tour_capture.py --radio --tour robot \
       --out-prefix .tmp/leg006_robot_r01
   ```
   (`r01` .. `r20`, or higher). `--radio` is mandatory per step 3 above
   -- there is no bench-stand variant of this campaign.
7. **Bracket every run with independent ground truth, start and end
   only.** Immediately before sending the tour command and immediately
   after the capture ends (per `tour_capture.py`'s own printed summary
   line), record, for BOTH the start and the end of the run:
   - An **overhead-camera fix**: read vevov's tag (53) position via the
     aprilcam tooling (`camlink.py`'s `Cam.frames()`, or the aprilcam
     MCP `get_tags`/`where` tools against `arducam-ov9782-usb-camera`).
     This is independent ground truth, external to anything the robot
     reports about itself. **Camera reads happen only at these two
     brackets -- never mid-tour.** This is not new latitude beyond the
     project's standing camera-is-diagnostics-not-control doctrine: the
     camera never steers a move in flight, full stop, and polling it
     mid-move is separately known to be actively dangerous over the
     wireless link (`tour_capture.py`'s own comment: mid-move polling
     measured cutting a leg from 197.5 mm to 0.3 mm on a *different*
     wire verb -- the lesson generalizes to "nothing request/reply
     shaped during a move," and the camera fix is exactly that shape).
   - A **live OTOS fix** (`RUN:fix`, over the same radio link): this is
     the ONLY thing that refreshes the telemetry `ox`/`oy`/`oh`
     columns -- confirmed by ticket 011-004's finding, that cache
     adopted a live fix verbatim (OCAL 6724:397:14490 -> telemetry
     columns 672,39,14490) and otherwise never updates during motion.
     Record the OCAL reply's own x/y/h.
   - The **encoder pose** at that same moment, read off the streaming
     telemetry (the pose CSV's own first/last rows already have this --
     no separate step needed for the encoder side).
   - **`i2cf`** (the I2C-fault-count telemetry column, present in both
     the 12-column POSE and 20-column FULL frames). It was observed
     climbing 60 -> 107 over several minutes, including while the robot
     sat at rest -- record it at both brackets of every run, not just
     once per session, so a climbing count is visible per-run rather
     than averaged away.
8. **Known gotchas -- build these into how the bracket is taken, not
   just into a footnote:**
   - **A second consecutive `RUN:fix` returns nothing** (observed
     twice on vevov). If the reply to a `RUN:fix` doesn't arrive, do
     NOT immediately resend `RUN:fix` -- that resend is itself the
     "second consecutive" case, and reading its silence as "the fix
     failed, try again" walks straight into a known no-op, not a
     retry. `robotlink.py`'s `Link.send_until()` already retries a
     dropped reply safely for commands where repeating is harmless
     ("the reply IS the delivery receipt"); for `RUN:fix` specifically,
     if a retry is genuinely needed, put a different command between
     the two attempts (e.g. a single `DIAG` read on USB, N/A over pure
     radio -- or simply wait one more full timeout window) rather than
     re-issuing `RUN:fix` back-to-back.
   - **Never blind-repeat a command that starts motion**
     (`robotlink.py`'s `Link.send()` docstring: a 3x-repeated `RUN:4`
     on vevov ran three consecutive 180-deg pivots, because MessageBus
     events queue rather than being deduplicated). `tour_capture.py`
     already uses `send_until()` for the tour-start command for this
     reason -- do not "help" by resending a tour command by hand if a
     run looks like it hung.
9. **Per-run validity gate -- apply before scoring, not after.**
   Cross-check camera vs. encoder vs. OTOS displacement using the
   brackets from step 7. Specifically:
   - Run `tools/leg_analysis.py` on the run's pose CSV (command below)
     and check the `otos_stale` column/flag it reports per leg
     (`detect_otos_staleness()`, ticket 011-002's own OTOS-staleness
     guard: OTOS displacement <=0.1 cm while the encoders moved
     >=2.0 cm over the same leg). **A run whose OTOS delta is ~zero
     while the encoders clearly moved has INVALID OTOS data for that
     leg and must be discarded from scoring, not counted as a failure
     or a pass.** This is the same freeze this issue's ticket 011-004
     finding and `leg_analysis.py`'s own module docstring already
     document on vevov's build -- expect to see it, and do not let a
     frozen-cache leg contaminate the failure-rate count either way.
   - Compare the two step-7 camera fixes' delta against the encoder
     pose's start/end delta (from the pose CSV's first/last rows). This
     is a whole-run sanity check, not a per-leg one -- `leg_analysis.py`
     always classifies a leg using the encoder-derived `believed` pose,
     never camera or OTOS (see its module docstring), so camera
     ground truth here is corroborating evidence for the run as a
     whole, not an input to the per-leg verdict. A camera/encoder
     mismatch bigger than `leg_analysis.py`'s own 6 cm distance
     tolerance on the FINAL corner is worth recording as a note next
     to that run's row, but does not by itself invalidate the run
     (only the OTOS-staleness gate above does that) -- do not silently
     average it away.
   - A run that fails the floor/stand check (step 3) is discarded
     outright, regardless of anything else it recorded.

### Scoring

10. **Per-leg logging.** For every valid run:
    ```
    uv run python3 tools/leg_analysis.py .tmp/leg006_world_r01_pose.csv \
        --out .tmp/leg006_world_r01_legs.csv
    ```
    (default `DEFAULT_CORNERS_CM` matches `test.ts`'s own four-corner
    world-tour geometry and applies to both `--tour world` and `--tour
    robot` captures, since both tours target the same physical square
    course -- only the on-robot guidance sensor differs, not the
    corners. Pass `--corners` explicitly if a bench operator finds
    that assumption wrong for a `--tour robot` capture.) Record, per
    leg: `classification` (`on-target` / `straight-overrun` /
    `mid-leg-truncation`), `distance_error_cm`, and `heading_error_deg`
    -- **both fields, always, even for an on-target leg.** The issue's
    own distinguishing signal is heading closing while distance
    doesn't; collapsing to one pass/fail bit destroys exactly the
    evidence this campaign exists to gather. The printed table and
    `--out` CSV already carry the `otos_stale` flag alongside each
    row's classification (step 9's gate) -- keep that column in the
    evidence template rather than dropping it once the gate has been
    applied.
11. **What ticket 011-003's and ticket 011-004's findings mean for
    what this campaign specifically watches for:**
    - **Ticket 011-003 (moveDeadline, RULED OUT)** -- host-tested
      clean, 59-74% margin on every leg shape the tours issue. This
      campaign's job re: that finding is narrow: confirm it stays
      ruled out, by checking whether any `mid-leg-truncation` leg's
      truncation point lines up suspiciously close to that leg's own
      `shims.cpp::startMove()` timeout (`max(distance/speed, yaw/
      yawRate) * 1000 + 1500` ms from the leg's start). If none do
      (expected, since the host test already found ~60%+ margin on
      real tick cadence), that is simply confirming evidence, not a
      new result. If one DOES land suspiciously close to its timeout,
      that is a genuine new signature -- record it explicitly and flag
      it for re-opening the moveDeadline finding against real hardware
      tick cadence, which the host harness cannot fully model.
    - **Ticket 011-004 (first-move-after-boot, code-review finding,
      NOT hardware-confirmed)** -- step 4 above is this campaign's
      dedicated probe for it. Beyond that one dedicated comparison,
      also watch the aggregate data: if failures cluster
      disproportionately on **leg 1 of a tour** (the first leg of the
      first run after a boot) relative to later legs across the whole
      sample, that is independent corroborating evidence for the same
      hypothesis, worth recording even outside the single paired
      comparison in step 4.

### Confirmed / ruled-out / new-signature criteria

Apply these to the aggregated, gate-passed (step 9) sample, separately
per tour type, at the end of the full >=20-run repetition set:

- **CONFIRMED FIXED:** at most 1 non-`on-target` leg across the entire
  >=20-run (>=80-leg) sample for that tour type, with no other
  evidence (step 11) pointing at a live mechanism. A single stray leg
  at this sample size is within the rule-of-three noise floor computed
  in step 5, not a pattern -- this bar is intentionally NOT "zero
  observed failures," because a genuinely-zero-observed-failures claim
  at n=20 does not distinguish "fixed" from "still ~10-15% broken and
  this sample got lucky." If confirmed fixed, close this issue
  directly (see Close-out below) and record the campaign's actual
  numbers (run counts, failure counts, both tour types) rather than
  just the verdict.
- **STILL PRESENT BUT NARROWED:** either (a) the measured failure rate
  has dropped meaningfully from the 2026-08-20 baseline's ~30% but
  exceeds the CONFIRMED FIXED bar above, or (b) one of the two
  classified failure modes (`straight-overrun` vs.
  `mid-leg-truncation`) has effectively disappeared (<=1 occurrence)
  while the other persists at a measurable rate. Either sub-case is
  real narrowing, not "no progress" -- record which.
- **NEW SIGNATURE:** any failure that does not fit the issue's own
  established shape -- e.g. heading error growing large alongside the
  distance error (the issue's signature is specifically "heading
  usually still closes"), a `mid-leg-truncation` landing on the exact
  `moveDeadline` boundary (step 11's flag), or a failure symmetric
  across both tour types but concentrated on leg 1 only (step 11's
  first-move corroboration). A NEW SIGNATURE does not retire the
  STILL PRESENT bucket -- both can be true of the same sample; record
  both.

### Close-out

- **If CONFIRMED FIXED** (both tour types, or with a stated reason if
  only one was run this sitting): close
  `intermittent-cw-pivot-abort-wheel-reversal.md` directly, recording
  the campaign's numbers (run counts per tour type, failure counts,
  which failure modes if any, the step-4 first-move comparison result,
  and the step-11 moveDeadline-boundary check result) in the closing
  note.
- **If STILL PRESENT or NEW SIGNATURE:** do not close this issue. File
  a sharpened successor issue that states plainly: what this campaign
  additionally ruled out (building on this issue's existing RETIRED
  THEORIES list above, plus ticket 011-003's moveDeadline result), and
  what it narrowed the remaining suspects to (e.g. "confirmed
  first-leg-only" or "confirmed straight-overrun persists,
  mid-leg-truncation gone") -- matching this sprint's own Success
  Criteria (`sprint.md`), which requires a campaign to leave the
  investigation narrower even when it does not leave it solved.

### Verification that this ticket needed no robot

Every step above is a written instruction for a future bench sitting.
No table, number, or claim in this section is a campaign result --
the table in the moveDeadline section above is ticket 011-003's own
host-test result (not this ticket's, and not from a robot), and every
other cited number (the ~30% baseline rate, the 60 mm/8 deg
tolerances, the `i2cf` 60->107 observation, the OCAL cache-adoption
numbers) is prior evidence this issue file already carried in, cited
by reference, not re-measured here. This ticket's own acceptance
criteria require exactly that -- confirmed true before marking this
ticket done.
