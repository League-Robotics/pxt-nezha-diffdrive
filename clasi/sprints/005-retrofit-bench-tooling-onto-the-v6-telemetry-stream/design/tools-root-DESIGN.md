# tools — bench and diagnostic tooling

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (sprint 005: `tools/tlm.py` retrofits all six telemetry consumers onto the v6 `thdr`/`t` frame with fail-loud guards, `tools/camproc.py`/`tools/field.py` consolidate the camera/link-layer duplication, and the numeric-RUN-vocabulary and testFiles build-hygiene defects are fixed; `make_deploy.py`'s `build()` remains triage-aware, see "Build checkpoint triage" below)

Host-side Python scripts for building, deploying, driving, measuring,
and charting the robot. Flat root, no subsystems. Run under `uv`
(`uv run python tools/<script>.py`) — including `robotlink.py`, now
that `pyproject.toml` declares `pyserial` (sprint 005; previously only
the system interpreter had it); `camlink.py` still runs under the
aprilcam pipx venv, its interpreter resolved once by `camproc.py`
rather than hardcoded per spawn site. Conventions (units, frames,
camera doctrine) are in
[`docs/design/design.md`](../docs/design/design.md).

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
- **`camproc.py`** (sprint 005) — owns camera-subprocess lifecycle:
  resolves the AprilTags interpreter once (not six hardcoded spawn
  sites), surfaces a spawned camera's `ERR` lines to the calling tool
  instead of discarding them, and invalidates a cached pose once the
  stream is marked dead — a mid-session camera death is now a visible
  failure, not a silently frozen pose fed back into `place()`/`fix()`.
- **`field.py`** (sprint 005) — owns playfield geometry: the dot/corner
  constants, `wrap()`, and corner scoring that used to be copied into
  seven separate `Cam` wrapper scaffolds (with two incompatible
  `latest` tuple orders) across the tour/ground-truth tools. Consumes
  `camlink.py`'s existing shared `Cam` rather than re-wrapping it.

## Telemetry (`tlm.py`, sprint 005)

- **`tlm.py`** — the single place any v6 telemetry scale factor is
  written. `TlmStream` tracks the `thdr` column header (re-emitted by
  firmware at ~1 Hz so a late-attaching consumer can resync) and feeds
  `t` lines, exposing `frames`, `orphan_frames` (a `t` before any
  header), `malformed` (a `t` whose value count disagrees with the
  header — the defense against `RadioTransport`'s 200-byte line
  truncation), and `dropped`/`loss_pct` (from `seq` gaps — a 7-bit
  wrapping counter at 20 Hz). Unit-conversion helpers (`pose_cm`,
  `otos_cm`, `wheels_mms`) live here too. Three fail-loud guards make
  "the instrument returned nothing" a loud, immediate failure instead
  of a silent empty CSV: `require_stream(link, timeout=3.0)` aborts
  *before* a run is triggered if no `t` frame arrives; `write_tlm_csv()`
  raises rather than writing a header-only CSV; a `<stem>_tlm.meta.json`
  sidecar (frames/dropped/loss_pct/orphan_frames/malformed/columns/
  duration) lets `tour_chart.py`/`practice_chart.py` refuse to plot a
  zero-frame run. All six tour/ground-truth consumers listed below
  import `tlm.py` instead of parsing wire lines themselves — see the
  "Known limitation" section this replaced, kept below as a resolved
  note for history.

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
  own sensors; no radio round-trips inside the tour. Records via
  `tlm.py`; aborts before starting if `require_stream()` finds no
  telemetry.
- **`tour_capture.py`** / **`tour_watch.py`** — telemetry recorders
  (triggered vs. button-watch); write the pose/wheel CSVs plus the
  `tlm.py` `.meta.json` sidecar (frames/dropped/loss_pct). Both tools'
  own pre-sprint-005 field-count arity checks (`tour_watch.py:202`'s
  `len(f) == 7`, `tour_capture.py:70`'s 7/4/3-length ladder) are gone —
  `tlm.py` owns arity now.
- **`tour_chart.py`** / **`practice_chart.py`** — the standard
  matplotlib plots of those CSVs; refuse to plot a run whose
  `.meta.json` sidecar reports `frames == 0`.
- **`tour_practice.py`** — repeated camera-scored runs from the start
  dot, repositioning between runs.
- **`tour_square.py`**, **`tour_closedloop.py`** — earlier variants
  kept for reference: composing a tour host-side, and the
  camera-in-the-loop experiment the doctrine now forbids (it left the
  robot stationary 73% of a run).

## Ground truth and calibration

- **`pivot_truth.py`** / **`truth_check.py`** — camera vs. OTOS vs.
  odometry for rotations: is the robot misbehaving or the sensor
  mis-reporting? Drive `test.ts`'s named `pivot`/`fix` RUN verbs
  (sprint 005; previously sent dead numeric `RUN:2/4/5/10` offsets that
  matched no handler on named-verb-only firmware).
- **`rotation_check.py`** — commanded vs. gyro-measured rotation
  (floor + radio only; on the bench the body never rotates). Same
  named-verb retargeting as `pivot_truth.py`/`truth_check.py`.
- **`turn_sweep.py`** — turn accuracy vs. yaw rate, camera-scored.
  Drives `test.ts`'s named `turnrate`/`pivot` verbs (sprint 005;
  previously `RUN:57000+rate`/`RUN:58360+deg`, also dead numeric
  offsets).
- **`otos_levercal.py`** — fits the OTOS lever arm from pivot circles
  (produced the 38.2 mm arm baked into `test/test.ts`). Drives
  `test.ts`'s already-named `RUN:cal`/`RUN:cal:1` (sprint 005; a
  Python-side rename only — `RUN:8`/`RUN:14` never matched a handler,
  but `cal` always did).
- **`reposition.py`** — put the robot on a world point, camera-
  verified, seeding from measured truth rather than assumed placement.

## OTOS rig console

- **`otos_bench.py`** — chainable subcommands driving
  `test/testrig.ts`'s numeric `RUN:<n>` vocabulary on the zeguz drum
  rig (probe, zero, stream, calibrate, servo, drum speed, lever arm).
  `testrig.ts`'s own two-arg `onRunCommand` dispatch bug (it stored the
  always-zero `arg` instead of the parsed numeric `name`, so every
  command silently reached no branch) is fixed as of sprint 005; this
  tool's own commands are unchanged.

## Resolved (sprint 005): the telemetry gap and the dead RUN vocabulary

~~These tools speak the old cleartext vocabulary (`RUN:` commands in;
`TLM:`/`DIAG`/`OCAL:`-style lines back), and the numeric `RUN:<n>`
vocabulary has no handlers anywhere on current firmware.~~ Both halves
are fixed as of sprint 005: telemetry now flows through `tlm.py`'s
`thdr`/`t` parser (see above), and every tool that used to send a
numeric `RUN:<n>` offset now sends a real named verb (`test.ts` gained
two new ones, `pivot` and `turnrate`, for exactly this purpose) or, for
`otos_bench.py`/`testrig.ts`, has its dispatch bug fixed rather than
its vocabulary ported. See `clasi/sprints/005-retrofit-bench-tooling-
onto-the-v6-telemetry-stream/sprint.md`'s Architecture section for the
full design rationale, including why `testrig.ts`'s vocabulary was
restored rather than renamed.
