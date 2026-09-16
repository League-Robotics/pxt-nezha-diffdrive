# Sprint 039 ticket 002 — hardware repro results (vevov, 2026-09-15/16)

Team-lead session. **vevov on a bench, WHEELS UP**, off the playfield and
not visible to any camera (the stakeholder had removed it from the main
field hours earlier; tovez was on that field instead). Reached over
zilch's serial daemon at 192.168.4.52:40881.

Build flashed: `.tmp/deploy-head/built/binary.hex` from
`sprint/039-nudge-mode-sub-floor-micro-moves-for-calibratel`, built with
`tools/make_deploy.py --robot vevov --profile-suffix=-nudgehang0915`.

```
id diffdrive vevov-nudgehang0915 1.20260914.1 vevov
```

The `-nudgehang0915` profile suffix is what distinguishes this build from
the one that produced `captures/calibratel-vevov-20260915/bench-log.md`
(`calibrate-l-bench 1.20260912.8`).

## Result 1 — Defect 1 (stale STATUS active) is FIXED. CONFIRMED on hardware.

**MEASURED vevov 2026-09-16 (this file).** Control, from `notes.md` in
this directory: on the PRE-FIX build an idle robot read `active=1` with
`cyc` frozen at 1660 across two reads.

On the fixed build, after driving (so the kernel has genuinely ticked —
`cyc` 198 and 473 and 841 across the runs below), an idle robot reads:

```
status ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 flags=31 i2cf=28  cyc=198 ...
status ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 flags=31 i2cf=118 cyc=473 ...
status ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 flags=31 i2cf=168 cyc=841 ...
```

`active=0` every time, immediately after motion stopped.

NOTE the first post-flash reads are NOT evidence of the fix and are not
cited as such: a freshly-flashed board reads `ready=0 connL=0 connR=0
cyc=0 active=0` because the kernel has never ticked, which looks like
success for the wrong reason. Only a read taken after real motion tests
the fix.

## Result 2 — the reverse-to-forward hang did NOT reproduce. 14 transitions, 0 failures.

Every run: `RUN nudge <left> <right> 40 #<id>`, the bench verb added for
this repro, which reports the tick count it actually completed.

| speeds [cm/s] | reversal transitions | ranTicks | completion line | emitDrops |
|---|---|---|---|---|
| -10/+10 | 4 | 40/40 every run | present every run | 0 |
| -4/+4 | 6 | 40/40 every run | present every run | 0 |
| mixed, tight gap (~1.15 s, next command sent as the previous loop ended) | 4 | 40/40 every run | present every run | 0 |

Against the original symptom — 16-17 of 40 ticks and no completion line
(`captures/calibratel-vevov-20260915/bench-log.md` runs 7-8) — nothing
resembling it occurred.

### A harness artifact that imitated the bug exactly, recorded so nobody re-finds it

The first attempt used `mbdeploy connect --remote vevov --timeout 15`,
one process per command. Both 40-tick runs printed `NUDGE:start` and no
`NUDGE:done`, which looks precisely like the reported hang. It was not:
`cyc` had advanced by the full ~94 steps, so both loops ran all 80 ticks.
`connect` returns once it has the reply to the line it sent and closes
the socket, so a line emitted a second later is lost by the HARNESS.

`nudgelink.py` (scratchpad) holds one socket open and timestamps every
line; under it, every completion line arrived. **Any future "the robot
stopped printing" claim must be made on a link that stayed open.**

## Result 3 — repeated ON THE FLOOR, wheels loaded. Still no hang. 8 transitions, 0 failures.

The stakeholder put vevov back on the main playfield (upper-left
quadrant) alongside tovez (lower-right, driven by the
nezha-robot-template session, which was between runs). Separation about
42 cm; the moves below are ~8 cm out and back, net zero.

vevov's tag plate was **missing at first** — the camera saw only tovez's
tag 52, and `get_tag(apriltag, 53)` returned null while the raw frame
clearly showed two robots. The stakeholder then fitted the tag, after
which tag 53 read world (-18.48, +17.18), matching the position
estimated from the frame's border markers (-22, +19).

**MEASURED vevov 2026-09-16 (this file), wheels DOWN, on the floor:**
four reversal pairs (-4/+4 twice, -10/+10 twice), `RUN nudge <l> <r> 40`:

- `ranTicks=40` of 40 on all 8 runs.
- Both `NUDGE:start` and `NUDGE:done` present on all 8.
- `runDrops=0`, `emitDrops=0` throughout.
- STATUS afterwards: `ready=1 active=0`, `cyc=1205`.

The wheels were genuinely loaded, and the log proves it rather than
asserting it: applied duty reached 1300-1600 (13-16%) against 1000-1100
for the same commands wheels-up, which is the drivetrain working against
the floor.

## What this does and does not settle

- Defect 1: settled on hardware. Fixed.
- The hang: NOT reproduced in **22 reversal transitions total** — 14
  wheels-up, 8 on the floor under load — across both speeds the original
  used. The wheels-up caveat this file originally carried is now
  answered: Result 3 repeated the test loaded, and the applied-duty
  figures prove the load was real.
- What still prevents calling it FIXED: **the build differs by more than
  the bench verb.** It carries the Defect 1 fix, which adds
  `engine.settleToRest()` to `softStop()` — a change to the very stop
  path the original hang followed. So "the hang no longer occurs on this
  build" is measured; "the hang was caused by X" is not. It may have been
  fixed incidentally, or it may need a trigger neither session has
  identified.
  The leading hypothesis in
  `docs/knowledge/2026-09-15-reverse-to-forward-drivetick-hang-diagnosis.md`
  (a load-dependent I2C stall) is NOT confirmed and NOT refuted: 8 loaded
  transitions is a small sample against an intermittent fault that showed
  up twice in the original session.

The honest verdict: **not reproduced on this build, loaded or unloaded;
cause still unknown.** The remaining way to settle it is to flash the
ORIGINAL firmware back onto vevov and try to reproduce it there. If it
reproduces on the old build and not the new one, the Defect 1 fix
explains it. If it will not reproduce on the old build either, the
trigger is something neither session has isolated, and the honest record
is an intermittent fault seen twice on 2026-09-15 and never since.
