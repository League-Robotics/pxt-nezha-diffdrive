# vevov party demo, 2026-08-28 evening — and what it found

Stakeholder ask: a continuous demo — the orange-dots rectangle forward,
back, then a cross, using world-frame go-to, until the battery dies.
Mid-session correction: "if go-to world isn't doing it for you, let's
just solve it later and use the camera and move_x." This note records
what was measured on the way, so "later" has something to start from.

Artifacts: `captures/party-20260828/` — `party.py` (GO_TO_W edition,
abandoned), `party2.py` (camera + MOVE_X edition, the one that ran),
`partylink.py` (relay link), `party.log`, `party2.log`,
`party2_fixes.jsonl` (per-pattern corner errors), `frame1.png`.

## GO_TO_W itself works — the OTOS bus around it does not

Smoke test 17:12 (`party.log` precursor, session transcript): camera
fix → `RUN:seedxy:49.9:28.8:173.4` → robot echoed
`OCAL:seeded:4991:2879:17340` → `GO_TO_W 500 300 120 10 20000` → robot
pivoted to face north and landed at camera **(50.4, 29.9)** for a target
of (50, 30): 0.4 cm. The verb, the seed and the OTOS pose were all
correct.

Six minutes later the same `RUN:seedxy` (17:18:30, `party.log`) put the
board into the CODAL I2C spin — silent on every relay AND on gauti's
USB. `STATUS` had reported `otos=1` right before, so `worldReady()`
short-circuited and the only OTOS traffic was `seedPose()` →
`OtosPort::setPose()` → `writePoseMm()`. **The wedge is not specific
to `otosBegin()`; any OTOS I2C transaction can trigger it.** `i2cf`
climbing steadily (55 → 58 → 61 across ten idle minutes; 0 → 13 in the
first two minutes of driving after a reset) is the tell that the bus is
faulting under it.

That is why GO_TO_W was set aside for the demo: not the verb, but that
every seed is a coin flip on this sensor's bus, and an unattended demo
cannot afford one.

## The wedge is cleared in three seconds from gauti — no reflash

`ssh ros@gauti`, pyserial `send_break(0.3)` on `/dev/ttyACM0`: DAPLink
resets the target, the boot banner returns
(`device NEZHA2 robot vevov …`, `OTOS:boot:id=95:connected=1`,
`ARM:-527:-12:89`) and `PING` → `pong`. Measured three times tonight
(17:22, 17:25, 17:29; `party2.log`). This supersedes "needs a reflash"
in `clasi/issues` and the memory notes. Also: the firmware DOES init
the OTOS at boot — the banner says so — contradicting the 08:23 section
of `docs/vevov-orange-dots-tour-20260828.md`.

**Never ESTOP a cold board.** BREAK → banner → `ESTOP` +
`RUN:clearestop` before any motion verb → silent again (17:25:57). The
same BREAK followed by a 2 mm `MOVE_X` (which starts the kernel and
rewrites the brick's duty) came back every time. `party2.py::gauti_reset()`
does exactly that; `recover()` tries PING → fresh relay → gauti BREAK.

## Other things that cost time tonight

- **The room lights switch themselves off roughly every ten minutes**
  (off at 17:15 after being on at 17:04; off again 17:31). A dark field
  keeps the white border tags but loses the robot's tag on its orange
  body — `frame1.png` — which looks exactly like a lost robot. A
  background loop re-asserting the Shelly every 60 s ran alongside the
  demo (`lights-keeper.out`).
- **STATUS `active=1` at rest is a stale kernel snapshot**, not a
  live move: `active` means "a wheel is measurably moving" read from
  the last published kernel output, which does not refresh until the
  next step. It cleared on the first move.
- **First move after the robot is placed by hand is a dud**: `MOVE_X
  40` completed in 0.4 s with 0.3 cm of camera-visible travel; the
  kernel's cached encoder baseline was stale relative to the wheels
  (`kernel-reads-are-published-snapshots`). The second move was real.
- **Relay pool board `zetog` never got a PONG from vevov tonight**
  (four tries, `party2.log`); `guvov` and `getez` did. The link
  helper rotates boards on a missing PONG.

## The demo that ran

`party2.py`: at each corner a camera fix at rest → pivot to the
bearing of the next dot → `MOVE_X` the distance, every drive
pre-flighted from the measured fix (targets are the dots at ±50/±30,
inside the 12 cm margin), a camera geofence that only ever sends STOP,
and per-pattern logging. Corners in the first pattern: 0.1 (after one
correction hop), 0.4, 1.6, 3.9 cm off their dots; ~2 min per rectangle
at 120 mm/s.

Per-pattern results accumulate in `party2_fixes.jsonl`.

## To solve later (the GO_TO_W thread)

1. The OTOS I2C fault rate. `i2cf` should not climb at ~1/10 s on a
   healthy bus; check the sensor's connector, pull-ups and supply
   before any firmware work. Until it is quiet, every OTOS transaction
   is a potential brick.
2. A bounded I2C wait in CODAL's `NRF52I2C::waitForStop()` (the
   `locked = 0` errata path defeats the timeout) — vendored, so a
   patch step in the build, not a source edit.
