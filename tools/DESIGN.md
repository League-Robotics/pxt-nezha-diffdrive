# tools — bench and diagnostic tooling

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** stable (host side of the retired cleartext vocabulary — see the telemetry note below)

Host-side Python scripts for building, deploying, driving, measuring,
and charting the robot. Flat root, no subsystems. Run under `uv`
(`uv run python tools/<script>.py`); `camlink.py` runs under the
aprilcam pipx venv instead. Conventions (units, frames, camera
doctrine) are in [`docs/design/design.md`](../docs/design/design.md).

## Link layer — what everything talks through

- **`robotlink.py`** — one `Link` object that talks to the robot over
  USB serial or the zavaz radio relay (`--radio`; channel 4, group
  10 — vevov's assignment; never retune getez's channel 3). Both
  carriers deliver the same ASCII lines. The split matters: the USB
  cable only reaches the bench stand where the wheels are off the
  ground, so anything needing real motion runs untethered over radio.
- **`camlink.py`** — persistent gRPC stream to the aprilcam overhead-
  camera daemon. Carries the hard-won registration rules in its
  docstring: tag mount parameters are not persisted across daemon
  restarts, units are centimetres, vevov's tag mounts a quarter-turn
  round (`mount_yaw_rad = -pi/2`) — an unregistered tag reports a
  plausible but wrong position.

## Build / deploy

- **`make_deploy.py`** — builds a flashable hex in a scratch copy of
  the repo with `test/test.ts` promoted into `files` (a `files`-listed
  test would run inside every student project) and
  `disablesVariants: ["mbdal"]` dropped (kept, it produces a hex that
  is dead on the device). Deletes the hex up front and verifies it
  exists afterwards, because the expected V1 `TS9283` error
  nondeterministically deletes it.

## Tour family — run, record, chart, score

All drive the on-robot programs in `test/test.ts` via `RUN:` commands
and record what comes back.

- **`tour_run.py`** — the canonical run: camera used exactly twice
  (seed at start, score at end); the robot drives all four legs on its
  own sensors; no radio round-trips inside the tour.
- **`tour_capture.py`** / **`tour_watch.py`** — telemetry recorders
  (triggered vs. button-watch); write the pose/wheel CSVs.
- **`tour_chart.py`** / **`practice_chart.py`** — the standard
  matplotlib plots of those CSVs.
- **`tour_practice.py`** — repeated camera-scored runs from the start
  dot, repositioning between runs.
- **`tour_square.py`**, **`tour_closedloop.py`** — earlier variants
  kept for reference: composing a tour host-side, and the
  camera-in-the-loop experiment the doctrine now forbids (it left the
  robot stationary 73% of a run).

## Ground truth and calibration

- **`pivot_truth.py`** / **`truth_check.py`** — camera vs. OTOS vs.
  odometry for rotations: is the robot misbehaving or the sensor
  mis-reporting?
- **`rotation_check.py`** — commanded vs. gyro-measured rotation
  (floor + radio only; on the bench the body never rotates).
- **`turn_sweep.py`** — turn accuracy vs. yaw rate, camera-scored.
- **`otos_levercal.py`** — fits the OTOS lever arm from pivot circles
  (produced the 38.2 mm arm baked into `test/test.ts`).
- **`reposition.py`** — put the robot on a world point, camera-
  verified, seeding from measured truth rather than assumed placement.

## OTOS rig console

- **`otos_bench.py`** — chainable subcommands driving
  `test/testrig.ts`'s numeric `RUN:<n>` vocabulary on the zeguz drum
  rig (probe, zero, stream, calibrate, servo, drum speed, lever arm).

## Known limitation — the telemetry gap

These tools speak the **old cleartext vocabulary** (`RUN:` commands
in; `TLM:`/`DIAG`/`OCAL:`-style lines back). Sprint 003's v6 cutover
retired the firmware's periodic `TLM:` stream with no v6 replacement
yet, so the recorders' `TLM:` branch never fires against current
firmware — pose columns record empty, silently. The `RUN:` cleartext
*transport* still works (`protocol.cpp` forwards it), but the numeric
`RUN:<n>` vocabulary has no handlers anywhere: `main.ts` dispatches RUN
by exact name, `test/test.ts` registers only named handlers, and
`testrig.ts`'s two-arg handler stores the argument, not the name — so
every numeric command from `otos_bench.py`, `rotation_check.py`,
`truth_check.py`, `pivot_truth.py`, `turn_sweep.py`, and
`otos_levercal.py` is a silent no-op. Only named-verb `RUN:` commands
and `emitLine()`-based result lines still work. Telemetry restored by
the planned telemetry-frame work (sprint 004), not yet built; the
numeric-vocabulary breakage is separate and unplanned (see
docs/code-review/2026-08-23/, PY-01/BLK-04).
