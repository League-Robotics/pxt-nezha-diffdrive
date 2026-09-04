# Motion profile unification — one shaper, one floor, one arrival rule

**Owner:** Eric Busboom · **Status:** proposal, 2026-09-03 · **Source:**
[code review 2026-09-02](../code-review/2026-09-02/review.md) §1 (MK-01…MK-07)
and §4 (CO-01, CO-02). **Scope:** `src/motion/`, `src/core/diffdrive.*`
(four small patches), `src/shims.cpp` config surface, `test/test.ts`
profiles, host tests. Does not touch the wire grammar, the ports' bus
code, odometry (its own design) or the block palette's shape.

Every number below marked MEASURED comes from
[`profile_probe.cpp`](../code-review/2026-09-02/raw/profile_probe.cpp)
run against the real kernel and engine; "predicted" numbers are what the
design should produce and are to be verified by the same probe before
any hardware run.

---

## 1. The problem in one page

Three objects each decide how fast the wheels should be going, and none
of them knows what the other two decided.

| who | what it decides | where |
|---|---|---|
| `MotionEngine::serviceMove()` | a scale in [floor, 1] on a full-rate command: time ramp *or* accel integrator up, `remain/taper` *or* `sqrt(2a·remain)` down, its own floor (25 % / 12 % of cruise), optional jerk rounding, optional profile-exit | `motion_engine.cpp:500-862` |
| `DifferentialDrive::applySpeedFloor()` | raises any nonzero command below `vMin` (70 mm/s) to `vMin`, both wheels, ratio preserved | `diffdrive.cpp:905-917` |
| `DifferentialDrive` twist-hold | integrates a reference from the command *before* the floor and trims the wheels toward it | `diffdrive.cpp:589-611` |

And a fourth thing that is not an object at all — the stage→land→move
pipeline — adds one tick of latency between "the engine decided" and
"the wheel did", which nothing models.

What that costs, MEASURED on ideal wheels (so every hardware number is
worse):

- Every pivot coasts 1.5°/tick past its target after completion is
  detected; pivots end +0.8…+2.6° long. The fleet calibrates this away
  per robot as `pivot_overrun` (2.2 mm/wheel ≈ one tick at 70 mm/s).
- In every crawl below ~200 mm/s cruise the twist servo fights the floor:
  −11 % reverse duty at the end of a pivot, a 45° arc landing 15 mm long.
- The engine's floor knobs are inert at every tour speed (25 % of 200 =
  50 < 70), so `setTaperFloors`, `SET dist_floor`, and both `test.ts`
  profiles change nothing they claim to change.
- The first tick of every move steps to max(70 mm/s, 25 % cruise) in
  every mode including the jerk-limited one; the last tick is a hard
  neutral from the crawl; `set wheel speeds` steps 0→200 mm/s in one
  tick. Jerk is bounded only in the middle of a move, where it never
  mattered.
- Thirteen shaping knobs, two interleaved algorithms, five mode forks in
  one 360-line method.

The fix is not a fourteenth knob. It is deciding who owns the question
"what should the wheels do this tick" and taking it away from everyone
else.

---

## 2. Goals and non-goals

**Goals**

1. One object computes the commanded wheel velocity every tick, for every
   entry point (`move`, `goTo`, `wheelsX`, `wheelsV`, `driveTwist`, the
   wire's six verbs). No other object reshapes it.
2. Floors and ceilings are expressed in the axis's own units — mm/s for
   travel, °/s for rotation — in one place.
3. A move ends when the plan says it is about to arrive, not after the
   encoders say it already has. The per-robot `pivot_overrun` constant
   goes away; a measured *stop distance* replaces it with a physical
   meaning.
4. Jerk is bounded at the start and end of a move, and on continuous
   drive, not only mid-profile.
5. The kernel becomes a wheel-velocity servo and nothing else: it tracks
   what it is given, it does not decide how fast to go.
6. Fewer knobs, one algorithm, host-testable tick by tick.

**Non-goals**

- Retuning `ki`, adding `kp`, or changing the feed-forward gain. Those
  are bench work on top of this; the design leaves the control law's
  gains alone and only fixes its reference handling.
- Odometry ownership (review CO-03). This design removes the engine's
  need for the rebase-epoch guard; the `Odometry` object is a separate
  proposal.
- The wire grammar. Field *names* change; verbs do not.
- Supervisory re-solve for `goTo` (still single-shot, per motion-api §3.5).

---

## 3. The principle: three questions, three owners

```
"What should the wheels be doing this tick?"   -> MotionEngine  (+ VelocityShaper, Segment, MotionLimits)
"How do I make the wheels do that?"             -> DifferentialDrive (the kernel)
"How do I say that to the brick safely?"        -> NezhaMotorPort
```

The kernel today answers the first question in two places (`vMin`, the
twist reference) and the engine answers it in two mutually-unaware ways
(legacy, shaped). After this design:

- The engine issues a **fully shaped** `(velocity, twist)` every tick.
  Floors, ceilings, accel, decel, jerk, and the arrival decision are all
  applied before the kernel ever sees the number.
- The kernel's `vMin` is **0** in the fleet bake (the floor has moved up),
  and its twist reference integrates **exactly the command it was given**
  (a bug fix that stands on its own).
- The port keeps its per-tick duty slew and reversal dwell as
  *hardware protection*, documented as such, sized so the shaper's limits
  are always the binding ones.

This matches motion-api.md §4's own statement — "the profiler plans one
scalar; each wheel commands λ·u_w" — more faithfully than today's code
does. It diverges from §4's list of kernel features in one place: the
"ratio-preserving speed floor" moves from the kernel to the profiler.
The ratio is still preserved (λ scales both wheels); the *policy* of
when to floor is now made by the object that knows which axis is
dominant and in what units. That divergence is recorded in §12.

---

## 4. The objects

Naming follows `.claude/rules/no-units-in-identifiers.md` and the
kernel's own style: an identifier names the quantity, the unit is a
trailing `// [unit]` comment on its declaration. The existing
`aAccelMmS2_`/`defaultCruiseMmS_` names in `src/motion/` and `shims.cpp`
are the counter-example and are renamed by ticket 3. JSON bake keys keep
`radio-robot-lib`'s convention (`stop_distance_mm` beside the existing
`pivot_overrun_mm`).

