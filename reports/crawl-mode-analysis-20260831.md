# Crawl mode — is sub-deadband pulsed drive worth building?

**Date:** 2026-08-31 · **Author:** team-lead session (stakeholder request)
· **Status:** analysis + implementation proposal, no code changed

Stakeholder question: would a "crawl mode" — intermittent short
high-duty pulses layered under the normal control, ~10 Hz, so the robot
can move slower than its deadband — be valuable for (a) accurately
hitting stops during deceleration and (b) making turns at commanded
rates below the deadband? And if so, how should it be implemented
(the stakeholder's sketch: turn off the PID controllers, track the
error left by each pulse, correct it on the next)?

## TL;DR

1. **A crawl mode already exists in the kernel** — `crawlDuty()`
   (`src/core/diffdrive.cpp:890`), config field 14, `SET crawl_pulse`,
   default 0 = off. It is a Bresenham pulse-frequency dither applied to
   the final duty demand, downstream of the PID.
2. **It was live-tested once and lost.** MEASURED tovez 2026-08-29
   wheels-up, `captures/tovez-taper-20260829/variants.json` (writeup:
   `reports/tovez-taper-stall-20260829.md`): `crawl_pulse 0.09` made
   the end-of-leg stall *worse* — legs stopped 12–15 / 5–11 / 7–8 mm
   short at 100/150/200 mm/s vs the 6–9 mm baseline stall. The
   speed-floor fix (`SET speed_floor 893` = 70 mm/s) won the same
   sweep — no bump, final error within ±1.4 mm — and is now the
   shipped default (`src/shims.cpp:211`, confirmed on gopiv:
   `captures/gopiv-floor70-20260829/`, 0/6 restart bumps vs 6/6 stock).
3. So use case (a), accurate stops at the end of deceleration, **is
   already solved by a simpler mechanism, with measurements**. Crawl
   mode adds nothing there today.
4. Use case (b), rotation below the deadband, **is genuinely unserved**:
   the kernel's floor makes ~65–70 °/s the *slowest sustainable pivot
   rate*, and rotation targets under ~2–3° are deliberate no-ops
   (margins + `pivot_overrun`), so `tools/park.py` absorbs small heading
   residuals instead of executing them. A pulsed "nudge" mode is the
   plausible mechanism for executable 0.5–3° trims and sub-centimeter
   position nudges. **Qualified yes — but as a new, narrow step-pulse
   primitive, not by turning on the existing dither, and gated on a
   floor-truthed per-pulse characterization first.**
5. The stakeholder's "turn off the PID" intuition is right — the
   kernel's raw-duty mode already does exactly that — but "keep track
   of errors between motions" should stay encoder-ledger bookkeeping
   inside one nudge move (remaining counts, measured between pulses),
   plus the cross-move absorption `park.py` already does. No new
   cross-motion error store is needed.

## What exists today (source reading, with pointers)

**The dither.** `crawlDuty(duty, carry)` — `src/core/diffdrive.cpp:890`:
if `crawl_pulse` is 0 or |demand| ≥ `crawl_pulse`, pass through
unchanged. Otherwise accumulate `carry += |demand|/crawlPulse` and emit
0 until carry ≥ 1, then one tick at ±`crawlPulse`. Average duty equals
demand; pulses are one 24 ms kernel tick wide (cadence:
`src/shims.cpp:225`). It runs *after* the PID sum
(`diffdrive.cpp:664-667`), so the PID stays on and its position
reference (`PositionRef`, `diffdrive.cpp:856`) is the memory that
carries error across pulses. Reset on `resetAdaptiveState()`
(`diffdrive.cpp:767`).

**The floor.** `applySpeedFloor()` (`diffdrive.cpp:905`) scales any
sub-`vMin` speed command *up* to `vMin` (893 counts/s = 70 mm/s). This
is the current anti-deadband strategy: never command below breakaway.
It is why the crawl path rarely engages in normal moves — the floor
keeps the demanded duty above the dither threshold.

**Raw-duty mode.** `driveDuty()` → `kModeRawDuty`
(`diffdrive.cpp:528-540`): bypasses PID, floor, crawl, twist-hold, and
does not update the stall/deficit latches. E-stop and lease expiry
still force neutral (`diffdrive.cpp:482-486`). This is the "PID off"
substrate a step controller can sit on without touching the control
law.

**Write shaping between kernel and brick** (`src/platform/nezha_port.h:89-91`,
`nezha_port.cpp:242-320` — all measured-hazard guards, see the header
comment):

