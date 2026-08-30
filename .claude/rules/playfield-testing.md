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

## The robot is OFF — check this first

If the robot is **visible on the field**, **answers the protocol** normally, and
**reports believed motion in its own odometry**, but the **camera shows it has
not moved** — the robot is switched off. Check that before slip, stiction, the
taper window, breakaway, or wheels-off-the-ground.

Measured on tovez 2026-08-26: `RUN:straight:4` then `RUN:straight:15` reported
4.20 cm then 15.00 cm of odometry (19.2 cm believed), while the camera held the
tag within **0.7 mm** of its start across all three reads, pixel position
unchanged to a fraction of a pixel.

**`connL=1` / `connR=1` is NOT proof the motors have power.** Those reflect
whether the encoder I2C transaction succeeded, and the brick's logic can answer
I2C while the motor drive is dead. `cyc` advancing only proves the kernel is
ticking. On the run above, STATUS read `ready=1 connL=1 connR=1 cyc=21 i2cf=0`
on a robot that was off — that line looks perfectly healthy and means nothing
about motion.

Odometry cannot detect its own failure to move: it integrates encoder deltas and
will report the full commanded distance. **Only an external instrument — the
overhead camera, or a tape — can confirm real motion.**

USB reaches only the bench stand; anything needing real motion runs
untethered over the zavaz relay (channel 4 — never retune getez's
channel 3).

### The fleet is MIXED on `!N` — one board migrated, four have not

**Live hazard, opened 2026-08-29, updated 2026-08-30. Closes when ALL
five robots are reflashed.** `!N <name>` derives the radio link from the
board's name. The relay migrated to that derivation
(`microbit-radio-relay` f8b1224/362d7f1); the robots are migrating one
at a time, so **`!N` is correct for some boards and silently wrong for
others** — a worse state to reason about than uniformly-unmigrated,
because it works once and then does not.

| board | `!N` tunes relay to | robot is on | `!N` |
|---|---|---|---|
| **gopiv** | 47 / 60 | **47 / 60** | **works** |
| vevov | 37 / 43 | 4 / 10 | silent |
| tovez | 55 / 108 | 3 / 10 | silent |
| zeguz | 25 / 19 | 3 / 10 | silent |
| zetuv | 27 / 21 | 3 / 10 | silent |

**Use `!CG <channel> <group>` with explicit numbers on everything except
gopiv.** For gopiv either works.

MEASURED gopiv 2026-08-30, `captures/radio-addressing-20260830.md`
(sprint 025 ticket 005, run on LAN host hodr): `HELLO` returns
`device NEZHA2 robot gopiv 2175407711`, and 2175407711 mod 3125 = 1461 =
base5("gopiv") -> 47/60. After the remote flash, `!CG 47 60` gave
`pong 51487, 52775, 54063, 55351` (4/4) and the NEGATIVE control
`!CG 5 10` got no reply to `HELLO`, four `PING`s or `ID` — so the board
genuinely moved rather than answering on both addresses. The four
unmigrated boards were verified against
`origin/master:src/comms/radio_transport.h:213` (`kChannel = 4`,
per-robot injection by `tools/make_deploy.py` `_K_CHANNEL_RE`) and the
relay's own `mbrelay.naming.name_to_radio()`.

The symptom on an unmigrated board is a **silent robot** — the failure
this whole file exists to stop you misdiagnosing. Nothing errors; the
relay is happily tuned somewhere the robot is not.

Note the hazard has reversed once already. Before the relay migrated,
`!N` computed a legacy hash nobody used, which was harmless. A working
`!N` pointed at unmigrated robots is worse than a broken one, and a
PARTIALLY migrated fleet is worse still. Delete this section only when
every board answers `!N`, not when the last sprint closes.

## v6 wire commands MUST carry a sequence id

The v6 handler compares each line's `#<id>` against its own
`expectedNext_` and classifies anything below it as a stale retransmit
that is deliberately **not executed**. An unsequenced line parses as
`#0`, which is unconditionally below `expectedNext_` (it starts at 1),
so it is silently dropped.

