# vevov — two square tours on the playfield, 2026-08-29

Stakeholder ask: drive vevov around the field, "a couple square tours",
and validate that everything is working. Two tours ran, both scored by
the overhead camera. **Everything works**: all 16 tour moves acked on
the first try, legs came out within 0.7 % of commanded, pivots landed
at 90 ± 1° physical, and both tours closed within 4.5 cm of their start
over 320 cm of driving. The residual is a consistent 4–5 cm northward
drift by the SE corner, and it repeats tour to tour.

Artifacts: `captures/vevov-square-20260829/` — `drive_square.py` (the
driver), `camstream.py` (registry-safe camera reader), `analyze.py`
(scoring + chart inputs), `run2.json` (tour A), `run3.json` (tour B),
`run1.json`/`run1.log` (first park attempts), `*.log`, `tour{A,B}_*.csv`,
`vevov_square_tour{A,B}.png`. Every number below is from those files.

## Setup

| | |
|---|---|
| robot | vevov, firmware `ver 0.20260829.1` (make_deploy build: geometry bake + 70 mm/s speed floor), `otos=1` at boot |
| link | vevov's USB is held by an `mbdeploy serve` fleet daemon on host **`null`** (192.168.4.50, reverse DNS `null.`); `dns-sd -L vevov _mbserial._tcp local.` → `null.local:36807` (dynamic). One raw TCP socket, sequenced v6 verbs, `TLM FULL` streaming at ~18 Hz. Connecting does not reset the target: `cyc` ran 0 → 8162 across six sessions. |
| camera | OV9782, tag 53 with the daemon's registered mount (`-5.34, -0.19, z 11.86, yaw −π/2`, read with `list_tag_parameters` 11:25). Tag 1 read (0.1, −0.1). Calibration flagged stale as usual. |
| lights | Shelly keeper loop (60 s) ran throughout — see "what cost time" |
| route | the four orange dots: park on NE (50, 30) facing west, then west 100 cm, south 60, east 100, north 60, four CCW +90° corners |

Recipe, per `reports/tovez-movex-square-tour-20260828.md` run 4 and
`.claude/rules/playfield-testing.md`:

- camera at the **start** (park onto the dot, pre-flight the whole
  projected path from the *measured* pose against the 12 cm margin) and
  at the **end** (score); during the tour it only records and guards the
  hard limit — nothing it sees reaches the robot mid-tour;
- legs `MOVE_X <mm> 0 200 15000`; corners pivot to the **absolute
  believed cardinal** (`h_start + n·90°` from telemetry) at 120 mm/s —
  closed loop on the robot's own heading, not the camera;
- completion from telemetry stillness + 0.7 s grace re-check;
- net-zero warm-up before the first tour (skipped when the kernel had
  already stepped this session).

## Results

| | tour A (`run2.json`, 11:33:56) | tour B (`run3.json`, 11:39:13) |
|---|---|---|
| start (camera) | (49.0, 30.6) @ −179.2° | (49.4, 30.2) @ −178.9° |
| end (camera) | (48.3, 35.0) @ −174.7° | (49.7, 33.6) @ −176.3° |
| **closure** (camera) | **4.5 cm** | **3.4 cm** |
| closure (encoder) | 3.8 cm | 3.3 cm |
| end heading vs start (camera) | +4.5° | +2.5° |
| believed net rotation | +362.0° | +361.4° |
| corner error vs dots NW / SW / SE / NE | 1.6 / 1.6 / **5.0 / 5.2** | 1.4 / 2.1 / **4.1 / 3.6** |
| total travel, believed vs camera | 320.3 vs 321.8 cm (+0.49 %) | 320.4 vs 321.4 cm (+0.31 %) |
| duration | 40 s | 40 s |
| acks first try | 8 / 8 | 8 / 8 |
| telemetry frames | 554 / 39.9 s, 0 malformed | 550 / 39.5 s, 0 malformed |
| `i2cf` | 8 → 24 | 32 → 51 |

![tour A](../captures/vevov-square-20260829/vevov_square_tourA.png)

![tour B](../captures/vevov-square-20260829/vevov_square_tourB.png)

Blue (encoder odometry, rigidly aligned to the camera start fix) and
green (camera) lie on top of each other on both tours. Orange is the
OTOS, aligned the same way from its own first sample; it is the one
track that does not fit (below).

### Per move (`analyze.py`)

Camera figures for legs are from the at-rest corner fixes bracketing
the leg (0.7 s settle, 1.2 s window, 2–4 fresh samples each — so ±1°
on heading). Pivot camera figures use the samples between the pivot's
stillness and the next leg's send (0.4 s, 2–4 samples).

| move | commanded | believed | camera | note |
|---|---|---|---|---|
| **A** leg 1 | 1000 mm | 100.0 cm | 100.3 cm | direction −179.2° vs heading −179.2° |
| A pivot 1 | +89.7° | +91.6° | +90.6° | in-place slip 0.4 cm |
| A leg 2 | 600 | 60.1 | 60.4 | −0.3° |
| A pivot 2 | +87.1° | +89.2° | +90.7° | slip 0.3 |
| A leg 3 | 1000 | 100.1 | 100.7 | direction +3.4° vs heading +3.7° |
| A pivot 3 | +87.4° | +89.3° | +90.1° | slip 0.3 |
| A leg 4 | 600 | 60.1 | 60.4 | −0.1° |
| A pivot 4 | +87.4° | +89.4° | +93.6° | n=2 samples |
| **B** leg 1 | 1000 | 100.1 | 100.3 | −0.4° |
| B pivot 1 | +89.4° | +91.5° | +93.7° | n=2 |
| B leg 2 | 600 | 60.0 | 60.4 | −2.1° |
| B pivot 2 | +87.4° | +89.3° | +90.0° | slip 0.2 |
| B leg 3 | 1000 | 100.2 | 100.7 | −0.3° |
| B pivot 3 | +87.4° | +89.3° | — | no at-rest sample |
| B leg 4 | 600 | 60.1 | 60.1 | −0.0° |
| B pivot 4 | +87.8° | +89.2° | +90.0° | slip 0.2 |

