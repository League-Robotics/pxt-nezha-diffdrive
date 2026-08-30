# vevov tour C — is the new firmware on the robot, and which carrier to trust for telemetry (2026-08-29)

**Short version.** Yes, the recent changes are on vevov and they work on
the floor: `VER 0.20260829.1`, `speed_floor` reads back at 70 mm/s and
`rotational_slip` at vevov's own 0.987, and **not one of the 12 straight
legs across three tours shows the old end-of-leg stall-and-bump** —
final errors are +0.3…+1.6 mm where the pre-change baseline was 6–9 mm
short with a restart pulse. Tour C closed at **2.8 cm** with every
corner inside 2.6 cm. For telemetry, the on-robot serial path (the
`mbdeploy` daemon on `null`) was **lossless** (956/956 frames); the
radio relay lost **12.7 %** of frames (18.8 % while moving), but every
frame it did deliver was byte-identical and arrived at the same time.
One new number to carry forward: **every MOVE_X pivot lands a constant
≈ +2° past its command, in the robot's own encoders**, 3° pivots and
90° pivots alike.

Companion report for the first two tours: [vevov-square-tours-20260829.md](vevov-square-tours-20260829.md).
Artifacts: `captures/vevov-square-20260829/` — `runC2.json` (tour C,
with every telemetry frame of the session on both carriers, the camera
track, the `GET` dump), `runC.json` (the first attempt: config dump and
five uncompensated park pivots), `analyze_c.py` (everything below),
`drive_square.py`, `tourC_*.csv`, `vevov_square_tourC.png`.

## 1. Is the recent firmware on the robot?

The robot reports `ver 0.20260829.1`, the version on disk. The only
source changes since that build (`git diff 1ff8bee..HEAD -- src`) are
two new blocks in `src/blocks/motion.ts` (`startDrive`, `whileDriving`)
that the tour path never calls, so the deployed hex is behaviourally
current and I did not reflash it.

Read back over the wire (`runC2.json`, 11:55:49; internal units are
counts at 12.76 counts/mm, so 893.2 → 70 mm/s):

| field | robot says | expected | |
|---|---|---|---|
| `speed_floor` | 893.2 (**70 mm/s**) | 893.2 — commit 9c703e9 raised the default from 255.2 (20 mm/s) | ✓ |
| `rotational_slip` | **0.987** | 0.987, vevov's `firmware_bake` (fleet default 0.952) | ✓ |
| `pid_ki` / `pid_i_max` | 6.0 / 765.6 (60 mm/s) | unchanged defaults | ✓ |
| `pos_err_max` | 127.6 (10 mm) | default | ✓ |
| `crawl_pulse` | 0 | default | ✓ |
| `default_cruise` | 150 | default | ✓ |

### The speed-floor change, on the floor

`reports/tovez-taper-stall-20260829.md` measured the old
behaviour on the bench: the wheel braked to a near-stop 6–9 mm short,
sat, then jumped the rest in one stiction pulse; `speed_floor 893`
removed it. Here is the same decoder on vevov's twelve loaded legs
(`analyze_c.py::leg_ends`; encoder mm; "bump" = travel after the first
stop, "peak" = max wheel speed after the stop):

| tour | leg | target | stopped at | short | bump | peak after stop | final error |
|---|---|---|---|---|---|---|---|
| A | 1 | 1000 | 1000.4 | −0.4 | 0.0 | 0 | +0.4 |
| A | 2 | 600 | 600.8 | −0.8 | 0.0 | 0 | +0.8 |
| A | 3 | 1000 | 1000.7 | −0.7 | 0.0 | 0 | +0.7 |
| A | 4 | 600 | 600.8 | −0.8 | 0.0 | 0 | +0.8 |
| B | 1 | 1000 | 1001.4 | −1.4 | 0.0 | 0 | +1.4 |
| B | 2 | 600 | 600.3 | −0.3 | 0.0 | 0 | +0.3 |
| B | 3 | 1000 | 1001.6 | −1.6 | 0.0 | 0 | +1.6 |
| B | 4 | 600 | 601.0 | −1.0 | 0.0 | 0 | +1.0 |
| C | 1 | 1000 | 1000.6 | −0.6 | 0.0 | 0 | +0.6 |
| C | 2 | 600 | 601.2 | −1.2 | 0.0 | 0 | +1.2 |
| C | 3 | 1000 | 1001.5 | −1.5 | 0.0 | 0 | +1.5 |
| C | 4 | 600 | 601.4 | −1.4 | 0.0 | 0 | +1.4 |