### 4.1 `MotionLimits` — a value object, the only place limits live

```cpp
// src/motion/motion_limits.h -- host-portable, <cstdint> only.
struct MotionLimits {
  // Rates: per robot, bench-measured; defaults are the fleet bake.
  float accel = 400.0f;        // [mm/s^2] dominant-wheel accel ceiling
  float decel = 400.0f;        // [mm/s^2] dominant-wheel decel ceiling (braking plan)
  float jerk = 0.0f;           // [mm/s^3] 0 = no jerk rounding (first-order shaper)
  float vMax = 250.0f;         // [mm/s] dominant-wheel cruise ceiling
  float omegaMax = 0.0f;       // [deg/s] pure-turn rate ceiling; 0 = none

  // Floors: below these the drivetrain does not move, so the profile
  // never commands less while not yet arrived.
  float vFloor = 70.0f;        // [mm/s] MEASURED tovez/gopiv 2026-08-29 (the old vMin)
  float omegaFloor = 20.0f;    // [deg/s] UNVERIFIED; sized so one tick is ~0.5 deg

  // Arrival.
  float lag = 0.0f;            // [s] drivetrain response lag: the wheel follows
                               //   a command change about this much later, so
                               //   it coasts ~v*lag past any command. 0 until
                               //   measured (see 10.2); 0.08 is the order the
                               //   host model needed to reproduce tovez (6.3)
  float stopDistance = 0.0f;   // [mm] per-wheel coast that does not scale with
                               //   speed (brick latency at zero); replaces
                               //   pivot_overrun. 0 until measured (see 10.2)
  float arriveDist = 1.0f;     // [mm] distance-axis arrival window
  float arriveYaw = 0.3f;      // [deg] pure-turn arrival window

  // Every setter is "positive, else keep", as today.
};
```

Responsibilities: hold the numbers; convert between axis units on
request (`omegaFloorAsWheelSpeed(b) = omegaFloor·π/180·b/2`, same for the
ceiling); validate. Nothing else. It is settable as a block from the
wire (`SET accel …`) and from a block program (`set config …`), and it is
what `test.ts`'s two "profiles" become — two `MotionLimits` literals.

Retired by this object: `distTaper_`, `yawTaper_`, `distFloor_`,
`turnFloor_`, `rampMs_`, `brakeFrac_`, `plateauMinS_`, `profileExitMmS_`,
`pivotOverrunMm_`, `maxYawRateDegS_` (renamed), `aAccelMmS2_`/`aDecelMmS2_`
(renamed), and the kernel's `vMin`. Thirteen fields become nine, and
none of them is inert at any speed.

### 4.2 `VelocityShaper` — the one per-tick scalar

The single function that answers "given where I am and where I want to
be, how fast should the dominant wheel be commanded this tick". It is
stateful only in the two values a rate limiter needs (last commanded
speed, last commanded acceleration).

```cpp
// src/motion/velocity_shaper.h -- host-portable.
class VelocityShaper {
 public:
  struct Step {
    float vCmd;      // [mm/s] what to command the dominant wheel this tick
    bool  arriving;  // true when this is the LAST nonzero tick (see 6.3)
  };

  void reset();      // at every segment start: v = 0, a = 0

  // remain < 0 means "no displacement bound" (continuous drive).
  // floor/cap are already converted to dominant-wheel speed for THIS axis.
  Step advance(float target, float remain, float floor, float cap,
               float dt, const MotionLimits& lim);  // [mm/s] [mm] [mm/s] [mm/s] [s]

  float velocity() const;      // [mm/s] last commanded
  float acceleration() const;  // [mm/s^2] last commanded
 private:
  float v_ = 0.0f;  // [mm/s]
  float a_ = 0.0f;  // [mm/s^2]
};
```

`advance()` is §6.1 verbatim. It does not know about counts, wheels,
kernels, or phases. It is the thing the probe's `profileStats()` should
be run against directly, and the thing every shaping test in
`tests/host/` should target.

### 4.3 `Segment` — one constant-ratio plan and its progress

Replaces `MoveState`. Owns what a segment *is* and how far along it is;
does not decide speeds.

```cpp
struct Segment {
  enum class Axis : uint8_t { kDistance, kYaw };
  float distTarget = 0;   // [counts] signed mean-axis target
  float yawTarget = 0;    // [counts] signed half-differential target
  float cruise = 0;       // [mm/s] caller's ceiling before limits
  Axis  dominantAxis = Axis::kDistance;
  float dominant = 0;     // [counts] |target| on the dominant wheel

  // Origin: captured LAZILY on the first service() call after start(),
  // never at start() -- see 6.5 for why this retires the epoch guard.
  bool  originPending = true;
  float posLeft0 = 0, posRight0 = 0;  // [counts]

  // Pending second phase (pivot-then-straight).
  bool  hasPending = false;
  float pendingDistance = 0;  // [mm]

  uint32_t deadline = 0;      // [ms] the caller's timeout backstop
  bool active = false;

  // Pure functions over kernel Output:
  float remaining(const Output&) const;   // [counts] dominant axis, signed toward target
  bool  wrongWay(const Output&) const;    // yaw progress against the target
  float progress(const Output&) const;    // [1] 0..1
  bool  pureTurn() const { return yawTarget != 0 && distTarget == 0; }
};
```

The `(uLeft, uRight)` ratio of motion-api §4 is implied by
`(distTarget, yawTarget)`: `velocity = distTarget/dominant · vCmd`,
`twist = yawTarget/dominant · vCmd`, exactly as `startSegment()`
computes `velCmd`/`twistCmd` today, but recomputed from `vCmd` each tick
instead of stored as a full-rate pair scaled afterwards.

### 4.4 `MotionEngine` — the orchestrator

Keeps its public surface (the two primitives, four reductions, `goToW`,
geometry, `isMoveActive`, `progress`, `endMove`, `settleToRest`). Loses
every shaping field and both shaping algorithms. Gains one continuous
"hold" state so `wheelsV` is shaped too.