3. An in-band recovery: `RUN:clearestop` now exists; what is missing is
   a watchdog that survives the I2C spin. Gauti's BREAK is the
   workaround.

## Cycle 1 (`party2.log` 17:31–17:38, `party2_fixes.jsonl`)

| pattern | corner errors (cm) | time | notes |
|---|---|---|---|
| square forward | 0.4, 1.6, 3.9, 2.4 | 97 s | |
| square back | 0.4, 0.5, 0.8, 2.4 | 155 s | one lost radio ack; PING proved the robot fine, leg had completed |
| cross | 0.9, 0.4, 0.6, — | | one lost ack on the last pivot, recovered the same way |

Lost acks cost ~30–50 s each (three 8 s ack waits, then a PING). The
robot had executed the move both times — the ack, not the command, was
what the radio dropped. Relay board `guvov` throughout.

## Pace: the slow driver vs the fast one

Stakeholder at 17:44: "It mostly just seems to sit there, and then it
makes a run… you gotta speed it up." The time was the host, not the
robot: 5-sample fixes, STATUS polls with 3 s timeouts on a lossy
radio, a grace re-check, and a second "reached" fix after every leg.

`party2.py` (120 mm/s, fix at every corner), `party2_fixes.jsonl`:

| cycle | pattern | corner errors (cm) | time |
|---|---|---|---|
| 1 | square forward | 0.4, 1.6, 3.9, 2.4 | 97 s |
| 1 | square back | 0.4, 0.5, 0.8, 2.4 | 155 s |
| 1 | cross | 0.9, 0.4, 0.6, 1.8 | 169 s |
| 2 | square forward | 7.0, 2.3, 2.2, 3.4 | 122 s |

`party3.py` (200 mm/s legs, 150 mm/s pivots, corners planned from the
geofence thread's free at-rest camera sample, completion by timing the
profile then one 1 s STATUS confirm), `party3.log` 17:45–17:48:

| pattern | time | note |
|---|---|---|
| square forward | 54 s | corners ~5 cm off, direction flipping leg to leg |
| square back | 49 s | one 9.7 cm miss |

The flipping direction says the residual is the PIVOT landing ±3° off
at 150 mm/s, not the legs yawing (the morning's clockwise leg leak is
a consistent sign). A post-pivot re-aim from the next free sample
(nudge if > 2°) was added at 17:47; its first corner needed +5.4°.
Paused by the stakeholder at 17:48 before a full re-aimed pattern ran.

## Resume at 20:23 and the fast driver's final shape (`party3.log`)

Three bugs of the driver's own surfaced on resume and were fixed in
place (all measured in `party3.log`, 20:23–20:35):

1. **Stale camera samples.** `aprilcam camera tags` returns the daemon's
   latest detection, which can be a mid-pivot frame; single-sample
   post-pivot re-aims of −5.9° / −7.1° drove the robot to the south
   curb (x 50.1, y −40.5). Now an at-rest sample is two consecutive
   detections returned ≥0.5 s and ≥1.2 s after the robot reports
   still, agreeing within 2.5° / 1 cm (camera heading jitter at rest
   is ~2°, so 1° never passed).
2. **Lost ack could drop a move.** After an unacked pivot the drive
   reused the same sequence id; the robot discarded it as a stale
   retransmit and the pivot's late `ack` satisfied the drive's wait —
   the robot never drove (20:32:17–20:32:30). `partylink.seqd()` now
   reads STATUS `next=`: if the robot is past our id the command ran
   (adopt `next`, never resend); otherwise the same id is resent.
3. **Geofence tripped on a robot that started outside it**, and the
   "answers but does not move" detector counted the aborted 4 s
   pattern. The hard limit is now relaxed to the start position +4 cm
   for that pattern; the detector only scores patterns that ran.

Also: pivots back to 120 mm/s (150 landed 3–7° off), targets pulled
in to y = ±27 (the field is narrow in y and legs overshoot outward),
a 3 cm warm-up wiggle after every start, and `main()` now goes to
gauti when the robot is silent at startup.

Result, 20:36–20:38:

| pattern | corner errors (cm) | time |
|---|---|---|
| square forward | 0.2, 1.1, 0.4, 1.4 | 52 s |
| square back | 0.4, 3.9, 1.4, 1.7 | 59 s |
| cross | long diagonals ~3–5.5 cm | ~65 s |

A full cycle is ~3 minutes. The robot went silent for ~20–30 s twice
after a STOP (20:24:40, 20:26:46) — `i2cf` was 108 by then — and once
came back on its own, once needed the gauti BREAK. Every silence so
far has been survivable.

## Stopped by the stakeholder at 21:02

Tally for the fast driver (`party3_fixes.jsonl`, 20:23–21:02, with the
2 h pause before it): 25 patterns started, 17 completed, 48 camera-scored
corners with a median error of **2.3 cm** (90th percentile 7.6 cm), five
gauti resets. From ~20:42 the board went silent every 2–4 minutes, always
at a motion command, and every time the BREAK brought it back — the
signature of a supply sagging under motor inrush (`i2cf` climbing to >100
between resets). Battery state was never measured; a fresh battery before
the next run would settle whether that reading is right.