No bump, no dead time, every leg lands +0.3…+1.6 mm long. Camera agrees
within its own resolution (legs 100.3–100.8 cm for 100 commanded). The
wheel-speed panel of the chart shows the same thing: clean ramps down to
zero at every leg end.

## 2. Tour C

Same recipe as A and B (park on the NE dot facing west, pre-flight the
whole projected path, MOVE_X legs at 200 mm/s, corners pivot to the
absolute believed cardinal at 120 mm/s, camera at start and end only).

![tour C](../captures/vevov-square-20260829/vevov_square_tourC.png)

| | tour A | tour B | **tour C** |
|---|---|---|---|
| closure (camera) | 4.5 cm | 3.4 cm | **2.8 cm** |
| end heading vs start | +4.5° | +2.5° | **−0.5°** |
| corners NW / SW / SE / NE | 1.6 / 1.6 / 5.0 / 5.2 | 1.4 / 2.1 / 4.1 / 3.6 | **2.4 / 2.1 / 2.4 / 2.6** |
| travel, believed vs camera | 320.3 / 321.8 cm | 320.4 / 321.4 | 320.5 / 321.9 (+0.44 %) |
| acks first try | 8/8 | 8/8 | 8/8 |
| `i2cf` during tour | 8 → 24 | 32 → 51 | 56 → 72 |

Per move (camera figures from at-rest fixes, 2–5 samples each):

| move | commanded | believed | camera |
|---|---|---|---|
| leg 1 | 1000 mm | 100.1 cm | 100.3 cm |
| pivot 1 | +89.3° | +91.0° | — |
| leg 2 | 600 | 60.1 | 60.2 |
| pivot 2 | +87.8° | +89.4° | +89.5° (slip 0.3 cm) |
| leg 3 | 1000 | 100.2 | 100.8 |
| pivot 3 | +87.1° | +89.1° | +88.3° (slip 0.4) |
| leg 4 | 600 | 60.1 | 60.6 |
| pivot 4 | +87.3° | +89.2° | +89.2° (slip 0.3) |