```cpp
class MotionEngine {
 public:
  // ... geometry, primitives, reductions as today ...
  MotionLimits& limits();                 // the ONE settable shaping surface
  bool service();                          // one tick: segment OR hold
 private:
  // exactly one of these is live; a new command replaces both
  Segment seg_;
  struct Hold {
    bool active;
    float v, twist;   // [mm/s] [mm/s] the target the shaper slews toward
    uint32_t until;   // [ms] the caller's duration deadline
  } hold_;
  VelocityShaper shaper_;
  MotionLimits limits_;
  // ...
};
```

Responsibilities, stated as what each entry point now does:

| entry | today | after |
|---|---|---|
| `wheelsV(l, r, ms)` | one `kernel.drive()` held on the lease; unshaped | sets `hold_` (target v, twist, deadline); `service()` slews toward it with the shaper every tick and issues `drive(…, 500 ms)`; the kernel lease still backstops an abandoned hold |
| `wheelsX(l, r, cruise, ms)` | one dead-reckoned `drive()` | a `Segment` like `moveX`, closed-loop on encoders (the spec allows this: "timeout is a required backstop, not the stop condition") |
| `moveX`, `goToR`, `goToW` | `startSegment()` + `serviceMove()` | build a `Segment` (split rule unchanged: `|rotation| ≥ 50°` with distance → pivot phase then straight phase); `service()` runs it |
| `serviceMove()` | 360 lines, two algorithms | `service()`: ~40 lines, §5 |
| `endMove()` | neutral if a move was active | neutral + `shaper_.reset()` + clear both states |

`service()` is the whole per-tick behaviour and is written out in §5.

### 4.5 `DifferentialDrive` — the kernel, four patches and one config change

