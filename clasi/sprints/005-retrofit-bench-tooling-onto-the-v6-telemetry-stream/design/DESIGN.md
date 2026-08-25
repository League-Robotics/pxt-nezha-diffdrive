# test — PXT testFiles (on-robot programs)

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** stable

MakeCode/PXT `testFiles` (declared in `pxt.json`): TypeScript programs
compiled into a **deploy** build only — `tools/make_deploy.py`
promotes them into `files` in a scratch copy; in the repo they must
stay `testFiles` so they never run inside a student project that
installs the extension. They are smoke/bench programs driven by
buttons and `RUN:` wire commands, not assertion suites — the
assertion-style coverage lives in `tests/host/`.

- **`test.ts`** — the playfield test programs: three square tours
  (robot-relative encoder+IMU, OTOS-guided `goToWorld`, open-loop
  wheels), each an explicit `startMove` + `driveTick()` loop so the
  tick model stays visible test code; plus named `RUN:` commands for
  lever-arm calibration (`cal`), fixes, seeding, and probes. Carries
  vevov's measured lever arm and the playfield's dot coordinates.
- **`testrig.ts`** — the zeguz OTOS validation rig: drum on M1 under
  the sensor, sensor on a servo, a numeric `RUN:<n>` vocabulary
  (probe/zero/stream/calibrate/servo/drum/lever-arm), driven by
  `tools/otos_bench.py`. One worker fiber does **all** I2C —
  kernel ticks and OTOS reads sequentially — per the shared-bus
  discipline in [`src/DESIGN.md`](../src/DESIGN.md) §7.

Deliberately thin: these files are working bench instruments; their
design decisions (tick loops, I2C single-fiber rule, RUN vocabulary)
are documented where they are owned — `src/DESIGN.md` and
`tools/DESIGN.md`.
