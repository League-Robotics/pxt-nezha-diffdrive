# tools — bench and diagnostic tooling

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (host side of the retired cleartext vocabulary — see the telemetry note below; `make_deploy.py`'s `build()` is now triage-aware, see "Build checkpoint triage" below)

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

### Build checkpoint triage (`make_deploy.py`, sprint 008)

`tests/host/` compiles this project's portable C++ at `-std=c++20`;
both real embedded targets compile at `-std=c++11`, so a green host
suite is never evidence that a change actually compiles for the robot
(`clasi/issues/host-tests-compile-newer-standard-than-target.md`; see
`docs/design/design.md`'s "Host-vs-target language standard" section
and `src/DESIGN.md` §11 for the full history — three defect classes
have escaped the host suite this way, one of them, a `pxt.json`
manifest omission, blocking every hex entirely). This is why every
sprint that touches build-eligible source now includes a **mandatory,
always-last build-checkpoint ticket** that runs this script against
that sprint's own combined final state — this section documents the
triage `build()` uses to tell a real failure from a retriable one, so
that ticket does not require a human to read raw compiler output each
time.

`build()` captures `pxt build`'s combined stdout/stderr (streamed live
to the console as it runs, since a cloud build can take minutes) and
hands it to `classify_attempt(output, hex_exists)`, a pure function
with no subprocess of its own — unit-tested directly against saved/
synthetic build-log fixtures in
`tests/tools/test_make_deploy_triage.py`, so this triage can fail
loudly if someone breaks it later, the same "tests that can fail"
theme this project applies everywhere else. The verdict:

1. **Hard failure — reported immediately, no retry spent.** A genuine
   GCC/Clang diagnostic naming a source file and a line: `<file>.
   (cpp|cc|cxx|h|hpp):<line>:[<col>:] error:` or `... fatal error:`.
   This one pattern deliberately catches two distinct defect classes
   with no separate manifest-reading code path: a real language-defect
   compile error (e.g. reintroducing an NSDMI used in aggregate-init
   context, the original `Wire::Column` defect under C++11), and a
   `pxt.json` `files` omission, which fails as a `fatal error: ...: No
   such file or directory` at whichever other file's `#include` names
   the missing header — the same file:line:diagnostic shape, so the
   same regex catches both. This check runs *first*, before hex
   existence is even considered: a hex produced by one build variant
   does not excuse a compile error surfaced elsewhere in the same
   output.
2. **Benign — retried once, automatically, before being reported as
   anything.** Checked only once no compile diagnostic is present and
   no hex exists. Two shapes, both observed repeatedly this session:
   - The legacy V1 `bbc-microbit-classic-gcc` variant's own hex-merge
     step failing after a successful compile (`srec_cat: ...
     contradictory ... value`) — this variant is not used to flash
     this hardware; only the codal-microbit-v2 variant's hex matters,
     and this text appears in *every* build's log, benign, whether or
     not that build ultimately succeeds.
   - The nondeterministic packaging abort, always after a pxt-core
     cache-write `TypeError [ERR_INVALID_ARG_TYPE]`, surfaced as
     `TS9283` ("program too big"), `TS9043` ("hex file is not
     available"), or `TS9200` — the code varies run to run and is not
     itself the defect signal, per the issue's own triage principle
     ("did any `.cpp` fail to compile", not the error code).
   The retry is **bounded, not infinite**: if the same benign shape
   recurs on the retry and still produces no hex, `build()` reports
   that as a failure — the two shapes are expected to be transient,
   not chronic.
3. **Unknown — reported as a failure, deliberately not retried.** No
   hex, no compile diagnostic, and neither benign shape matched. Fails
   closed rather than risk silently retrying past a real, merely
   unrecognized defect. **This is the triage's known gap, stated
   plainly rather than overclaimed**: an abort shape that is genuinely
   benign but not yet documented here is reported as a hard failure
   requiring a human to look, exactly like a real defect would — the
   cost of failing closed is a false alarm, never a false pass.

**Verified against real builds, this session (sprint 008 ticket 006).**
Reintroducing an NSDMI-in-aggregate-init construct into a scratch copy
of `wire_handler.cpp` produced a real `error: could not convert
'{1, true}' from '<brace-enclosed initializer list>' to
'ScratchCxx14Probe'` diagnostic, classified `hard_failure` and reported
on attempt 1 with no retry spent. Separately, dropping
`src/heading_wrap.h` from a scratch copy of `pxt.json`'s `files`
produced a real `fatal error: heading_wrap.h: No such file or
directory` at `otos_port.cpp`'s `#include` site, classified the same
way. A real build against this sprint's own final state hit the
documented V1 hex-merge failure plus a `TS9200` packaging abort on
attempt 1, retried automatically, and produced a genuine 1,397,816-byte
flashable hex on attempt 2 — no code change required beyond the
documented retry.

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
