# test — PXT testFiles (on-robot programs)

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:** stable

MakeCode/PXT `testFiles` (declared in `pxt.json`): TypeScript programs
compiled into a **deploy** build only — `tools/make_deploy.py` promotes
them into `files` in a scratch copy; in the repo they must stay
`testFiles` so they never run inside a student project that installs the
extension. They are smoke/bench programs driven by buttons and `RUN:`
wire commands, not assertion suites — the assertion-style coverage lives
in `tests/host/`.

The three programs are independent and **mutually exclusive** — each has
its own top-level code and button handlers, and they are never compiled
into the same flashable hex. `make_deploy.py` promotes `test.ts` by
default; `--program <basename>` selects another.

| file | what it is |
|---|---|
| **`test.ts`** | the playfield test program: the tours and the `RUN:` vocabulary. Its own header comment is the vocabulary reference. |
| **`testrig.ts`** | the zeguz OTOS validation rig: drum on M1 under the sensor, sensor on a servo, a numeric `RUN:<n>` vocabulary (probe/zero/stream/calibrate/servo/drum/lever-arm), driven by `tools/otos_bench.py`. One worker fiber does **all** I2C, per the shared-bus discipline in [`src/DESIGN.md`](../src/DESIGN.md) §7. |
| **`linefollow.ts`** | the smallest program that follows a line, using the PlanetX Trackbit reflectance array. |

Design decisions owned elsewhere are documented elsewhere: the tick
model and I2C single-fiber rule in `src/DESIGN.md`, the host-side tools
in `tools/DESIGN.md`. What follows is what `test.ts` and `linefollow.ts`
themselves need, and what their comments used to carry inline.

---

## 1. Build and flash

```bash
# the default: test.ts
uv run python tools/make_deploy.py --robot <name>
# another program (replaces test.ts in the hex)
uv run python tools/make_deploy.py --program linefollow.ts --robot <name>
mbdeploy deploy --remote <name> --hex .tmp/deploy-linefollow/built/binary.hex
```

`make_deploy.py` substitutes four placeholders into its **scratch copy**
of `test.ts`. The checked-in file keeps deliberately-fake values, so an
unsubstituted build reads as visibly wrong rather than silently
plausible. Changing the shape of any of these lines breaks the
corresponding regex in `make_deploy.py`, which exits with a message
naming it:

| placeholder | injected from | regex |
|---|---|---|
| `const BOOT_VERSION = "00.00"` | `pyproject.toml` | `_BOOT_VERSION_RE` |
| `const BOOT_ROBOT = "unknown"` | `--robot` | `_BOOT_ROBOT_RE` |
| `const BOOT_RADIO_LINK = false` | `--radio-link` / `connection.v6_radio_link` | `_BOOT_RADIO_LINK_RE` |
| `const otosBootId = diffDrive.otosBegin()` | `--no-otos` rewrites it to `= 0` | `_disable_otos_boot()` |

### Carriers are opt-in

The v6 radio link has been **off by default since 2026-08-29** so a
student's program can use MakeCode's own `radio` blocks for a joystick;
the WiFi link (Planet X Ai-WB2-12F on J1) is the untethered carrier now.
Neither names a channel or group here — `make_deploy.py` rewrites
`kChannel`/`kGroup` in `src/comms/radio_transport.h` from the board's own
config, so naming either in this file would put the whole fleet on one
address. A build with no `config/wifi_secrets.json` baked in keeps WiFi
off even though `enableWifiLink()` is called, so a bench without the
module loses nothing.

---

## 2. The tick model

Every move in `test.ts` is an explicit `startMove`/`startGoTo` plus a
`driveTick()` loop **in this file**, so the tick loop stays visible,
instrumentable test code rather than something the block API hides.

`tickToCompletion()` is the single choke point every `tickedMove()` /
`tickedGoTo()` leg runs through. It does three jobs:

1. tracks the largest gap between ticks (`maxGap`, reported as `GAP:`);
2. samples the OTOS every `OTOS_SAMPLE_TICKS` ticks (§4);
3. checks `aborted` and stops for real (§3).

**`tickWait()`, never `basic.pause()`.** Every `onRun()` handler runs
*on the protocol fiber itself* (nested, reentrant dispatch — see
`src/comms/protocol.h`), so a `basic.pause()` anywhere in a handler's
call tree stops that same fiber's wire-servicing loop for the pause's
full duration and leaves `PING`/`ESTOP`/`RUN:abort` unanswered.
`driveTick()` self-paces to one kernel cycle (`Config::cyclePeriod`,
24 ms) and runs the wire's service hook exactly once per call whether or
not a move is active, so looping it against the wall clock waits the
same real duration while still servicing the wire.