Measured on vevov, 2026-08-25, over USB. **PRE-SPRINT-024** — the
"keepalive acks" in the first row came from the free-running
`emitReliability()` call sprint 024 ticket 001 deleted, so that column
describes pre-024 firmware and has not been re-measured since:

| sent | result |
|---|---|
| `TLM POSE` | 0 telemetry frames (keepalive acks only) |
| `TLM POSE #1` | 72 `t` frames + 4 `thdr` frames |

`tools/robotlink.py` attaches ids to the v6 verbs automatically. Since
sprint 024 ticket 002 it resyncs on connect by sending `HELLO`
(`Link.hello()`), **not** by reading a keepalive via `sync_seq()` —
`HELLO` resets the robot to `expectedNext_ = 1` and clears any
outstanding gap, so a wedged link now heals on reconnect without a
reboot. `sync_seq()` still exists and is still correct for a caller
that has a live `ack`/`nack` line to read outside the connect path, but
nothing streams passively anymore for it to find. A retransmit must
reuse its ORIGINAL id — a resend that takes a fresh one presents as a
numeric gap, which stalls the stream on purpose.

**Which verbs carry an id (2026-08-27, agreed with radio-robot-lib):**
a verb is sequenced iff its correctness depends on its position in the
stream — either running it twice changes the robot, or answering it out
of order gives a wrong answer.

| unsequenced (just type them) | sequenced (need `#<id>`) |
|---|---|
| `HELLO` `PING` `ESTOP` `HELP` `ID` `VER` `STATUS` | `GET` `SET` `TLM` `STOP` `RUN` `WHEELS_*` `MOVE_*` `GO_TO_*` |

`GET` is sequenced despite being read-only, because `SET` mutates what
it reads. The unsequenced ones are forgiving: `ID`, `ID #1`, `ID junk`
all answer identically.

**`HELLO` is NOT a liveness probe.** It is a session RESET — it sets
`expectedNext_ = 1`, so firing it at a live session desyncs the link you
were checking and can stall it permanently. Use:

- `PING` → `pong <n>` — "alive"
- `STATUS` → `... next= done= reason=` — "alive, and here is where the
  sequence stands"; distinguishes idle from stalled-on-a-gap
- `HELLO` — "start over", only where losing the sequence is the intent
  (e.g. `open_link()` at session start, which is correct usage)

The cleartext `RUN:`/`DIAG` vocabulary is a **different parser path**
and is NOT sequenced: `RUN:tour:wheels` unsequenced returns its
`DBG:tour=` receipt normally.

## RUN verbs are string-keyed — numeric RUN is a silent no-op

`test.ts` dispatches `onRun()` on a string. `RUN:1` matches no handler,
so the tool runs to completion, prints numbers, and the robot never
moved. See `tests/tools/test_run_verbs.py`, which pins the exact
strings.

## `mbdeploy probe`'s ROLE column is a cached registry, not a live read

`probe` is authoritative for **ports** and **CONN**, and NOT for what
firmware a board is running. Its COMMON NAME / ROLE columns come from a
registry keyed by UID and go stale the moment a board is reflashed to a
different role.

Measured on vevov, 2026-08-26, minutes apart:

| source | says |
|---|---|
| `mbdeploy probe` | `vevov  relay  RADIOBRIDGE` |
| `HELLO` over USB | `device NEZHA2 robot vevov 1198504156` |

The board was running robot firmware the whole time. Reading the probe
column as "vevov is still a radio bridge" would have started a hunt for a
flash that had in fact succeeded.

**`HELLO` is the only identity authority** -- it derives from
`microbit_friendly_name()`, burned into the chip. Note `ID` is NOT: its
middle field is `kProfile`, build provenance that on 2026-08-26 read
`tovez` on vevov. Same rule as everywhere else on this rig: trust the
instrument physically coupled to the thing you are measuring.

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