## What the numbers say

1. **Distance is calibrated.** 100 cm legs: encoder 100.0–100.2 cm,
   camera 100.3–100.7 cm. 60 cm legs: 60.0–60.1 vs 60.1–60.4. Whole
   tour +0.3 / +0.5 %. Legs run straight along their start heading
   (direction − heading within ±0.4° except one −2.1°).
2. **Every MOVE_X pivot overshoots its command by +1.9…+2.1° in the
   robot's own encoder frame**, consistently (eight of eight). The
   closed-loop cardinal targeting sees that and asks the next pivot for
   ~87.4° instead of 90°, so it is absorbed — except at the last
   corner, hence "believed net +362 / +361.4". This is the +2 %/90°
   MOVE_X over-rotation `reports/tovez-taper-stall-20260829.md` noted on
   the bench; here it is on the floor, camera-confirmed to be roughly
   physical (pivots land 90.0–90.7° where the samples are good). If it
   ever matters, aim pivots 2 % short — the controller's own encoders
   see the overshoot, so the firmware could do it itself.
3. **Physical over-rotation the encoders never see: +2.5° (A) and
   +1.1° (B) per tour** — camera end-heading minus believed net
   rotation. Splitting it between legs and pivots needs better than
   the 2–4-sample corner fixes here (see the ±3° pivot-4 readings);
   the split is inside camera noise. It is what puts the robot ~3°
   left of east on leg 3 and lands SE/NE 4–5 cm north of their dots on
   both tours. Pivot slip is 0.1–0.4 cm — so the tag-53 mount
   registration in the daemon is right, and pivots do not translate.
4. **The OTOS is the weak instrument on this run.** Its heading drifts
   +6.5° (A) / +4.4° (B) over one tour relative to the encoders, and its
   closure is 82 / 75 mm against the encoders' 38 / 33 mm and the
   camera's 45 / 34 mm. UNVERIFIED whether that is angular scale, the
   lever arm, or bus faults (`i2cf` climbed 8 → 55 across ~10 min of
   driving, no wedge). Do not seed world-frame navigation from it
   without checking this first.
5. **`i2cf` climbs ~2/min while driving and the board never wedged**
   — 22 minutes of session, ~80 sequenced commands, one `HELLO` per
   session. No gauti reset was needed (and none was available: no ssh
   key for `null`).

Robot left parked on the NE dot: camera (49.8, 30.2) @ 176°,
`STATUS ready=1 active=0 connL=1 connR=1 otos=1 i2cf=55 cyc=8162
tlm=off`, `PING` → `pong`.

## What cost time (each one is a trap for the next session)

- **The field went dark while the Shelly said `output: true`.**
  11:29:01–~11:30:30: camera lost tag 53 and the east/south ArUco
  border; a frame showed a black field with the robot's LEDs glowing;
  `Switch.GetStatus` said on the whole time and `Switch.Set on` replied
  `was_on: true`. The next frame at 11:30:31 was bright. **The frame is
  the truth, not the relay status.** The keeper loop cannot catch this
  case.
- **Telemetry decodes need the `thdr` header, which the firmware
  re-emits only about every ~19 frames (~1 s).** A 1 s wait after `TLM
  FULL` decoded 18 frames on one run and 0 on the next (13 orphan
  frames). Wait for the header, not for a fixed time.
- **The camera stream starts slow and re-serves stale detections.**
  First sample took 1–2 s usually, once 34 s; the first seconds run at
  ~1 Hz before settling at 4–5 Hz. The daemon also repeats an older
  detection byte-identically a few seconds later, ~4° off the live
  yaw (`run1.json` 11:31:49 and 11:31:52 both `44.90 29.46 171.76`).
  Dedupe exact repeats; use a circular median over ≥6 fresh samples
  for an at-rest heading.
- **`tools/camlink.py` re-registers tag 53 with the stale `-3.61 cm`
  mount every time it starts** (`MOUNTS` table), silently replacing
  the daemon's re-measured `-5.34`. Every `tools/camproc.Cam` user
  inherits that. `camstream.py` here reads without registering.
- **The dots leave 2.65 cm of y-slack inside the 12 cm margin**, so
  the pre-flight from a measured pose refuses the tour unless the park
  heading is within ~1.5° of west — and camera heading at rest is only
  good to ~1° with a good fix. The park loop needed 2–6 pivots per
  tour and failed once (11:40, gave up at 176.8°). Two things made it
  worse: single-sample fixes (fixed above), and **small MOVE_X pivots
  over-rotating ~2× on camera** (−3.5° → −7.9°, +4.4° → +10.1°, −5.4°
  → −8.3°, `run3.log` 11:40:13–11:40:21) while 18–90° pivots overshoot
  by a roughly constant +3.5–4.5°. UNVERIFIED on the encoder side —
  the driver kept telemetry frames only inside tours, not for park
  moves — so the next session should log believed heading across a
  few 2–5° pivots before tuning anything. A start pose *outside* the
  margin (the robot ends 3–5 cm north of the dot) also needs the
  pre-flight to allow an inward move; the driver has that exception.
- `null` (192.168.4.50) refuses my ssh keys (`ros`, `jtl`) and gauti
  timed out on 2026-08-29, so there is **no BREAK-reset path** for a
  wedged board from this machine today; a reflash over
  `mbdeploy deploy --remote` would be the recovery.