The same reasoning removed every per-leg `basic.showNumber()` /
`basic.showString()` from inside a job: they blocked the protocol fiber
for the duration of the flash. The `DBG:leg=`/`DBG:corner=`/`OCAL:c<N>`
wire lines are the non-blocking substitute — machine-parseable, and
strictly more informative. An operator with no host connected loses the
on-robot LED counter; that is the accepted trade.

For the same reason the **boot banner is deliberately last** in
`test.ts`: handler registration is synchronous and near-instant, while
`showIcon`/`showString` block. A `RUN:` line landing in the first
couple of seconds after boot needs its handler already registered to be
dispatched at all. (The protocol fiber's own wire-level `HELLO` reply
runs on a separate CODAL fiber and is unaffected either way.)

---

## 3. Job lifecycle and abort

Every motion-issuing job is:

```ts
if (touring) return
beginJob("<VERB>")
...
endJob(jobReason())
```

`beginJob()` resets `aborted`, selects the shaping profile, resets the
gap tracker and records the verb. `endJob()` emits `GAP:` then the
terminal `<VERB>:end:<reason>` line and clears `touring`. The `touring`
guard stays at the call site because several jobs check
`worldReady()`/`worldTrackingReady()` *between* the guard and
`beginJob()`, and that ordering matters.

`jobReason()` returns `abort` > `estop` > `ok`: an abort reflects the
operator's own intent, so it outranks a coincident e-stop. **Call it
once, at the `endJob()` site**, and pass the result straight in — sprint
031's session-a capture (tovez, 2026-09-04) found a wire-reported
`reason=` can be poll-timing dependent when a caller recomputes it after
the fact.

This pair replaced a per-handler hand-rolled copy of the same thing that
**most handlers skipped**. The failure it fixed: a stale `aborted` left
by an earlier `RUN:abort` silently truncated the very next
`RUN:pivot`/`straight`/`face`/`cal`/`arc` to one tick, and that handler's
own terminal line reported it as a normal end. Five newer tours plus
`RUN:cal` also applied no shaping profile at all, silently inheriting
whatever the previous command left set.

### Abort scope

`RUN:abort` and `RUN:clearestop` bypass the RUN queue — `protocol.cpp`
dispatches them reentrantly, nested inside whatever handler is mid-tick,
on the same fiber. So neither guards on `touring`, and both must stay
flag-only and non-blocking.

`RUN:abort` sets the flag **and** calls `diffDrive.stopMove()`.
That second call is what makes an abort reach a move already in flight:
`stopMove()`'s native body (`shims.cpp`'s `endMove()`) stops
unconditionally with **no ownership check**, so it ends whatever tick
loop is currently active regardless of which file started it —
including `goToWorld()`'s own loop in `src/blocks/world.ts`, which has
no visibility into `aborted` at all. Without it, an abort during a
`goToWorld` leg could only prevent the *next* leg from starting. The
`if (aborted) break` after each leg is therefore only about not planning
a further leg.

Every `if (aborted) break` sits **before** the following `logFix()` on
purpose: an abort must not emit a plausible-looking `OCAL:` fix for a
corner the robot never reached.

`clearestop` is its own verb and is never folded into `STOP`, which is
issued reflexively and must never silently disarm a safety latch. It
exists because `ESTOP` had no wire-level clear: once latched, every
motion verb was silently ignored and the only recovery was a power
cycle.

