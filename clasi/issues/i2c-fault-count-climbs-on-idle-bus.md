---
status: pending
sprint: ''
---

# `i2cf` climbs steadily on a largely idle I2C bus

Priority: **Medium** — not blocking anything today, but it is an error counter
that increases while the robot does nothing, which is never benign and is
currently unexplained.

## What was observed

vevov, 2026-08-25, driven over the zavaz radio relay with the robot on the mat.
The `i2cf` column of the telemetry frame (`thdr seq now flags x y h ox oy oh vl
vr i2cf`) over roughly ten minutes of light use:

```
t = 0 min    i2cf = 60     (already 60 at first contact this session)
during a commanded 20 cm drive      60 -> 62     (+2)
t = ~10 min  i2cf = 107    (+45 more, much of it while parked)
```

The robot was stationary for the majority of that window. Two commanded
`RUN:straight:20` legs and a handful of `RUN:fix` / `RUN:probe` calls account
for only a small part of the increase.

## Why it matters

1. **It is monotonic and untriggered.** A fault counter that only advances
   during motion would point at the known Phase-F select/read interposition
   hazard (an OTOS transaction landing inside the Nezha encoder's select->read
   window). Advancing at rest does not fit that story.
2. **Nothing surfaces it.** `i2cf` is a telemetry column; no banner, no
   `STATUS` flag, and no test asserts a bound on it. A robot could accumulate
   thousands of I2C faults across a session and every artifact would look
   normal.
3. **It muddies every campaign** that runs on this hardware. If faults are
   being absorbed silently, "the sensor answered" and "the sensor answered
   correctly" are not the same claim, and no current tooling separates them.

## What is NOT known

- Whether the count is per-transaction retries (benign, bus noise absorbed by
  a retry layer) or genuinely dropped transactions (not benign).
- Whether the rate is normal for this hardware. **There is no baseline.** No
  prior session recorded `i2cf` over time, so "60 at first contact" cannot be
  compared to anything.
- Whether it is specific to vevov, to its older firmware build, or general.
  vevov runs the 12-column `POSE` build and does not answer `STATUS`; this has
  not been checked against master.
- Whether it correlates with the stale telemetry projection recorded in
  `tour-corner-fixes-are-stale-cache.md`. Both involve the OTOS I2C path and
  both were seen in the same session, but no causal link has been shown and
  they should not be assumed related.

## Suggested first steps

1. Find where `i2cf` is incremented in `src/` and establish what one count
   actually means — a retry, or a lost transaction. That single fact decides
   whether this is noise or a real defect, and it is a source read, not a
   bench session.
2. Record `i2cf` at the start and end of every run in the sprint 011 campaign
   procedures (already required there) so a baseline finally exists.
3. Only then decide whether a rate bound is worth asserting anywhere.

## Related

- `tour-corner-fixes-are-stale-cache.md` — same OTOS I2C path, same session.
- `unpowered-nezha-brick-wedges-program-at-boot.md` — the other place I2C
  health silently changes what the program reports.

---

## Related observation (2026-08-25): OTOS probe wedges the program on current firmware

While attempting the master-firmware retest, vevov was flashed with a current
build and then wedged by the first command that touches I2C.

Sequence, all over USB (`/dev/cu.usbmodem2121202`, confirmed by `mbdeploy
probe` — note the `config/devices.json` registry is STALE and lists vevov at a
port that no longer exists; always probe):

```
flash ok (386048 bytes programmed, after a CTRL-AP mass-erase recovery)
STATUS   -> status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0
            i2cf=0 cyc=0 tlm=off next=2
TLM FULL -> thdr seq now flags x y h ox oy oh vl vr i2cf cyc posl posr dutl
            dutr lexc wrng cycovr        (20 columns -- current firmware)
            t 1 47300 0 0 0 ...          (frames streaming normally)
RUN:probe -> OPROBE:95:1                 (0x5F product id, connected)
RUN:fix   -> OCAL:now:0:0:-1             (pose ~zero, chip freshly begun)
...then NOTHING. No telemetry, no STATUS, no response to any command.
```

The board still enumerates on USB afterwards (`mbdeploy probe` lists it
`CONN yes`), so DAPLink is alive and the **application program** is what is
stuck — the documented wedge signature, not a dead board.

`ready=0 cyc=0` in that STATUS is the never-ticked state, not a fault; sprint
010 added `cyc=` specifically so a never-ticked robot is distinguishable from a
dead one, and it did its job here.

### Why this matters against sprint 010's finding

Sprint 010 ticket 004 established, by reading the pinned
`codal-nrf52 @ 1fbb7240` source, that a stuck I2C call is **bounded at ~11 s**,
not infinite. That bound may well hold per call — but it did not restore a
usable program here. The board stayed unresponsive across several commands and
well over a minute. A per-call bound is not the same property as recovery, and
nothing currently distinguishes them from the outside.

### Two things NOT established — do not read past them

1. **The Nezha brick's power state was not verified.** vevov was on the bench,
   not on the mat, and the brick is separately powered. An unpowered brick
   wedging I2C is the known, expected behaviour
   (`unpowered-nezha-brick-wedges-program-at-boot.md`) and is the most likely
   explanation by far.
2. **The flashed build was an unmerged mid-refactor build** — sprint 012's
   branch after the `sim.ts` extraction, not master. The split is not a
   plausible cause (the program booted, answered STATUS, and streamed correct
   20-column telemetry before any I2C command; a load-order break would have
   failed at startup) but it cannot be formally excluded from this run alone.
   Re-test against a pre-split master hex before drawing any conclusion about
   the refactor.

### The master-firmware retest is still OPEN

The question sprint 011 left open — whether the stale `ox`/`oy`/`oh`
projection exists on current firmware — was NOT answered. It needs:
- vevov's Nezha brick powered, and
- vevov on the mat in camera view (the test needs real chassis motion; on a
  stand a frozen OTOS reading is *correct* behaviour and the test cannot
  distinguish the two — the exact ambiguity that produced the fabricated
  0.6 mm closure).
