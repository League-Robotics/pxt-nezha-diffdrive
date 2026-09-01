# Any RUN: program that drives the motors resets the board (fw 1.20260829.1)

**Severity: high — every on-robot tour program is unusable.**
Opened 2026-09-01. Board: gopiv. Firmware: `1.20260829.1` (master,
built and flashed 2026-09-01 from `.tmp/deploy-head`, DAPLink MSD onto
`/media/jtl/MICROBIT` at farm node magni, UID
`9906360200052820049d38a46da36a83000000006e052820` verified against
`DETAILS.TXT`).

## Symptom

A cleartext `RUN:` verb that moves the robot emits its `DBG:` banner,
drives for roughly one move, and then the board **resets**: the boot
banner reappears on the wire, the `PING` uptime counter restarts, and
`cyc` returns to 0 and stays there — the motor kernel never comes back
until the program is restarted.

```
RUN:square:20
  DBG:tour=square:side=20
  device NEZHA2 robot gopiv 2175407711     <- boot banner: this is a RESET
  OTOS:boot:id=0:connected=0
```

`STATUS` across the event, 2.1 s apart:

```
t= 2.1  ready=1 active=1 connL=1 connR=1 cyc=53 ...   pong 114858
t= 4.2  ready=0 active=0 connL=0 connR=0 cyc=0  ...   pong 1743
```

`pong` going 114858 -> 1743 is the proof it is a reset and not a wedge.
No panic text, no fault code, no LED error pattern reported over the
wire — a silent reset, consistent with a HardFault reaching the reset
vector.

## What is and is not affected — MEASURED, one session, one board

All rows measured gopiv 2026-09-01 over the magni farm serial daemon
(`captures/` not needed; the raw transcript is in this session's
`reports/onboard-tours-20260901/*.json`, which hold the telemetry
frames captured up to the moment each stream died).

| what was sent | resets? |
|---|---|
| `RUN:turnrate:90`, `RUN:abort`, `RUN:gap` — RUN dispatch, **no motion** | **no** |
| `MOVE_X 200 0 300 8000` then `MOVE_X 0 1571 300 8000` — **host-driven**, same two motions | **no** |
| `RUN:straight:20` — RUN dispatch **+ motion** | **yes** |
| `RUN:pivot:90` — RUN dispatch **+ motion** | **yes** |
| `RUN:square:20` — RUN dispatch **+ motion** | **yes** |

That isolates it cleanly. It is **not** the RUN dispatch path (three
non-motion RUN verbs are fine), and it is **not** the motions (the
identical straight and pivot run clean when the host issues them as
`MOVE_X`). The one thing the three failing cases share and the two
passing groups do not is `tickToCompletion()` — the busy loop in
`test/test.ts` that calls `diffDrive.driveTick()` **on the RUN fiber**.

The reset lands at or just after move COMPLETION, not at the start. In
the `RUN:square:30` capture the telemetry runs to x = 299 mm of a
commanded 300 mm leg — the leg finished — and the stream then stops
dead mid-deceleration (`vl=36 vr=46`).

## Not caused by the tour programs added this session

`RUN:straight` and `RUN:pivot` both **predate** today's work and fail
identically. The new `RUN:square` / `RUN:infinity` / `RUN:spline`
handlers parse their arguments and dispatch correctly — the banner
`DBG:tour=square:side=20` carries the parsed side length — and then hit
this same fault. They are written and build-verified but **cannot be
run to completion on this firmware**.

## Probably related, not yet proven the same bug

`clasi/issues/fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`
(and CLAUDE.md's standing hazard) records the same firmware version
hard-failing when a v6 radio exchange runs concurrently with the motor
kernel, with the regression bisected to the 3 commits in
`v0.20260829.3..master`. Both are "a second execution context touches
the motor kernel and the board dies". They differ in outcome — that one
WEDGES with the last motor command latched and wheels spinning, this
one RESETS — so they may be one root cause with two presentations, or
two faults. Worth checking `v0.20260829.3..master` for this one first.

**Safety note on the difference:** a reset stops the wheels, so this
failure mode is not dangerous the way the radio wedge is. Do not assume
that holds if the root cause turns out to be shared.

## What would settle it

1. **Is it a regression?** Run `RUN:straight:20` on a board flashed
   with `v0.20260829.3`. UNVERIFIED — tigez holds that build but was
   powered down and silent on `/dev/cu.usbmodem2121202` when this was
   written (`mbdeploy connect tigez` timed out), so the comparison was
   not made. This is the single highest-value next measurement: it
   converts "master is broken" into a 3-commit bisect.
2. If it is a regression, bisect `v0.20260829.3..master` with
   `RUN:straight:20` as the kill test — it reproduces 3/3 and takes
   about 15 s per trial.
3. Capture the fault properly rather than inferring it from the boot
   banner: attach pyOCD (recipe in the `radio-heap-corruption-hardfault`
   notes) and read the fault status registers instead of guessing at
   HardFault.

## Impact

`tests/tools/test_run_verbs.py` exists because five bench tools
(`otos_levercal.py`, `pivot_truth.py`, `truth_check.py`,
`rotation_check.py`, `turn_sweep.py`) drive the robot through exactly
these verbs. On this firmware **all five are broken on hardware** —
they will reset the board mid-measurement. That test pins the strings
they send, which is all it can do without a robot; nothing catches this.

Host-driven `MOVE_X` is unaffected, so `tests/system/run_tour.py` and
the `.tour` suite are the working path today and every tour result from
2026-09-01 (square 5.0 mm, circle 17.8 mm, infinity 25.5 mm) came
through it.