- min-write throttle 19 ms — a rising edge each 24 ms tick survives it;
- slew 25 %/tick — **a single-tick pulse cannot exceed ~25 % duty**
  (two-tick pulses can reach 50 %);
- exact-zero short-circuit — the falling edge (stop) is written
  immediately, never shaped, so pulse *end* timing is crisp;
- reversal dwell 100 ms on sign change — a **bipolar dither
  (zero-mean square wave superposed on the demand) is a non-starter on
  this hardware**: every half-cycle would eat a 100 ms dwell and risk
  the 0x46 encoder wedge the dwell exists to prevent.

## Why the one measured crawl test failed (analysis — UNVERIFIED, would
## be settled by the characterization below)

Three compounding reasons, all visible in the mechanism:

1. **Amplitude at or below breakaway.** The taper report puts tovez's
   working floor at 6–9 % duty for a *rolling* wheel and its
   population breakaway near 100 mm/s (~12 % duty equivalent;
   `reports/tovez-taper-stall-20260829.md`, "why speed_floor works").
   A 9 % pulse from *rest* is below static breakaway — pulses that
   don't break stiction deliver nothing, so dithering 6–9 % continuous
   duty into intermittent 9 % pulses strictly reduces delivered torque
   time. "The pulse dithering stalls the wheel earlier" is exactly
   this.
2. **Amplitude and threshold are the same knob.** `crawlPulse` is both
   the engage threshold and the pulse height. You cannot ask for
   "pulse at 25 % whenever demand falls below 10 %" — raising the
   pulse high enough to clear breakaway also widens the band of
   demands that get dithered, including demands the continuous path
   was already serving fine.
3. **One tick is a small impulse.** 24 ms at ≤25 % duty from rest,
   against stiction plus load, is a marginal kick. Width is not
   configurable today.

None of this says pulsed actuation can't work; it says *this* dither,
at *that* amplitude, was the wrong shape. A stick-slip stepper wants:
amplitude comfortably above breakaway, width 1–3 ticks, and a settle
period between pulses so each pulse yields one discrete, measurable
increment.

## Where crawl mode would actually pay

**Not leg endings.** The bump is gone (floor 70), final error is
±1.4 mm bench (tovez), 0/6 bumps (gopiv), and the aim-long "predict"
variant landed +0.3 ± 1.8 mm without any new mechanism
(`captures/tovez-taper-20260829/predict.json`). Tour closure error is
dominated by heading injected during the *legs*, not by terminal
positioning (vevov 2026-08-25, camera-truthed:
`clasi/issues/rotation-error-is-injected-by-the-legs-not-the-pivots.md`).
A crawl finish cannot improve what is already sub-2 mm.

**Micro-rotation is the real gap.** Arithmetic from shipped config
(analysis, not a measurement): floor 70 mm/s per wheel, effective track
114.2/0.952 ≈ 120 mm → slowest sustainable pivot ω = 2·70/120 ≈
1.17 rad/s ≈ **67 °/s**. A 2° trim at that rate is ~30 ms — about one
kernel tick — with a ~0.3° stop margin (4 counts,
`motion_engine.cpp:364`) and `pivot_overrun` 2.2 mm ≈ 2.1° subtracted
from every rotation target, which is precisely why sub-3° pivots
no-op and `park.py` absorbs residuals instead. Today the robot
*cannot execute* a 1–2° heading trim; it can only fold it into the
next move's plan. A nudge mode with, say, 0.3–1° per pulse-pair would
make final-heading parking a real capability instead of an absorbed
error. Secondary benefits: sub-centimeter position nudges below the
shortest reliable MOVE_X, robustness when a robot's breakaway drifts
outside the floor's narrow working window (100 mm/s floor already
overshoots — the window is only ~2:1 wide), and possibly a stiction
"warm-up" cheaper than net-zero warm-up moves (cold first move yaws;
see memory `cold-first-move-yaws`).

**How big is the prize?** Bounded. Pivot translation slip is already
only 0.09–0.50 cm per pivot and tour closure 1–4.5 cm (vevov baseline,
`reports/` + playfield rules). Better micro-trims sharpen parking
heading, not tour closure. This is a precision-parking feature, not an
error-budget fix — worth building only in its narrow lane.

## Proposed implementation (if pursued)

