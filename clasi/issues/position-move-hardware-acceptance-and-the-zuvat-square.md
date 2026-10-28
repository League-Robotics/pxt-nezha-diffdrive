---
status: pending
sprint: '043'
---

# Hardware acceptance of position moves: bench 50 cm, then a square tour on zuvat

Sprint 1 ships position moves host-tested only. This issue is the
hardware run that decides whether `position_mode 1` (and 2 for arcs)
becomes the default. `change-plan.md` C13 to C16, plus the stakeholder's
ask of 2026-10-27: a two-motor square tour with the closure metric and
the motor speed curves.

## Rigs

- Bench: the micro:bit + Nezha rig with one motor on M1 and an 83 mm
  wheel, local USB (`tools/mb50.py`).
- Robot: **zuvat** (two motors, no camera, no OTOS), on the nolanet farm
  node loki (`mbdeploy list` shows it free on `/dev/ttyACM1`). Flash with
  `mbdeploy deploy`, talk over the farm serial daemon or WiFi if the
  deploy bakes credentials. Only the motor path is under test.

## Runs

1. Bench 50 cm at `position_mode 1`, 30/60/100 %, four trials each
   direction, the `STATUS` flag confirming the path: every trial within
   0.5 mm, time at 100 % under 1.2 s.
2. zuvat: 90° and 180° pivots at `position_mode 1`, encoder-side error
   within 0.5°, no lurch; two-wheel start skew from telemetry under 10 ms.
3. zuvat: the square tour (`RUN:tour:square:<side>`, 50 or 60 cm sides)
   at `position_mode 0` and `position_mode 1`, telemetry captured with
   `tools/tour_capture.py` and charted with `tools/tour_chart.py`:
   encoder-side closure (start-to-end distance and heading residual) and
   the left/right wheel speed curves. Report the closure metric for both
   modes side by side. Target: better than the 11 mm sprint 031 recorded.
   No camera on zuvat, so this is encoder truth; say so in the capture.
4. Stop timing during a live move (`STOP`, `ESTOP`, watchdog): at rest
   within 200 ms, travel per the §7a table.
5. Arcs: `position_mode 2` square-of-arcs or circle against the kernel's,
   encoder-truthed; decides the arc default.
6. If `speed_path` exists: `0` against `1` on `WHEELS_V` and a 600 mm
   kernel leg; decides its default.

Every run lands under `captures/zuvat-position-<date>/` with the hex,
the CSVs, the charts and a notes file, per
`.claude/rules/measurement-citations.md`.