These properties are source-pinned by
`tests/host/test_run_abort_source_pin.py` — including a count assertion
that `aborted = false` appears exactly twice in `test.ts` (the
declaration and `beginJob()`'s reset), so a handler that starts
hand-rolling its own reset fails the build.

---

## 4. OTOS: bring-up, sampling, and the lever arm

**Bring-up runs on the MAIN fiber at boot.** The hazard is the No-ACK
case: an I2C transaction that neither completes nor errors spins CODAL's
`waitForStop()` forever and wedges the board with no recovery
(`clasi/issues/high/first-i2c-command-can-wedge-the-program-with-no-recovery.md`).
Doing it at boot keeps that risk off the `RUN:` path, where it once
bricked two robots. Capture:
`captures/otos-run-handler-i2c-hang-20260828.md`. The boot line emits
the product id so it can be checked against the value that produced it
rather than trusted on its own.

**Sampling happens inside `tickToCompletion()`, not a background fiber.**
`otosGet()` is a cache-only read (`wire_adapter.h`), so without
something periodically calling `readWorld()` the telemetry's `ox/oy/oh`
sit at `(0,0,0)` forever — MEASURED vevov 2026-08-28: 153 frames of
`ox=oy=oh=0` while the encoders logged 246 mm of travel. This used to be
a free-running `control.inBackground` fiber at 10 Hz with no mutual
exclusion against the bus, where an OTOS transaction could land inside
the Nezha encoder's select→read settle window on whichever *other* fiber
was ticking and destroy that sample (the Phase-F signature,
`src/platform/nezha_port.cpp:376-380`). Sprint 030 ticket 001 moved it
onto the ticking fiber; `OTOS_SAMPLE_TICKS = 4` at the kernel's 24 ms
cycle is 96 ms, the closest whole-tick match to the old 10 Hz rate.
`otosRead()`/`otosBegin()` also now take the kernel's `BusGuard`, so
even a call from a genuinely different fiber is serialized — the
tick-loop sampling is belt-and-braces on top of that.

**Known behavior change from that move:** telemetry's `ox/oy/oh` update
only while something is actively ticking, not continuously while the
robot sits idle. That is the ticket's own explicit trade
(`enforce-the-one-fiber-i2c-invariant.md`).

### The lever arm

`armX`/`armY` are the sensor's position relative to the **centre of
rotation**. MEASURED vevov 2026-08-28 (`RUN:cal` + `tools/otos_levercal.py`),
after the chassis rebuild that moved the centre of rotation and
invalidated the earlier figure. Capture:
`captures/otos-run-handler-i2c-hang-20260828.md`.

Method: with `applyArm()` not yet run the OTOS reports the *sensor's*
own path, so eight 45° in-place pivots trace a circle of radius `|arm|`
about the centre; a least-squares fit of `otos_i = C + R(theta_i)·arm`
over 9 rest readings gave **x −52.7 mm, y −1.2 mm**, residuals 1.4 mm
median / 1.9 mm max. **Independent cross-check:** the overhead camera's
tag-53 mount solved to 53.4 mm behind the centre the same day, by the
same fit shape but a different instrument. Two sensors agreeing to
0.7 mm is what makes this trustworthy rather than merely fitted.

`armYaw = 0.89` is **UNVERIFIED** — the pivot fit constrains the arm's
*position*, not the sensor's angular mounting. Carried over from
2026-08-21. Re-measure by comparing OTOS heading against camera heading
at rest across several headings.

**Why `worldReady()`'s fast path still arms the sensor:**
`worldTrackingReady()` only asks whether the chip answers (`otosGet(7)`
→ `connected_`), and *any* earlier `otosBegin()` — a bare `RUN:probe` is
enough — makes it true. An un-armed sensor reports its own path, so
every in-place pivot injects a phantom `2·|arm|·sin(θ/2)` of
translation. MEASURED BUG, vevov 2026-08-25, against overhead-camera
truth: four uncorrected corners cost **58 mm** of tour closure that the
robot scored as 22 mm. The guard is `armApplied`, not the chip's state:
`otosBegin()` does not clear `OtosPort`'s offset members, so once
applied the arm survives a re-begin, and the flag only stops the `ARM:`
line being re-emitted.

`RUN:fix` calls `worldReady()` before `logFix()` for the same reason —
`logFix()` calls `readWorld()` directly, so a bare `RUN:probe` →
`RUN:fix` used to report the sensor's position with no arm applied, off
by up to 38.2 mm and silently plausible. That is exactly the reading
that sent a 2026-08-25 bench session chasing a drivetrain fault that did
not exist.

**`tourWorld()` deliberately does NOT call `worldReady()`** — that
re-inits the sensor when it looks unready, and `begin()` zeroes the
position registers, which would throw away the pose the host just seeded
from the camera and send the robot off from a phantom origin. It checks
`worldTrackingReady()` and emits `OERR:not-seeded` instead.

Neither `worldReady()` nor `tourWorld()` shows a `"NO"` glyph on
failure: both run *before* `beginJob()`, so nothing has been reported
done yet and a blocking display would stall the wire with no terminal
line to justify it. The `OERR:` line carries the failure to any bench
tool watching the log.

---

## 5. Shaping profiles

`beginJob()` selects one by verb name. `RUN:goto` gets
`closedLoopProfile()` — a leg re-measured and re-planned every hop can
afford faster shaping. **Everything else gets `openLoopProfile()`**,
where every error is permanent.

Floors and `stop_distance` are per-robot (the deploy bake, or
`set config`) and never per-profile, so they stay out of both functions.
`setDefaultSpeed`/`setDefaultYawRate` are a separate mechanism from
`setLimits()`'s `MotionLimits` shaping — the `move()`/`goTo()` blocks'
own default cruise speed and yaw rate.

`RUN:cal`, `RUN:pivot` and `RUN:face` each override one of the two
defaults for their own job, on top of the profile. The overrides are
explicit rather than inherited, so a bare `RUN:pivot` with no preceding
`RUN:turnrate` is still deterministic.

### Why `openLoopProfile()` is `setLimits(400, 400, ...)`

**CORRECTED 2026-09-05** (sprint 031 ticket 020) — accel/decel are
400/400, the **fleet default**, not the 800/300 this was previously
argued down to. MEASURED tovez,
`captures/session-b-20260905/gain-sweep-20260905/`:

| setting | captures | n | mean \|dh\| | max |
|---|---|---|---|---|
| **400/400** | `accel400/` + `accel400b/` | 8 | **1.06°** | 2.55° |
| 800 | `accel800/` + `accel800b/` | 8 | 1.35° | 3.45° |
| 300 baseline | `discriminator-20260905{,-v2}/` | 8 | 3.62° | 7.61° |

The 800 result was real — it beat 300 — but was never checked against
the actual fleet default until the second sweep. **Root cause of the
whole episode:** this function had been left at `setLimits(300, 300,
...)` by a live `RUN:straight:8` check that was never cleared, so every
RUN-driven gate ran on 300/300 instead of the compiled 400/400 default
that student block programs actually get. *A RUN verb must not leave the
robot in a worse shaping profile than the default for every later
`MOVE_X`.*

The **mechanism** for accel's effect on the breakaway-yaw defect is
still UNVERIFIED at any setting: `docs/sprint-031-postmortem.md` §3a's
ramp check shows the physical wheel ramp does not track any commanded
ceiling (759–955 mm/s² at 300 vs 873–894 at 800 — the drivetrain already
outruns every ceiling tried). The literal agrees with
`radio-robot-lib/config/robots/tovez.json`'s
`geometry.firmware_bake.accel`, whose provenance note carries the full
history.

---

## 6. The figures

The three rectangle tours start **on the northeast orange dot facing
west** and run counter-clockwise: NE → NW (100 cm) → SW (60) → SE (100)
→ NE (60). The dots are A1-centred, +x east, +y north — NW (−50, 30),
NE (50, 30), SW (−50, −30), SE (50, −30).

- **`tour:robot`** — "robot-relative" means the tour never needs a world
  *position*: the rectangle is expressed in a frame anchored where the
  robot started. It does **not** mean flying blind — heading comes from
  the IMU every leg, because a gyro heading is far better than one
  differenced out of wheel encoders, and a heading error is what rotates
  an entire rectangle. Every leg is planned as one body twist from the
  current pose and current measured heading; a few degrees of residual
  after a turn is never corrected with another turn, it is absorbed by
  curving to the destination, which costs nothing and avoids a second
  pivot's settle time and overshoot. `startGoTo()` owns the
  pivot-vs-blend split and short-arc wrap internally.
- **`tour:world`** — the sensor is consulted *before every move*, so each
  leg is planned from where the robot actually is. The move itself still
  runs on encoder odometry; the sensor never steers it in flight. No
  seed: the host has already seeded the true world pose (`RUN:seedxy`),
  so the robot can start anywhere on the field.
- **`tour:wheels`** — open loop, and the **only** one meaningful on the
  bench stand, where the wheels are off the ground and neither the IMU
  nor the OTOS sees the body move.

`RUN:straight` is **wheels only**: deliberately no `worldReady()`, no
`seedPose()`, no `logFix()`, and no steering. Consult the sensor and you
are testing the sensor instead. It reports the encoder pose, where `x`
is forward travel and `y` is sideways drift — `y` is the interesting
number, because a perfectly straight run has `y = 0` and nothing in that
path corrects it.

### ARC SEGMENT SIZE IS NOT FREE

`MotionEngine::moveX()` splits any move with a nonzero distance and
`|yaw| >= kTurnFirstAngle` (~50°) into a **pivot then a straight**. An
arc asked for in 90° pieces therefore comes out as a **square** —
measured 2026-09-01: 90° pieces drew a square, 45° pieces drew the
circle. Every `arcSegment()` call in `test.ts` is 45° for that reason,
and `tests/host/test_run_tour_programs.py` pins it by reading
`kTurnFirstAngle` out of the C++ header rather than hardcoding it.

The same threshold is why **`RUN:arc` needs `|deg| >= 50` to mean
anything**: below that it is a single blended move and never exercises
the split-move path at all. Its shape (`move(20, deg)`) is the one that
measured the sprint 015 ticket 005 phase-handoff defect (`twistRef_`
unwinding its own pivot at the phase 1 → phase 2 handoff) and its fix.
Firmware trusts the caller and does not enforce the bound.

### Sizing

- **`diamond`** is smaller than `square` because a square of side S
  turned 45° spans `S·√2` in **both** axes: 45 cm sides span 63.6 cm,
  which is what fits the field's tight axis.
- **`circle`** driven CCW from a point on its own circumference puts the
  centre 90° to the left, so it spans ±r across the start heading and
  0…2r along it.
- **`snake`** advances `8r` = 100 cm at its defaults **perpendicular** to
  the start heading — the first half circle turns the robot 180°, so
  progress is sideways. Stage it facing the short axis.
- It is **not a spline**, and the verb used to claim it was. A spline is
  a fitted curve followed with pure pursuit; the *host* drives that one,
  because it needs the sampled path and a steering loop. `RUN:spline` is
  pinned as absent.

`tests/host/test_run_tour_programs.py` also simulates every `.tour` file
against `tools/field.py`'s usable half-extents, in either orientation,
so a figure cannot pass its sizing gate here and still be refused by the
geofence every driving tool pre-flights against.

### `RUN:arc`'s trajectory dump

The heading trajectory is **not** read live off the wire. A
request/reply round trip *during* a move is dangerous — `shims.cpp`'s
`probe()` doc comment records a 197.5 mm leg collapsing to 0.3 mm — so
`tickArcSampled()` samples `diffDrive.heading()` once per tick on the
ticking fiber and `emitTrajectory()` dumps it as `ARCT:` lines after the
move, the pattern `probe()`'s own comment prescribes. It is a separate
tick loop from `tickToCompletion()` on purpose, so every other caller of
the shared one is untouched.

A 180° arc runs ~2.8 s at ~24 ms/tick (~120 ticks); `ARC_SAMPLE_CAP =
200` is headroom above that and stops the array growing unbounded if a
tick stall makes a move run long. `ARCT:meta:<count>:<capped>` comes
first — read it before trusting the chunk lines' count.
`ARCT_CHUNK = 20` centidegree ints per line is a wide margin under the
wire's 240-byte line cap (`kMaxLineBytes` in both transports, and
`Protocol::emitLine`).

