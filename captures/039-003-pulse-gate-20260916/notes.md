# Sprint 039 ticket 003 — per-pulse characterization gate, vevov, 2026-09-16

**VERDICT: GO.** Accepted operating point: **amplitude 15 %, width 2
ticks**, which gives a 1.79 mm per-pulse step with sd/mean 0.08 and no
dead pulses, warm or cold.

Team-lead hardware session. Robot **vevov** on the MAIN playfield,
wheels down, alone on the table (gopiv lifted off by the stakeholder;
camera confirmed only tag 53 present). Reached over the farm serial
daemon at `null.local:41285` — vevov migrated from zilch to null earlier
the same day.

Camera: **arducam-ov9782-usb-camera (number 4)**, stakeholder-pinned.
Both ov9281 (2) and ov9782 (4) are registered to `main-playfield`; 4 is
the one this project's notes name as the overhead camera. Both report
`calibration_stale`, and the nezha-robot-template session measured this
camera **over-reading distance by 0.41 %** against a tape — carried
below as a known systematic, never attributed to the robot.

Firmware: `id diffdrive vevov-pulsefix0916 1.20260914.1 vevov`.

## The instrument had to be fixed first

The pulse verb shipped in ticket 001 returned EMPTY values on hardware:

```
TX  RUN pulse 25 0 1 #21
RX  ret left_counts= right_counts= left_mm= right_mm= #21
```

`execPulse` formatted with `%.1f`/`%.2f`, and the target's newlib-nano
printf has no float conversion linked in. Host tests passed throughout
because a desktop libc formats floats correctly — the defect was
unreachable from the host harness by construction. Fixed in commit
`c49bc58` (integer-only fields, plus a source-pin test that fails the
build on any `%f`/`%g`/`%e` in the wire layer). The reply is now:

```
ret left_counts=<int> right_counts=<int> left_mm_x100=<int> right_mm_x100=<int> #<id>
```

**The pulses themselves were always working.** Before the fix, the
camera measured 21 single-wheel pulses moving the robot 1.55 cm of arc
(~0.74 mm each) while the reply carried no numbers.

## The displacement map

Single-wheel pulses unless noted. "dead" counts pulses that moved the
wheel less than 0.05 mm. Raw per-pulse samples are in the `.json` files
beside this note; the harness is `pulsesweep.py`, copied here.

| amp % | width | wheel | n | mean [mm] | sd [mm] | sd/mean | dead | verdict |
|---|---|---|---|---|---|---|---|---|
| 15 | 1 | left | 5 | 0.44 | 0.56 | 1.27 | 3/5 | bimodal — reject |
| 20 | 1 | left | 20 | 1.06 | 0.69 | 0.65 | 4/20 | too scattered |
| 25 | 1 | left | 20 | 1.61 | 1.27 | 0.79 | 6/20 | too scattered |
| 20 | 2 | left | 20 | 2.69 | 0.19 | **0.07** | 0/20 | repeatable, but ABOVE the 2 mm band |
| **15** | **2** | **left** | **20** | **1.79** | **0.15** | **0.08** | **0/20** | **ACCEPT** |
| **15** | **2** | **right** | **20** | **1.79** | **0.42** | **0.24** | **0/20** | **ACCEPT** |
| 15 | 2 | left, COLD | 12 | 1.80 | 0.26 | 0.14 | 0/12 | ACCEPT |
| 15 | 2 | both | 20 | 2.50 | 0.37 | 0.15 | 0/20 | camera cross-check run |

**MEASURED vevov 2026-09-16 (this directory).** The acceptance bar from
the ticket is a repeatable 0.3–2 mm increment with sd/mean <= 0.4.

### What the map says

- **Width 1 is unusable at every amplitude tried.** It is the classic
  nothing-or-lurch signature: raising the amplitude from 15 to 25 %
  raised the mean but did NOT reduce the scatter or the dead-pulse rate
  (0.65 -> 0.79, 4/20 -> 6/20). A single 24 ms tick is simply not enough
  impulse to break stiction reliably.