**Constraint first:** the kernel is a vendored, byte-synced copy of the
radio-robot firmware's control law (`src/DESIGN.md` §2 invariants) —
changing `crawlDuty()` means changing both repos and their fidelity
suite. The cheaper, better-layered home is the **MotionEngine**, which
is host-portable and already owns segments, margins, and deadlines.

**Shape: a settle-gated step controller ("nudge mode"), not a dither.**

- New engine entry point, e.g. `nudge(distMm, rotDeg, timeout)` with
  targets converted to counts exactly as `startSegment()` does.
- Loop per `serviceMove()` tick, in kernel raw-duty mode:
  1. If both wheels are settled (|velocity| below a rest threshold —
     the kernel already publishes per-wheel velocity in `Output`) and
     remaining error > margin: stage one pulse — `driveDuty(±A, ±A)`
     (straight) or `driveDuty(±A, ∓A)` (pivot), width `W` ticks, then
     back to zero.
  2. While not settled: stage zero, wait. Stiction stops the robot;
     each pulse is one discrete increment. Self-paced, this lands at
     roughly 4–10 Hz depending on settle time — the stakeholder's
     10 Hz intuition, but measured rather than scheduled.
  3. Remaining error is re-read from encoder counts between pulses —
     this *is* the "track the error and correct on the next pulse"
     ledger, and it needs no new state beyond the segment targets the
     engine already keeps.
  4. Terminate on margin, deadline, or a pulse budget (e.g. 40 pulses)
     — raw-duty mode has no stall latch, so the deadline/budget is the
     runaway backstop. E-stop still cuts through (kernel forces
     neutral).
- Direction changes pay the port's 100 ms reversal dwell once —
  correct behavior, already handled below us; the settle gate absorbs
  it naturally.
- Asymmetry handling: alternate or bias pulses per wheel from the
  measured per-wheel increments (left/right breakaway differ — the
  cold-yaw and taper sessions both show the left wheel weaker on
  tovez), rather than trusting a fixed 50/50 split.

**Config surface:** three new fields through the existing
`ConfigField`/`kFields` mechanism (`src/comms/wire_adapter.cpp:118`
area): `nudge_amp` (duty %, start ~22–25 % — at the single-tick slew
ceiling), `nudge_width` (ticks, 1–3), `nudge_settle_ms`. Per-robot
values later via `firmware_bake` like `pivot_overrun`.

**Routing:** `MOVE_X` (and `park.py`'s trim path) auto-routes to nudge
mode when the request is below what the floor can execute — roughly
|dist| < 15 mm and |rot| < 5° — so no new wire verb is required; the
existing sequenced `MOVE_X` semantics, ack/done channel, and deadline
plumbing all carry over.

**Host tests:** the engine is host-testable today; a fake motor with a
stiction model (no motion below a breakaway duty, quantized increments
above) pins the loop: pulses only when settled, ledger converges,
budget/deadline terminate, direction flip pays one dwell.

## Measurement gates before any code

Per the bench/playfield rules: stiction behavior wheels-up is *not* a
proxy for loaded stiction, so the deciding data must come from the
floor with the camera as truth.

1. **Per-pulse displacement map (the go/no-go gate).** On the floor,
   camera-truthed: for amplitude {15, 20, 25} % (and {35, 50} % at
   width 2) × width {1, 2, 3} ticks, ~20 pulses each from rest, per
   wheel, warm and cold: mean and sd of per-pulse displacement, and
   per-pulse yaw disturbance for paired straight pulses. **Accept** if
   some (A, W) gives a repeatable 0.3–2 mm increment with sd/mean
   ≲ 0.4; **reject** the whole feature if every cell is bimodal
   (nothing-or-lurch) — then the floor + aim-long approach stays the
   ceiling.
2. **Then** implement the engine mode + host tests, and validate on
   the floor: command 1/2/3° trims and 5/10 mm nudges, camera-scored.
3. Scheduling constraint: fw 1.20260829.1 is un-drivable over radio
   (`clasi/issues/fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`),
   and USB reaches only the bench. Floor characterization therefore
   runs on **vevov via the null daemon's lossless serial tap**
   (Pi Zero W on the robot, no cable drag) or on **tigez's
   v0.20260829.3 build** — or after the radio regression is fixed.

## Recommendation

File it as an issue, sequenced **after** the radio-wedge regression
(which blocks the floor work anyway): "nudge mode — settle-gated
pulse stepper for sub-floor moves, gated on a per-pulse
characterization." Do not turn on `crawl_pulse` as-is anywhere — the
one measurement we have says it hurts — and do not modify the vendored
kernel for this.