### Radius arguments are validated (BT-22)

`circle`, `infinity` and `snake` take their radius through
`runArgOr(0, <default>, 0)`, whose `minExclusive = 0` bound rejects an
unparseable radius (`RUN:circle:abc`) and a non-positive one
(`RUN:circle:0`, `:-5`) alike as `NaN`. Both are refused outright with
an `ARGERR:` line rather than silently substituting 0 or the fallback:
these are student-facing verbs, and a typo that quietly ran eight
pivots-in-place used to look like a normal, if odd, completion. Every
other `runArg()` call site (`pivot`, `face`, `arc`, `straight`,
`seedxy`, `turnrate`) is deliberately left on plain `runArg()`;
`tests/host/test_run_arg_or_contract.py` pins both halves.

---

## 7. `RUN:face` closes its loop on the robot

Bouncing "measure, turn, measure" over the wireless link made the host
hunt: every round trip added latency and a fresh chance for a lost
command, so it oscillated instead of converging. On-device against the
robot's own IMU heading it settles in one or two passes with no radio in
the loop. `goToWorld` controls position only, and the tours start facing
west, which is why this verb exists at all.

---

## 8. `linefollow.ts`

Sensor: **ElecFreaks PlanetX Trackbit**, a four-channel reflectance
array on **I2C address 0x1A**, mounted ahead of the wheels with channel
0 on the robot's left. Protocol as in `PlanetX_Basic.Trackbit*` of
[pxt-planetx](https://github.com/elecfreaks/pxt-planetx)'s `basic.ts`:
write a register byte, read one byte back. **Register 4** is the line
bitmask, bit `i` set when channel `i` sees the line — that one byte is
all the follower needs.

Steering is proportional: yaw rate = `kp · error`, in deg/s with CCW
positive, so a line to the left turns the robot left. With nothing seen
it turns toward the side the line was last on, at 40% speed, and gives
up after 1.5 s.

Everything lives in a `namespace` so the file can sit next to `test.ts`
in the repo type-check without name collisions; PXT runs a namespace
body at start-up exactly like top-level code.