Tour C's better corners are the park's doing, not the robot's: it
started at −179.9° instead of −179.2°/−178.9°, so the heading budget
that pushed A and B 4–5 cm north by the SE corner was spent before the
tour began. The OTOS again drifted (+4.4° heading, 64 mm closure vs the
encoders' 28 mm) — still not a sensor to seed from.

## 3. Telemetry carriers: on-robot serial vs radio

The robot carries its own radio, micro:bit and Pi (`null`, a Pi Zero W
at 192.168.4.50, `ssh jtl@` works). The Pi's root `mbdeploy.service`
holds `/dev/ttyACM0` open and pipes it to a TCP port advertised as
`vevov._mbserial._tcp` — that daemon **is** the on-robot serial tap.
There is no `socat` on `null` and `jtl` has no sudo, so I could not
stop the daemon to put a separate `socat`/`nc` on the port, and a second
reader on the same tty would only split bytes with the daemon. What I
could do instead was subscribe `TLM FULL` on **both** transports at once
during tour C — commands over the daemon socket, a relay-pool micro:bit
(`gozop`, channel 4) listening over the radio — and compare the same
frames. The two transports have separate v6 sequence spaces (a `HELLO`
on the radio left the socket's `next=` at 9), which is what makes the
dual subscription legal.

Common window 66.8 s of device time, park + tour (`analyze_c.py::carriers`):

| carrier | frames | lost | loss | rate | longest gap | malformed |
|---|---|---|---|---|---|---|
| daemon socket on `null` (serial) | 956 | **0** | **0.0 %** | 14.3 Hz | 130 ms | 0 |
| radio relay `gozop` | 835 | 121 | **12.7 %** | 12.5 Hz | 692 ms | 0 |

- Loss on the radio is worse while the robot moves: **18.8 %** of the
  daemon's in-motion frames never arrived vs 10.0 % at rest.
- **Latency is a wash**: for the 835 frames both carriers delivered,
  radio arrival minus daemon arrival is median −1 ms (p10 −7, p90 +3 ms).
  The radio is not slower; it just drops.
- Every matched frame's payload was identical (0 of 835 differed), and
  the radio produced 0 malformed lines this session — so what the
  radio delivers can be trusted; what it drops is simply gone.
- The daemon path's own cadence: median 72 ms between frames under
  motion (13.9–14.3 Hz), 56 ms idle. That is the firmware's pacing, not
  the link — the same rate on both carriers before drops.

So for anything scored from telemetry (leg ends, pivot overshoot,
stall diagnosis) collect on the serial path. The radio is fine for
commanding and for a rough picture, and for the party-demo style of
driving it was adequate — but a 692 ms hole mid-pivot is exactly where
an end-of-move analysis would go wrong.

## 4. A constant +2° per pivot, in the encoders

Chasing the park heading this morning looked like camera noise. With
every frame of the session saved, it is not:

| pivot (`runC.json` / `runC2.json`) | commanded | believed (encoder) | camera |
|---|---|---|---|
| park face | +3.2° | +5.1° (+1.9) | +5.9° |
| park face | −2.6° | −4.4° (−1.8) | −5.2° |
| park face | +2.6° | +5.0° (+2.4) | +6.1° |
| park face | −3.5° | −5.7° (−2.2) | −7.0° |
| park face | +3.6° | +6.3° (+2.7) | +8.2° |
| park face (compensated) | −1.1° | −2.4° (−1.3) | −0.0° |
| park pivot | −7.2° | −9.6° (−2.5) | −8.7° |
| park face (compensated) | +5.1° | +7.6° (+2.5) | +7.3° |
| tour corners (C) | +89.3 / +87.8 / +87.1 / +87.3° | +91.0 / +89.4 / +89.1 / +89.2° (+1.6…+2.0) | |

The overshoot does not scale with the pivot: 3° and 90° both land about
2° long. In wheel terms that is 2–3 mm past the target per wheel —
the size of one kernel tick at the new 70 mm/s floor (70 mm/s × 33 ms
≈ 2.3 mm), which is the obvious suspect (UNVERIFIED — settle it by
re-running a few 3° pivots with `SET speed_floor 255` and watching the
believed Δh). The frame-by-frame trace of a 3° pivot shows the whole
move done in 0.25 s with the wheels going 0 → 47 mm/s → 0 and stopping
exactly at the commanded-plus-2°. Two consequences:

- closed-loop cardinal corners absorb it (the tour pivots are commanded
  at ~87.5° and land on 90); open-loop `+90` pivots would stack +2°/corner;
- the park loop now commands `residual − 2°·sign(residual)` (a token
  0.1° for residuals under 2.1°) and converged in two pivots where the
  uncompensated loop oscillated for five (`drive_square.py::park`).

The firmware sees this in its own encoders, so it could subtract it
itself; or the floor could be lowered for the last few mm of a
rotation. Either is a firmware change and out of scope here.

## 5. Other things measured on the way

- `i2cf` rose 55 → 72 across the session (~1/min while driving); the
  board never wedged, 20 sequenced commands per session all acked first
  try, and no gauti-style reset was needed.
- The camera's at-rest fix now uses ≥ 6 fresh samples with duplicates
  dropped (the daemon re-serves stale detections); heading agreed with
  the encoders to ~1° on every pivot where it had ≥ 4 samples.
- The lights held for the whole session this time; no keeper loop was
  running. The morning's dark-field-while-Shelly-says-on episode is in
  the companion report.

Robot left parked on the NE dot: camera (50.0, 32.8) @ 179.4°,
`STATUS ready=1 active=0 connL=1 connR=1 otos=1 i2cf=72 cyc=11676 tlm=off`.
