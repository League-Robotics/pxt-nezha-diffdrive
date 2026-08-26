# Playfield and bench testing

Operational facts for driving vevov. Imported from `radio-robot-elite`'s
own `.claude/rules/playfield-testing.md` and `hardware-bench-testing.md`
(the authoritative copies — check there for anything not covered here),
plus what was measured in this repo on 2026-08-25.

Driving off the playfield is a **failure**, not a synonym for driving.

## Room lights — turn them on yourself

A **Shelly Plus 1 at `192.168.1.122`**, no auth. **They turn off on
their own.** When tags vanish, suspect the lights FIRST — a dark field
looks exactly like a broken camera or a lost robot.

```bash
curl -s "http://192.168.1.122/rpc/Switch.GetStatus?id=0"    # "output" is the lights
curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true"  # ON
```

Check `output: true` BEFORE arming a run. Prefer leaving them **on**;
only turn them off when explicitly asked. `was_on` in the Set reply is
not fully trustworthy — confirm with `GetStatus`.

## Field limits and the mandatory pre-flight path check

Field is **134.3 x 89.3 cm**, AprilTag-1-centred, so limits are
**±67.15 / ±44.65 cm**. Keep a **12 cm margin**.

Before sending ANY commanded motion, compute the full projected path
from a **measured** start pose (a camera fix, never an assumption)
through every planned leg and turn, and confirm every waypoint clears
the margin. The geofence is what catches *unexpected* drift on top of
that — it is not the primary check. The 100x60 cm tour rectangle
(±50/±30) clears with 17 x 15 cm to spare, but only from a start pose
actually on the NE dot.

## Bench stand vs playfield — never combined

On the bench stand the wheels are off the ground. That means:

- **Only `RUN:tour:wheels` is meaningful there.** `tour:robot` plans
  each leg from IMU heading and `tour:world` from the OTOS; neither
  sensor changes when the body never moves, so both stall or diverge.
- **Confirm which surface you are on from the DATA, never from memory
  of what someone said.** The OTOS `ox`/`oy` columns are the cheapest
  discriminator: across a full tour they show ~112 cm of travel on the
  table and ~1 mm on the stand. Anything in between is ambiguous —
  a lifted robot's optical flow can integrate tens of cm of garbage —
  so fall back to the camera.

  This is not hypothetical: on 2026-08-25 a whole error attribution
  (an "81% control overshoot vs 19% scrub" split) was built on the
  assumption that a run had been wheels-up. It had not, the split was
  meaningless, and the 112 cm of OTOS travel proving it was already
  sitting in the captured CSV, unread. A single `get_tags` call that
  happened not to see the robot was taken as proof of placement instead
  of being re-checked.
- **Bench odometry is not a proxy for field accuracy.** Unloaded wheels
  do not match loaded ones; a bench tour on 2026-08-25 drew a visibly
  rotated rectangle in pure odometry that the same firmware does not
  produce on the floor.

Opening or reopening the USB serial port RESETS the target program
(measured on tovez 2026-08-26: pose re-zeroed between two scripted
serial sessions). Plan bench scripts as one serial session per
experiment, and never assume state (pose, taper/floor config, stall
latch) survives a port close.

USB reaches only the bench stand; anything needing real motion runs
untethered over the zavaz relay (channel 4 — never retune getez's
channel 3).

## v6 wire commands MUST carry a sequence id

The v6 handler compares each line's `#<id>` against its own
`expectedNext_` and classifies anything below it as a stale retransmit
that is deliberately **not executed**. An unsequenced line parses as
`#0`, which is unconditionally below `expectedNext_` (it starts at 1),
so it is silently dropped.

Measured on vevov, 2026-08-25, over USB:

| sent | result |
|---|---|
| `TLM POSE` | 0 telemetry frames (keepalive acks only) |
| `TLM POSE #1` | 72 `t` frames + 4 `thdr` frames |

`tools/robotlink.py` now attaches ids to the v6 verbs automatically and
adopts the robot's `expectedNext_` on connect (`sync_seq()`). A
retransmit must reuse its ORIGINAL id — a resend that takes a fresh one
presents as a numeric gap, which stalls the stream on purpose.

The cleartext `RUN:`/`DIAG` vocabulary is a **different parser path**
and is NOT sequenced: `RUN:tour:wheels` unsequenced returns its
`DBG:tour=` receipt normally.

## RUN verbs are string-keyed — numeric RUN is a silent no-op

`test.ts` dispatches `onRun()` on a string. `RUN:1` matches no handler,
so the tool runs to completion, prints numbers, and the robot never
moved. See `tests/tools/test_run_verbs.py`, which pins the exact
strings.

## Camera

- The overhead camera is the **OV9782** (`open_camera(pattern="arducam")`
  matches the OV9281 first, which cannot see the field).
- **Measured pipeline lag is ~0.10 s**, not the ~0.7 s older notes
  assume. Verify by cross-correlating camera heading against the
  encoder heading staircase rather than trusting either number —
  a wrong lag makes per-segment error attribution produce nonsense
  (it once implied a −168° turn error on a tour that closed in 33 mm).
- `camlink.py --check` verifies **AprilTag** 10/11, but the field now
  carries an **ArUco** border set, so it reports `NOT VISIBLE` on a
  perfectly healthy camera. Verify with **AprilTag 1** instead: it is
  the fixed field-centre marker and must read world (0, 0).
- The camera is a **diagnostic**, never a control input: one seed at
  the start, scoring at the end, recording throughout, and nothing it
  records reaches the robot mid-tour.
- Per-boundary fixes beat start-and-end: with only two fixes there is
  no way to split the residual between leg-length and rotation error.

## Where the error actually is (vevov, 2026-08-25, camera-truthed)

Over a 320 cm open-loop tour: travel accurate to **0.5%** (encoder
324.4 cm vs camera 322.7 cm), pivots barely translating (0.09–0.50 cm
slip), and net rotation **363.7° physical for 360.4° believed** — the
tour as a whole OVER-rotates by +3.3°.

But an isolated, camera-truthed `RUN:pivot:90` **UNDER**-rotates:
camera/commanded 0.9852, camera/encoder 0.9805 over six alternating
pivots. Both cannot be caused by the pivots. The remaining ~+7° must be
injected during the straight LEGS — physical heading change the wheel
odometry never sees, on legs whose *distance* is accurate to 0.5%.

**So rotation is the error budget, but the pivots are not where it
comes from.** Do not "correct" the pivots; they already under-turn.
Confirming the leg/pivot split needs per-boundary camera fixes at REST,
not a continuous recording segmented afterwards. See
`clasi/issues/rotation-error-is-injected-by-the-legs-not-the-pivots.md`.
`tools/park.py` picks forward-vs-reverse approach to minimise total
commanded rotation, and absorbs sub-tolerance heading residuals into
the next move instead of pivoting them away.

Note a subtlety when reasoning about pivot pairs: a *scale* error
cancels exactly across an equal-and-opposite pivot pair (turn out, turn
back), so such a plan can land on a correct heading having driven in
the wrong direction — the cost shows up in position, not heading. A
constant per-pivot offset error does not cancel.