The kernel stays a vendored copy of `radio-robot-elite/src/firm/diffdrive/`
(today's diff against upstream is comments plus `cycleGapCount`). This
design needs four small, independently justifiable changes, each a bug
fix in its own right, to be made in both trees:

| # | change | where | why |
|---|---|---|---|
| K1 | Integrate the twist-hold reference from the **post-floor** half-differential and compute headroom from the same floored speeds | `controlStep()`: move the `twistRef_.reference += …` line after `applySpeedFloor()` and use `0.5·(speedRight − speedLeft)` | MEASURED −11 % reverse kick, pivot 1.9° short with the servo on vs 2.5° long with it off (review MK-02). With `vMin = 0` this is latent, not moot: a caller that sets `vMin` again must not reintroduce the fight |
| K2 | Do not advance a wheel's position reference on a tick whose sample did not advance | `positionError()`: take `fresh` as an argument; `if (!fresh) return lastError` without `ref.reference += speed·dt` | MEASURED +6 duty points from one frozen tick through the position I-term (review MK-03 ⟲); this is the actual mechanism behind `pid-error-uses-a-stale-velocity-sample…` |
| K3 | Anti-windup: after updating, clamp `ref.reference` to `(position − origin) ± posErrMax` | `positionError()` | the reference otherwise carries an unbounded backlog into the taper and discharges it there (the "end bump" memory) |
| K4 | `rearmReferences()`: a deferred request (same shape as `rebasePosition()`) that disarms `posRefLeft_/Right_` and `twistRef_` at the start of the next `step()`, before `controlStep()` | new public method + request counter | lets a segment boundary re-anchor the integrators without the engine having to sacrifice a neutral tick (`awaitingHandoffNeutral` goes away) |
| K5 | Fleet bake: `cfg.vMin = 0.0f` | `shims.cpp:ensure()` | the floor now lives in `MotionLimits`; a kernel floor under a shaped profile is exactly the double-decision this design removes |

Everything else in the kernel is untouched: the FF+I law, lambda,
bias, stall and deficit latches, lease, e-stop, output publication.
`applySpeedFloor()` stays in the code (upstream firmware may still use
it) but is inert here.

### 4.6 `NezhaMotorPort` — unchanged, re-described

Keeps `slewRate_` (25 %/tick) and the 100 ms reversal dwell. They are
*hardware protection* — the brick's own controller stability and the
encoder-wedge trigger — not profile shaping, and the header should say
so. The design constraint they impose: `MotionLimits::accel` must
convert to less than the port slew, i.e. `accel·dt/fullDutyVelocity`
per tick < 25 %; at 400 mm/s² that is 1.2 %/tick, far inside. The dwell
means the reversing wheel of a pivot→straight transition starts ~4
ticks after the other; §6.4 says how the engine handles that.

### 4.7 The config surface — `shims.cpp`, wire names, blocks, `test.ts`

One descriptor table replaces the three parallel switches for the
shaping fields (this is review CO-05 scoped to what this design touches):

| wire name | ordinal | maps to | replaces |
|---|---|---|---|
| `accel` | 19 | `limits.accel` | `a_accel`, `ramp_ms` |
| `decel` | 20 | `limits.decel` | `a_decel`, `dist_taper`, `yaw_taper` |
| `jerk` | 28 | `limits.jerk` | `jerk` (same) |
| `v_max` | 21 | `limits.vMax` | `v_max` (same); `brake_frac` retired |
| `omega_max` | 30 | `limits.omegaMax` | `max_yaw_rate` |
| `v_floor` | 8 | `limits.vFloor` | kernel `speed_floor` (ordinal 8 keeps its number; the setter now writes `limits`, the kernel gets 0) |
| `omega_floor` | 34 (new) | `limits.omegaFloor` | `dist_floor`, `turn_floor` |
| `stop_distance` | 18 | `limits.stopDistance` | `pivot_overrun` |
| `arrive_dist` | 35 (new) | `limits.arriveDist` | the hard-coded 10-count margin |
| `arrive_yaw` | 36 (new) | `limits.arriveYaw` | the hard-coded 4-count margin |
| — | 22, 23, 24, 25, 26, 27, 29, 31 | **removed** | `brake_frac`, `dist_taper`, `yaw_taper`, `dist_floor`, `turn_floor`, `ramp_ms`, `plateau_min_s`, `profile_exit` |

Removed ordinals answer `err 1` on GET and SET for one release so a
stale bench script fails loudly instead of silently setting nothing;
`tools/field_dance.py` and any `SET` in `tools/` are updated in the same
ticket.

Blocks: `setTaperWindows`, `setTaperFloors`, `setRampMs` become hidden
no-op shims for one release (MakeCode projects that used them compile,
do nothing, and the release note says so); the `ConfigField` enum gains
the new names and loses the removed ones. `test.ts`'s two profiles
become:

```ts
function openLoopProfile()   { setLimits({accel: 300, decel: 300, vMax: 200, omegaMax: 90}) }
function closedLoopProfile() { setLimits({accel: 600, decel: 500, vMax: 400, omegaMax: 120}) }
```

(one shim taking four ints; floors and stop distance are per-robot and
come from the deploy bake, never from a profile).

### 4.8 What this design does *not* ask of odometry

Today the engine carries a rebase-epoch guard in `serviceMove()` and
`progress()` because `startSegment()` snapshots wheel positions at
`start()` and a deferred `rebasePosition()` can zero them before the
first tick. `Segment` captures its origin **lazily on the first
`service()` call** (§6.5), after that tick's `step()` has already
applied any deferred rebase. The engine's two epoch copies are deleted;
`odomUpdate()` keeps its own until the `Odometry` object absorbs it.

---

## 5. The tick, end to end

`tickDrive()` (`shims.cpp`) is unchanged in shape: `step()`, odometry,
`service()`, settle-on-completion, hook, pace. What changes is inside
`service()`:

```
MotionEngine::service():
  if (!seg_.active && !hold_.active) return false
  out = kernel_.output()                       // published by this tick's step()
  dt  = (nowMs - lastTickMs) / 1000

  if (seg_.active):
    if (seg_.originPending):                   // 6.5: first tick after start()
        seg_.posLeft0 = out.positionLeft; seg_.posRight0 = out.positionRight
        seg_.originPending = false
    remain = seg_.remaining(out) / cpm         // [mm] on the dominant axis
    (floor, cap) = axisLimits(seg_)            // [mm/s] 6.2: pure turn -> converted from deg/s
    step = shaper_.advance(target = min(seg_.cruise, cap, limits.vMax),
                           remain, floor, cap, dt, limits)
    if (seg_.wrongWay(out) || out.stallHalted || out.estopped || expired(seg_)):
        end(reason); return false
    if (step.arriving):                        // 6.3: the plan says "this is the last tick"
        if (seg_.hasPending):                  // pivot phase done -> straight phase
            kernel_.neutral(); kernel_.rearmReferences()
            seg_ = straightPhaseOf(seg_)       // originPending = true, shaper_.reset()
            return true
        kernel_.neutral(); seg_.active = false; return false
    (velocity, twist) = seg_.ratio() * step.vCmd * cpm
    kernel_.drive(velocity, twist, 500 ms)
    return true

  else:                                        // continuous hold (wheelsV / driveTwist)
    if (expired(hold_)): kernel_.neutral(); hold_.active = false; return false
    step = shaper_.advance(target = hold_.dominant, remain = -1,
                           floor = 0, cap = limits.vMax, dt, limits)
    (velocity, twist) = hold_.ratio() * step.vCmd * cpm
    kernel_.drive(velocity, twist, 500 ms)
    return true
```

Thirty-odd lines. No mode forks. The kernel receives one number per
axis per tick and does not reshape it.

---

## 6. The math

### 6.1 `VelocityShaper::advance()`

Inputs: `target` [mm/s] (the ceiling this segment may run at), `remain`
[mm] (signed distance still to travel on the dominant axis, or −1 for
none), `floor`/`cap` [mm/s] (already converted from this axis's own
units to dominant-wheel speed), `dt` [s], the limits. Every speed below
is [mm/s], every acceleration [mm/s²], `jerk` [mm/s³], `stopDistance`
[mm].

```
// 0. what the wheel is ACTUALLY doing: the kernel's last measured
//    dominant-axis speed (mean(vl, vr) for travel, half-differential for
//    yaw), not this shaper's own last command. With a real drivetrain
//    the wheel lags the command by `lag`, so planning against the
//    command over-brakes late and lands long (see 6.3, MEASURED).
vAct = measured >= 0 ? measured : v_prev

// 1. braking plan: the highest speed from which decel can still stop
//    inside what remains, less the coast the hardware adds after the
//    last command lands (stopDistance), less what the wheel travels
//    before it can respond at all: one tick of pipeline (unchanged,
//    v_prev*dt) PLUS the lag, credited separately as an ADDITIVE
//    vAct*lag term -- see this section's own "amended, not literal"
//    note below for why this is v_prev*dt + vAct*lag, not the single
//    term vAct*(dt+lag) an earlier draft of this section specified.
if remain >= 0:
    usable  = max(remain - stopDistance - v_prev*dt - vAct*lag, 0)
    vBrake  = sqrt(2 * decel * usable)
    vGoal   = min(target, vBrake, cap)
else:
    vGoal   = min(target, cap)

// 2. rate limit toward vGoal (first-order shaper)
vNext = clamp(vGoal, v_prev - decel*dt, v_prev + accel*dt)

// 3. optional jerk rounding (second-order): bound da/dt, with the
//    a^2/(2j) anticipation the current code already carries so a
//    jerk-limited ramp does not overshoot its cap.
if jerk > 0:
    aWant = (vGoal - v_prev) / dt, clamped to [-decel, +accel]
    if v_prev + a_prev^2/(2*jerk) >= vGoal and a_prev > 0: aWant = 0
    a = clamp(aWant, a_prev - jerk*dt, a_prev + jerk*dt)
    vNext = clamp(v_prev + a*dt, 0, vGoal)

// 4. floor: while not arrived the drivetrain cannot move below it, so
//    never command less. This is the ONLY floor in the system.
if remain >= 0 and vNext < floor: vNext = floor

// 5. arrival (6.3): the wheel, at its MEASURED speed, will cover what
//    remains during the pipeline tick plus the lag plus the fixed coast
//    -- same additive shape as step 1: v_next*dt (unchanged) PLUS
//    vAct*lag (new), not the single term vAct*(dt+lag).
arriving = remain >= 0 and remain <= vNext*dt + vAct*lag + stopDistance

v_prev = vNext; a_prev = (vNext - v_prev_before) / dt
return {vNext, arriving}
```

**Amended, not literal (found while implementing the lag fix).** The
two `vAct*(dt+lag)` terms this section originally specified are NOT
what the implementation does; both step 1 and step 5 instead use
`(the pre-existing dt-term, unchanged) + vAct*lag`, not the whole
`(dt+lag)` window driven through `vAct`. MEASURED (host testing): the
single-term form changes behavior even when NO lag is configured,
because a real kernel-measured `vAct` is only approximately equal to
`v_prev`/`v_next` (float noise in the encoder-derived velocity,
~1e-4 mm/s) — negligible on its own, but this is a discrete
arrival-boundary decision made every tick, and that noise compounding
across dozens of ticks was enough to shift WHICH tick a 90° pivot
arrives on (a cruise-200 ideal pivot moved from 90.15° to 89.26°, a
0.89° regression, purely from `vAct` replacing `v_prev`/`v_next` while
`lag` stayed 0 — breaking §9.1's own ideal-wheel arrival test, which
locks the pre-lag formula bit-exactly). The additive form's new term is
multiplied by `lag`, which is EXACTLY `0.0` — not merely close —
whenever `lag` is unconfigured, so both formulas are bit-identical to
their pre-lag originals at `lag = 0`, with no float-noise sensitivity.
See `velocity_shaper.cpp`'s own step 1/step 5 comments for the full
reasoning, and §6.3 below for how well the additive form closes the gap
once `lag` IS configured (not uniformly under a 1.0° stretch goal — see
that section's own updated table).

Properties worth naming:

- **From rest, the first command is the floor** — a step, deliberately.
  A wheel below breakaway does not move, and commanding a ramp from 0
  means the two wheels break away at different times, which is the
  "cold first move yaws" phenomenon. Commanding the floor on both wheels
  at once is a synchronous breakaway; the shaper's accel limit applies
  from the floor upward. (Today the first tick is max(floor, 25 %·cruise)
  = 100 mm/s at cruise 400; after: exactly the floor.)
- **The end is a planned stop, not a floor drop.** `vBrake` reaches the
  floor when `usable` is small, the floor holds it there for the last
  few ticks, and `arriving` fires when one more tick would cross. The
  hard neutral from the crawl still exists — physics, at 70 mm/s — but
  it is now the *planned* last tick, not a discovery.
- **`target` can change mid-segment** (a `SET v_max` over the wire, a
  supervisory re-solve later): the rate limiter simply slews toward the
  new value. Today a changed cruise is ignored until the next segment.
- **Legacy mode is gone.** The `elapsed/rampMs` ramp and `remain/taper`
  decel are not preserved; §7 shows what changes for the numbers that
  were tuned against them.

### 6.2 Axis units: floors and caps for pure turns

`b = effectiveTrackWidth()`. For a pure turn the dominant wheel's speed
is `ω·b/2`, so:

```
floor = pureTurn ? omegaFloor·(π/180)·b/2 : vFloor
cap   = pureTurn && omegaMax > 0 ? omegaMax·(π/180)·b/2 : +inf
```

At `b = 120 mm`: `omegaFloor` 20°/s → 21 mm/s per wheel → 0.5°/tick;
the old 70 mm/s floor was 67°/s → 1.6°/tick. `omegaMax` 90°/s → 94 mm/s
per wheel, which is why a pivot commanded at cruise 200 turned at
190°/s before `max_yaw_rate` existed.

Arcs use the linear floor and cap on the dominant wheel; the other wheel
follows the ratio. This keeps motion-api §3.3's rule that the pivot
rate is *derived* from cruise (`2·speed/b`) — the design adds a ceiling
and a floor on that derived rate, not a program-facing pivot speed.

**Why a separate yaw floor is physical, not cosmetic.** Breakaway is a
per-wheel torque threshold; on a pivot both wheels turn, so the same
70 mm/s applies per wheel and the robot spins at 67°/s minimum — too
fast to land inside a 0.3° window. The yaw floor is the lowest rate at
which a pivot still *sustains* motion once started, which is lower than
the breakaway rate because static friction has been broken. UNVERIFIED:
it needs one sweep (§10.2). If it measures at 67°/s after all, the
design still holds; predictive arrival then lands within one 1.6° tick
instead of two.

### 6.3 Arrival: predict, don't discover

Today: end when `remain <= margin` (4 or 10 counts), tested *after* the
step that crossed it, with the neutral landing a tick later still —
two ticks of coast at floor speed, MEASURED +0.8…+2.6° on pivots.

After: `arriving = remain <= vNext·dt + stopDistance` — "the tick I am
about to command will carry me to the target". The engine then commands
neutral *this* tick, and the pipeline delivers the stop as the wheel
completes exactly that last tick of travel. The residual is bounded by
the arithmetic error in `vNext·dt` (one tick of the *floor* speed at
most: 0.5° with the yaw floor, 1.7 mm on a straight) rather than by two
ticks.

`stopDistance` is the per-wheel coast after the last nonzero command
lands that does not scale with speed: brick latency at zero. It is the
physical quantity `pivot_overrun` was approximating (2.2 mm ≈ one tick
at 70 mm/s plus ~0.5 mm of coast). It is measured, not fitted, by §10.2.

**Plan against the measured speed, and model the lag.** This was added
after the first hardware run (tovez, 2026-09-04,
`captures/bench-acceptance-029-20260904/`): 90° pivots at cruise 100
ended +13…+56° long in the robot's own odometry while the ideal-wheel
probe had predicted ±0.5°. The host model with a first-order wheel lag
reproduces it — MEASURED against the sprint-029 engine as first landed,
[`raw/stiction_probe.cpp`](../code-review/2026-09-02/raw/stiction_probe.cpp)
/ [`.out`](../code-review/2026-09-02/raw/stiction_probe.out):

| wheel model | cruise 40 | cruise 100 | cruise 200 |
|---|---|---|---|
| ideal | +0.1° | +0.0° | −0.0° |
| lag 80 ms | +2.7° | +3.8° | +8.8° |
| lag 80 ms + breakaway 70 mm/s | +5.6° | +3.4° | +9.4° |
| lag 150 ms + breakaway | +8.8° | +4.5° | **+26.1°** |

The old taper was insensitive to lag because it crawled the last
degrees at the floor; a constant-decel plan brakes from cruise and is
sensitive to it in proportion to speed. Two changes close it: the
braking plan and the arrival test use the kernel's *measured*
dominant-axis speed (`Output.velocityLeft/Right`, already sampled every
tick) instead of the shaper's own last command, and a per-robot `lag`
[s] enters both as an ADDITIVE `+ vAct·lag` term on top of the existing
`v_prev·dt`/`v_next·dt` terms — not the single term `vAct·(dt + lag)`
this paragraph originally specified; §6.1's own "amended, not literal"
note has the measured reason the implementation deviates. `stopDistance`
keeps only the speed-independent remainder.

**Re-measured with the fix landed** (sprint 029 ticket 009, same
lagged-wheel host model, `lag` set to each row's own time constant —
`tests/host/test_profile_probe.py::test_design_s6_3_table_remeasured_with_the_fix`
is the citation, rerun with `-s` to reproduce):

| lag model (breakaway 70 mm/s) | cruise 40 | cruise 100 | cruise 200 |
|---|---|---|---|
| 80 ms, unfixed (`lag` = 0) | +5.6° | +3.4° | +9.4° |
| 80 ms, fixed (`lag` = 0.08) | **+0.8°** | +1.9° | +2.2° |
| 150 ms, unfixed (`lag` = 0) | +8.8° | +4.5° | +26.1° |
| 150 ms, fixed (`lag` = 0.15) | +0.2° | +0.9° | −1.6° |

The fix closes 85–98% of every cell's gap, but NOT uniformly under the
1.0° stretch goal this section originally set: three of six cells land
inside it, the other three land inside 2.5°. The residual is not an
arrival-formula problem — it was measured to be the SAME regardless of
which term (`v_prev`/`v_next` vs `vAct`, additive vs single-term) the
braking plan and arrival test were driven by. Its actual cause: at this
geometry, `omegaFloorAsWheelSpeed()` (~21 mm/s) sits below half the
model's own breakaway (35 mm/s), so the segment's very first commanded
tick — §6.1's own "from rest, the first command is the floor, a step"
— does not itself break the simulated wheel away; it takes ~5–6 further
accel-ramped ticks before the commanded speed first crosses the full
70 mm/s breakaway. That fixed startup delay belongs to the stiction
model and this floor/breakaway relationship, not to anything
`VelocityShaper::advance()` decides, so no arrival-side formula reaches
it. `stopDistance` — bench-measured *with* `lag` already set, "the
speed-independent remainder once the lag term is accounted for
separately" (§10.2) — is the mechanism this design already names for
exactly this kind of residual; it stays 0 (unmeasured) in this host
model, since §10.2's bench sweep is a later ticket's job. The constant
`+2°` the fleet used to calibrate away becomes `v_floor·lag`, which the
model predicts rather than fits, modulo this same residual.

The old margins (`arriveDist`, `arriveYaw`) survive only as the
window inside which a segment is *considered done without a further
tick* — the `remain <= arrive` case of the same test — so a call whose
residual is already inside the window issues nothing, as `goToR`'s
`arrive` gate does today.

### 6.4 The pivot→straight handoff goes through rest

motion-api §3.3: "Never replace an in-flight arc with a pivot at speed…
ramp to rest through an ordinary planned stop first." The shaper makes
this structural: phase 1 ends with `arriving` (planned stop), the engine
issues `neutral()` + `rearmReferences()`, and phase 2 starts from
`v = 0` at the floor. No `awaitingHandoffNeutral`, no wasted tick: the
neutral tick *is* the rest the spec asks for. K4 is what lets the
twist-hold reference re-anchor at the new origin without a neutral
*step* being the only way to disarm it.

The port's reversal dwell still holds the wheel that reversed for
~100 ms after the phase change. The engine does not model it; with a
synchronous floor start the other wheel moves alone for ~4 ticks at
21-70 mm/s (≤ 6 mm), and the twist-hold servo (now integrating the
right reference) trims it back. MEASURED on the ideal model this costs
≈1 mm / 0.1°; on hardware UNVERIFIED and worth one look at `dutl/dutr`
in the four ticks after a pivot. If it matters, the fix is in the port
(dwell both wheels together), not in the profile.

### 6.5 Lazy origin capture

`start()` builds the `Segment` with `originPending = true` and issues no
`drive()`. The first `service()` call — which always follows a `step()`
on the same fiber — captures `posLeft0/Right0` from that step's `Output`
and issues the first command. Between `start()` and that first `step()`
the wheels cannot have moved (nothing was commanded), and any deferred
`rebasePosition()` requested before the move has been applied by that
`step()`. The race the review's CO-02 describes cannot occur, and the
engine needs no `positionEpoch*` at all.

Cost: the first command lands one `service()` later than today. Today
`startSegment()` issues `drive()` synchronously and the caller's next
`tickDrive()` delivers it; after, `start()` returns, the next
`tickDrive()`'s `step()` delivers nothing new, its `service()` issues
the first command, and the *following* `step()` delivers it. One tick
(24 ms) of extra latency at move start, identical for every entry point,
and paid back by not needing the handoff tick or the epoch guard.

---

## 7. What changes, and by how much

MEASURED "before" from the probe (ideal wheels); "after" is what §6
computes for the same inputs and must be confirmed by re-running the
probe against the new engine before any hardware run.

| scenario | before | after (predicted) |
|---|---|---|
| 90° pivot, cruise 100, servo on | ends 88.07° (servo fights floor), −11 % reverse kick | ends 90.0 ± 0.5°, no reverse duty (K1 + yaw floor + predictive stop) |
| 90° pivot, cruise 200 | ends 91.42° | 90.0 ± 0.5° |
| 45° / 300 mm arc, cruise 100 | (285, 120) vs exact (270, 112) | (270, 112) ± 2 mm |
| 600 mm straight, cruise 200 | peak 220.7 mm/s (+10 %), start accel 2932, decel ∝ v² | start step to 70 then 400 mm/s²; decel 400; peak ≈ 200 + I-term catch-up (K3 bounds it to ≤ posErrMax·ki = 60 mm/s worst case, typically far less) |
| 600 mm straight, cruise 400, 80 ms lag | legacy +5.6 mm overshoot, 6058 mm/s² decel | −0.5…+0.5 mm (shaped mode already does this, MEASURED −0.6) |
| `set wheel speeds 200 200` from rest | 0, 200, 229, 229, 225 mm/s | 0, 9.6, 19.2, 28.8, … (400 mm/s² from rest; a continuous hold has no floor, §5 and §13), no overshoot spike. MEASURED by `tests/host/test_profile_probe.py` (sprint 029 ticket 003) |
| frozen encoder tick at 300 mm/s | +6 duty points, wheel +17 % for a tick | 0 (K2) |
| `SET dist_floor 45` at cruise 200 | no effect | field removed; `v_floor` is the floor and it applies |
| `pivot_overrun 2.2` | subtracts 2.2 mm from every yaw target | field removed; `stop_distance` measured once, applied to both axes |
| `test.ts` open vs closed profile | identical crawl (both below the kernel floor) | genuinely different accel/decel/cruise, same floor |

Move duration: a 600 mm leg at cruise 200 is 3.36 s today and ≈3.3 s
after (the ramp is 0.33 s at 400 mm/s² instead of 0.43 s; the crawl is
shorter because the braking plan reaches the floor later than the fixed
31 mm taper window does). Pivots get slower at the end (0.5°/tick crawl
instead of 1.6°) and faster in the middle (no servo fight); net roughly
even at cruise 100.

Behaviour students see: moves start a little more gently and stop
without the end bump; `set wheel speeds` ramps instead of lurching; a
`move 47 cm turning 90°` still pivots first (the split rule is
unchanged). Nothing in the block palette changes shape.

---

## 8. Knob compatibility

| old | new | note |
|---|---|---|
| `a_accel`, `a_decel` | `accel`, `decel` | renamed; same units; now always active (no legacy mode) |
| `ramp_ms` | — | derived: ramp time = cruise/accel |
| `dist_taper`, `yaw_taper` | — | derived: window = v²/(2·decel), per axis |
| `dist_floor`, `turn_floor` | `v_floor`, `omega_floor` | fractions of cruise → absolute, per axis |
| `speed_floor` (kernel) | `v_floor` | ordinal 8 keeps its number; the kernel's own `vMin` is pinned at 0 |
| `pivot_overrun` | `stop_distance` | per-wheel mm, both axes; measured not fitted |
| `max_yaw_rate` | `omega_max` | renamed |
| `profile_exit` | — | the braking plan ends at the floor by construction |
| `plateau_min_s`, `brake_frac` | — | the plateau derate and the distance-chosen default cruise are replaced by one rule: `v_default(D) = min(v_max, sqrt(decel·D))` (a triangle whose braking half fits in D) |
| `arrive` (goToR argument) | unchanged | plus `arrive_dist`/`arrive_yaw` as the engine's own windows |

`tools/` grep for the removed names and the `firmware_bake` keys in
`radio-robot-lib/config/robots/*.json` (`pivot_overrun_mm` →
`stop_distance_mm`) go in the migration ticket.

---

## 9. Tests

**Rewrite** (they pin the algorithm this design removes):
`test_motion_engine_acceleration_profile.py` (legacy/shaped split,
`plateau`, `profile_exit`, `brake_frac`),
`test_regression_yaw_taper_pure_turn.py` (pins "only a pure turn tapers
on yaw" — still true, restated as "the shaper runs on the dominant
axis"), `test_motion_engine_shaping_fields.py` (the field list),
`test_motion_engine_settle.py` (unchanged behaviour, different entry).

**New**, all host-side, all against `VelocityShaper` or `MotionEngine`
with `FakeMotor` ideal wheels:

1. `test_velocity_shaper.py` — from rest the first command is the floor;
   accel never exceeds `accel` above the floor; decel never exceeds
   `decel`; with `jerk` the acceleration never steps by more than
   `jerk·dt`; `arriving` fires exactly when `remain <= v·dt + stop`.
2. `test_profile_probe.py` — the review's probe promoted to a test:
   pivot 90° at cruise 60/100/200 ends within 0.5°, no negative duty on
   either wheel during a pivot, arc endpoint within 2 mm, straight peak
   speed ≤ cruise + 5 %, `set wheel speeds` never steps more than
   `accel·dt` above the floor.
3. `test_kernel_reference_handling.py` — K1: a floored command produces
   a twist reference equal to the floored half-differential; K2: a
   frozen tick leaves the reference where it was; K3: a 50 mm lag
   yields a reference backlog of exactly `posErrMax`; K4:
   `rearmReferences()` zeroes both references at the next step and the
   twist error is zero on the tick after a phase change.
4. `test_segment_lazy_origin.py` — a `rebasePosition()` requested
   between `start()` and the first `service()` does not change the
   segment's measured progress.
5. `test_config_descriptor_table.py` — every wire name in the table
   round-trips through SET/GET; the removed names answer `err 1`.

**Keep**: the deadline, e-stop/refusal, goToW geometry, primitives and
reductions tests; they are about targets and outcomes, not shaping.

---

## 10. Bench acceptance

### 10.1 The gates

Run on one robot before the branch merges, via the wire, with the
overhead camera as truth (`.claude/rules/measurement-citations.md`
applies: every number names its capture):

| gate | procedure | pass |
|---|---|---|
| G1 pivot accuracy | 12 × `MOVE_X 0 ±1571 100 5000` alternating, camera at rest before and after each | mean |error| ≤ 0.5°, sd ≤ 0.4°, no per-tick `dutl/dutr` sign reversal in the last 10 ticks |
| G2 arc endpoint | 6 × `MOVE_X 300 785 100 8000` (45°), camera | endpoint within 5 mm of (270, 112) in the body frame |
| G3 straight | 6 × `MOVE_X 600 0 200 8000` | camera leg length 600 ± 3 mm; peak `vl/vr` ≤ 220 mm/s; no leg-end bump (`vl/vr` monotone in the last 10 ticks) |
| G4 jerk | same as G3, differentiate `vl/vr` twice from `TLM FULL` | first tick ≤ floor; thereafter |Δv/Δt| ≤ 1.5 × `accel`; no tick above 2 × `decel` at the end |
| G5 continuous | `WHEELS_V 200 200 2000` from rest | `vl/vr` rise from the floor at ≤ 1.5 × `accel`; no overshoot above 210 mm/s |
| G6 square tour closure | `RUN:square` × 3, camera | closure ≤ the current baseline (`reports/gopiv-closure-20260901.md`); no regression is the bar, improvement is expected |

### 10.2 The three measurements the limits need

- **`lag`**: a `WHEELS_V 200 200 1500` step from rest with `TLM FULL`;
  fit `vl`/`vr` against the commanded ramp (the shaper's own `accel`
  limit) as a first-order response; the time constant is `lag`. Store in
  `firmware_bake.lag_s`. Expected order: 50-150 ms (the host model needs
  ~80-150 ms to reproduce tovez's 2026-09-04 overshoots).
- **`stop_distance`**: 10 pivots at the yaw floor only (`MOVE_X 0 1571
  <floor-equivalent cruise>`) with `lag` already set, residual overshoot
  at rest by camera, converted to per-wheel mm. Store in
  `firmware_bake.stop_distance_mm`. Expected order: 0.3-1 mm.
- **`omega_floor`**: from rest, `WHEELS_V ±v ∓v 1500` sweeping v down
  from 70 mm/s per wheel; the lowest v at which the encoders show
  sustained rotation over the whole 1.5 s is the floor. Expected order:
  15-30°/s. `v_floor` is already measured (70 mm/s, 2026-08-29).

---

## 11. Migration — five tickets, in order

| # | ticket | touches | done when |
|---|---|---|---|
| 1 | Kernel patches K1-K4 with host tests (§9.3); PR to `radio-robot-elite` in the same change | `core/diffdrive.*`, `tests/host/` | both trees pass their fidelity suites; vendored diff is again comments-only |
| 2 | `MotionLimits` + `VelocityShaper` as new files, host-tested in isolation (§9.1); not yet wired | `motion/motion_limits.h`, `motion/velocity_shaper.{h,cpp}` | shaper tests green; probe-as-test written against the shaper alone |
| 3 | `Segment` + `MotionEngine::service()`; delete both legacy algorithms, the thirteen fields, the handoff flag, the epoch copies; `wheelsV` through the hold; K5 (`vMin = 0`); rename every unit-suffixed identifier left in `motion/` per `.claude/rules/no-units-in-identifiers.md` (review CH-04, triage #24 covers the rest of `src/`) | `motion/motion_engine.*`, `shims.cpp:ensure()` | §9.2 probe test green on ideal wheels; §7's "after" column measured by the probe and recorded; no `MmS`/`Ms`/`Mm`/`Rad`/`Counts` suffix remains in `motion/` |
| 4 | Config surface: descriptor table, wire names, removed ordinals erroring, blocks hidden no-ops, `test.ts` profiles, `tools/` and `firmware_bake` keys | `shims.cpp`, `wire_adapter.cpp`, `blocks/motion.ts`, `test/test.ts`, `tools/`, `make_deploy.py` | §9.5 green; `make_deploy.py --robot` bakes `stop_distance_mm` |
| 5 | Bench acceptance §10 on one robot; measure §10.2; update `src/DESIGN.md` §3 and `docs/design/specification.md`'s constants table; retire `pivot_overrun` from every robot config | captures, reports, docs | G1-G6 pass and are cited |

Tickets 1 and 2 are independent of each other and of the rest; 3 needs
both; 4 needs 3; 5 needs 4. The build-checkpoint ticket convention
applies to 3 and 4.

---

## 12. Decisions this design makes, and the ones it needs

**Made here:**

- The speed floor is a *profile* concept, not a *servo* concept. This
  diverges from motion-api §4's enumeration of "ratio-preserving speed
  floor" as a kernel feature; the ratio is still preserved, the policy
  moves up. Record it in `src/DESIGN.md` §3 as a deliberate divergence.
- Legacy shaping is deleted, not kept behind a mode. Two modes in one
  method is the defect.
- Start from the floor, not from zero. Synchronous breakaway over
  cosmetic smoothness; the jerk limit begins above the floor.
- `wheelsX` becomes closed-loop on encoders like `moveX`. The spec permits
  it ("timeout is a required backstop, not the stop condition"); the
  dead-reckoned lease was the only reason the two primitives differed in
  how they end.

**Needed from the stakeholder:**

1. **The kernel fork.** K1-K4 are the third, fourth, fifth and sixth
   local kernel changes. Either the "byte-identical" rule is replaced by
   a behavioural fidelity test and this repo owns its copy, or every
   kernel ticket ships as a paired upstream PR. This design works under
   either; ticket 1 is written for the paired-PR case.
2. **Retiring `pivot_overrun` from the fleet configs** (`firmware_bake`
   in `radio-robot-lib`), a cross-repo config change.
3. Whether `setTaperWindows`/`setTaperFloors`/`setRampMs` may be removed
   from the block palette outright or must stay as hidden no-ops for a
   release (students' saved projects).

**Out of scope, flagged:** `kp` > 0 with the FF gain corrected
(`measure-vevov-s-true-full-duty-velocity.md`) would remove most of the
remaining +5-10 % ramp-end overshoot the I-term still produces after K3.
That is a tuning campaign with the probe as its bench, after this lands.

---

## 13. Open questions

- Is the reversal dwell (§6.4) visible on hardware as a leg-start yaw?
  One `TLM FULL` capture of four ticks after a pivot answers it. If yes,
  the port should dwell both wheels.
- Should the hold (`wheelsV`) apply `v_floor`? Today a `set wheel speeds
  20 20` is floored to 70 by the kernel; after, the shaper's hold path
  passes `floor = 0` so a student can command a crawl that does not move.
  The design says no floor on continuous drive (the student asked for 20)
  but a `STATUS` flag "commanded below breakaway" would make the silent
  non-motion diagnosable. Cheap; decide in ticket 4.
- `omega_floor` for arcs: the design floors the dominant *wheel* at
  `v_floor` in an arc. A very tight arc (dominant wheel far faster than
  the inner) could leave the inner wheel below breakaway. The twist-hold
  servo will compensate to a point; whether a tight arc needs its own
  rule is a §10 observation, not a design decision yet.