- **Width 2 transforms it.** At the same 15 % amplitude, going from one
  tick to two takes sd/mean from 1.27 to 0.08 and dead pulses from 60 %
  to zero. This is the whole finding: pulse WIDTH, not amplitude, is
  what buys repeatability here.
- **Amplitude then sets the step size** cleanly: at width 2, 15 % gives
  1.79 mm and 20 % gives 2.69 mm, both highly repeatable. 20 % is
  rejected only for being outside the requested band, not for quality.
- **Per-wheel asymmetry: none in magnitude, some in consistency.** Both
  wheels mean exactly 1.79 mm; the right wheel is noisier (sd/mean 0.24
  vs 0.08). Ticket 004 must not assume the wheels are interchangeable in
  scatter, though a 50/50 split of magnitude looks justified.
- **Cold does not matter at the accepted point.** After 150 s idle,
  1.80 mm vs 1.79 mm warm, still zero dead. That is the condition
  calibrateL actually nudges in.

## Camera cross-check (ground truth for the encoder numbers)

Both wheels, 15 % / width 2, 20 pulses, camera fixes either side:

```
before  tag 53 world (9.805, -2.251)
after   tag 53 world (9.663, -7.224)
displacement 49.75 mm
encoder-reported total ~50.0 mm (20 x 2.50 mm)
```

Agreement **within 0.5 %**, and the camera's own 0.41 % over-read
accounts for most of it. The per-pulse encoder figures above are
therefore trustworthy, which matters because a single 1.79 mm pulse is
far below what the camera could resolve on its own.

## What this means for tickets 004 and 005

- Recommended default: **amplitude 15 %, width 2**. Step 1.79 mm per
  wheel.
- **Rotation resolution:** a single-wheel pulse pivots the robot about
  the other wheel by roughly `1.79 / b`, which at vevov's measured
  111 mm track is about **0.9° per pulse**. calibrateL's tolerance is
  1°, so the finest available nudge only just fits inside it. The
  stepper must therefore be able to stop within one step of target
  rather than overshooting and correcting.
- Width 1 must not be offered as a "finer" option. It is not finer, it
  is unreliable.
- A narrower step, if one is wanted, should be sought BELOW 15 % at
  width 2 (untested), not at width 1.

## Coverage this run does NOT have

Stated plainly so nobody reads the map as complete:

- **Widths 3 and amplitudes 35/50 were not run.** Once width 2 at 15 %
  passed inside the band, larger and wider cells could only produce
  bigger steps, which is the wrong direction for a nudge.
- **Cold was tested at the accepted point only** (left wheel, 12
  pulses), not per cell.
- **Per-cell camera cross-checks were not taken** — one cumulative
  check was run, at the accepted operating point. Per-pulse camera
  verification is not possible at this scale: 1.79 mm is below the
  camera's noise.
- Every cell is LEFT wheel except the two noted, and all on this one
  surface.

## Caveats carried from the session

- **The pre-flight dance FAILED on pivot magnitude and was overridden**
  for this ticket, with the stakeholder's explicit go-ahead. Conventions
  all passed (left is left, forward is forward, distances accurate to
  0.1 cm, bearings within 3°, returns home within 1 cm); only rotation
  magnitude failed, and this gate fires single-wheel pulses in a
  straight line and never pivots. Recorded as an override, not a pass.
- **vevov's geometry is wrong in the flashed build.** trackwidth is
  baked 128.0 mm; the stakeholder measured **111 mm** with calipers on
  2026-09-16. Rotational slip was live-SET from 1.1013 to 1.0153 and
  stop_distance from 0 to 1.51 mm during this session (suggested by
  `calibrate.py turns`), which improved the dance from -36/-41/-17 to
  -9/-31/-6 but did not make it pass. **Those SETs are live-only and die
  on reboot.** None of this affects the map above, which is pure
  straight-line wheel travel, but vevov should not be used for
  rotation-dependent work until the geometry is re-fitted and baked.
