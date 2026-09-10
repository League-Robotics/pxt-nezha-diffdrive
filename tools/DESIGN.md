# tools — bench and diagnostic tooling

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
stable. The inventory below covers every file under `tools/` — 38
Python files plus `field_calibration.json` — and
`tests/tools/test_tools_design_inventory.py` fails if a file is added
without an entry here.

Host-side Python for building, deploying, driving, measuring and
charting the robot. One flat root plus two self-contained
subdirectories (`rogo/`, `linefollow/`). Everything runs under `uv`
(`uv run python tools/<script>.py`) in this repo's single venv —
including `camlink.py`, which reads the aprilcam daemon in this
interpreter because `aprilcam[daemon]` is a declared dependency of it.
Conventions (units, frames, camera doctrine) are in
[`docs/design/design.md`](../docs/design/design.md).

This document is **content, not a changelog** — it describes the tree
as it stands, per `docs/design/design.md`'s "Subsystem-doc contract"
section. A paragraph that goes stale is rewritten, never annotated with
a dated update beneath it: the previous revision carried three layers
of "superseded by" on top of one wrong claim, and every reader had to
work out which layer was live.

## Inventory

One line per file. The sections after this one cover the pieces that
need more than a line; a file with no section is fully described here.

### Link layer and carriers

| file | what it is for |
|---|---|
| `link.py` | the one sequenced-wire protocol every carrier shares: `Sequencer`, `LineBuffer`, `relay_setup_lines()`, `RELAY_HOST`/`RELAY_PORT`. Stdlib only. |
| `robotlink.py` | the `Link` bench tools open — USB serial or the radio relay — plus `open_link()`, `radio_address(robot)` and the `_V6_VERBS` sequenced-verb set. |
| `fieldlink.py` | two carriers behind one `unseq`/`seqd`/`hello`/`close` interface for the field programs: the lossy relay pool (`FieldLink`) and a farm node's lossless serial daemon (`TcpFieldLink`). |
| `wifilink.py` | the robot over its own WiFi transport: `TcpLink` on port 7654, the UDP `WifiLink` on fixed host port 7655, and mDNS/broadcast discovery. |
| `rogo/rogo.py` | `nc` for a robot: discover it, open its TCP server, pipe lines. Stdlib-only and pipx-installable, so its line handling is a **deliberate** duplicate of `link.py`'s — see below. |
| `rogo/pyproject.toml` | packaging for that one file, so `pipx install tools/rogo` works from this checkout or straight from git. |

### Camera, field geometry and placement

| file | what it is for |
|---|---|
| `camlink.py` | the ONE `Cam`: a background reader thread over a persistent gRPC stream to the aprilcam daemon, publishing one sample per real camera frame; also `--register`, the only path that writes a tag mount to the daemon. |
| `field_calibration.json` | the calibration of record — per-robot tag number, mount offsets, mount-yaw residual, lever arm, parallax factor and radio channel/group. Data, not code; `camlink.py` and `robotlink.py` both read it. |
| `field.py` | playfield geometry and the angle math the scorers need: `LIMITS`/`MARGIN`/`usable_half_extent()`, `check_path()`/`require_clear_path()`, `wrap()`, `turn_total()`, `score_corners()`, `clears_margin()`, `pose_from_registered_samples()`. Imports nothing but `math`. |
| `reposition.py` | the one repositioning loop: put the robot on a world point at a world heading, camera-verified, position first and heading second. |
| `park.py` | plans a park on a world pose for LEAST TOTAL ROTATION, using reverse motion where reversing is cheaper than turning around. |

### Telemetry, recording and charts

| file | what it is for |
|---|---|
| `tlm.py` | the single v6 telemetry parser (`TlmStream`, header-keyed), its fail-loud guards, and the one on-disk pose-CSV codec. |
| `tour_capture.py` | the standard triggered recorder: starts a named tour, records the `thdr`/`t` stream to the pose/wheel CSVs. |
| `tour_watch.py` | the same recording, triggered by the robot's own button instead of a host command; charts each run as it lands. |
| `tour_run.py` | the canonical run — stage through `reposition.py`, camera fix at the start, the robot drives all four legs alone, camera fix at the end. |
| `tour_practice.py` | repeated camera-scored runs from the start dot, repositioning between them, charting each. |
| `tour_chart.py` | the standard two-panel matplotlib plot of a recording (x-y trajectory with closure, wheel speeds), with outlier hygiene. |
| `practice_chart.py` | the per-run practice plot: one recorded tour against its camera track. |
| `leg_analysis.py` | turns a recording into a per-leg believed-vs-commanded table with a classification per leg. |

### Ground truth and calibration probes

| file | what it is for |
|---|---|
| `pivot_truth.py` | camera vs. OTOS vs. odometry for rotations — is the robot misbehaving or the sensor mis-reporting? |
| `rotation_check.py` | commanded vs. gyro-measured rotation over the standard pivot set (floor and radio only; on the bench the body never rotates). |
| `turn_sweep.py` | turn accuracy against commanded yaw rate, camera-scored. |
| `otos_levercal.py` | fits the OTOS lever arm from pivot circles (produced the 38.2 mm arm baked into `test/test.ts`). |
| `arc_capture.py` | captures the full on-device h(t) trajectory of a `RUN arc` split move, for the phase-handoff question an endpoint heading cannot answer. |
| `otos_bench.py` | the zeguz drum-rig console — chainable subcommands over `test/testrig.ts`'s numeric `RUN <n>` vocabulary. |

### Acceptance

| file | what it is for |
|---|---|
| `wire_acceptance.py` | end-to-end acceptance against real firmware on a real robot: good cases, bad cases, every v6 verb, and whether the robot actually MOVES. The proof a carrier works. |
| `provision_wifi.py` | one scripted bench session that writes a board's WIFICRED flash-backed credential store (single `--slot`, a `--manifest` batch, `--list`, or `--clear`) — no hand-typed wire lines, no wizard UI; a passphrase is read from an env var, a file, or a non-echoing prompt and never printed, logged, or persisted by this tool. Provision AFTER flashing: a flash mass-erases the chip. |

### Build, deploy and publish

| file | what it is for |
|---|---|
| `make_deploy.py` | builds a flashable hex in a scratch copy of the repo, bakes the target robot's radio channel/name/geometry/motors, and triages the build result. |
| `gen_config_field_enum.py` | the repo's one code generator: writes `src/blocks/motion.ts`'s `ConfigField` enum from `src/comms/config_fields.h`. `--check` reports drift without writing. |
| `publish_extension.py` | assembles the student-facing MakeCode extension from `pxt.json`'s `files` plus `extension/`, and pushes it to its own generated repository. |
| `publish_wiki.py` | renders a Markdown doc from this repo onto the Robot Garage DokuWiki. |
| `blocks_env.py` | brings up the local MakeCode blocks editor with this extension loaded (`just blocks`). |
| `blocks_toolbox.py` | applies `reports/blocks-toolbox.csv` to the extension's block annotations — the CSV is the source of truth for toolbox layout. |

### Shims

| file | what it is for |
|---|---|
| `field_dance.py` | a shim only. The field dance lives at `tests/calibration/field_dance.py`; running this file runs it there, importing this file re-exports it without driving a robot. |

### `linefollow/` — vevov on the KIPR line mat

Its own subsystem, with its own [`DESIGN.md`](linefollow/DESIGN.md) and
`README.md`. It is the one place in this repo that reads a RAW,
unregistered tag and applies its own parallax correction (see
"Camera-parallax correction" below).

| file | what it is for |
|---|---|
| `linefollow/stage.py` | stages vevov at a target true world pose from ONE camera fix, refusing anything outside the margin. |
| `linefollow/follow.py` | world-anchored pure pursuit along a field-frame path, on the robot's own odometry. |
| `linefollow/sensor_run.py` | runs the on-robot Trackbit follower (`RUN line`) over the farm serial daemon, with a camera watchdog that can only abort, never steer. |
| `linefollow/linerun.py` | one lossless session to a farm robot's serial daemon: send lines, log every reply with a timestamp. |
| `linefollow/camlog.py` | logs the camera-measured centre of rotation to CSV at the daemon's rate. Diagnostic only. |
| `linefollow/chart.py` | scores and charts a `follow.py` run: reference path, camera track, odometry track, cross-track error. |
| `linefollow/chart_sensor.py` | the same for a `sensor_run.py` result: camera truth against the traced line, plus the robot's own odometry trace. |
| `linefollow/kipr_course.path.json` | the reference path, traced from a deskewed camera frame — field frame, mm. |

## Link layer — what everything talks through

- **`link.py`** (sprint 034 ticket 006) — the one sequenced-wire
  protocol: `Sequencer` (id allocation, resend-with-the-same-id,
  `ack N` → N / `nack N` → N−1, the sequenced/unsequenced split),
  `LineBuffer` (newline reassembly across arbitrary read boundaries,
  with the relay's `'< '` receive prefix stripped), and
  `relay_setup_lines()` / `RELAY_HOST` / `RELAY_PORT`. It was
  implemented four times before this (`robotlink.Link`,
  `fieldlink._SequencedLink`, `wire_acceptance`'s link family,
  `tests/calibration/turn_calibration.Link`), so a fix landed in some
  of them. **Transports stay with their carriers** — how a socket or a
  serial port is opened, tuned and closed genuinely differs, and
  pretending otherwise is how the four copies started. Stdlib-only, so
  `tests/host/` and `tests/calibration/` can import it on a machine
  with no pyserial and no robot. Pinned by `tests/tools/test_link.py`.
  The relay setup is settled as **all four lines on every relay
  carrier** (`!ECHO OFF`, `!MODE RAW250`, `!CG <ch> <grp>`, `!P 7`,
  then `!GO` at the call site): the relay PERSISTS its config across
  resets (`!DEFAULTS` exists for exactly that), so the "a fresh board
  already defaults to RAW250/power 7" reasoning that let two carriers
  skip them inherits a previous session's setting in silence — and
  `!ECHO` is a radio TRANSPONDER, not terminal echo.
  **`tools/rogo/` is a deliberate duplicate of these rules and must
  never import this module** — see `tools/rogo/DESIGN.md` and sprint
  034's Design Rationale 3. `wire_acceptance.py` uses `LineBuffer` and
  `relay_setup_lines()` but deliberately NOT `Sequencer`: its job is to
  probe the sequencing contract from outside, so it hand-writes the ids
  its cases need (`#0`, a `#9` gap, the reserved ceiling
  `#4294967295`) and tracks the robot's counter from what the robot
  actually says.
- **`wifilink.py`** (2026-09-02) — the robot over its own WiFi
  transport: `TcpLink` (the robot's TCP server on `:7654`, a plain line
  stream, the default carrier) and the UDP `WifiLink` bound on the
  fixed host port `:7655` with a 15 s keepalive (the robot learns its
  host from the first datagram and forgets it after 60 s), plus
  discovery by mDNS (`<name>.local`, which the robot announces itself)
  with a broadcast `HELLO` fallback. `robotlink.open_link(wifi=...)`
  wraps `TcpLink` in the pyserial shape `Link` expects, so every tour
  tool takes `--wifi <name>`. `wire_acceptance.py --wifi-tcp`, `--wifi`
  and `--tcp <farm-node>:<port>` build on it; its every-verb section
  exercises the whole v6 table so a transport is judged against the
  whole protocol.
- **`fieldlink.py`** — the field programs' own two carriers behind one
  `unseq`/`seqd`/`hello`/`close` interface, so a caller does not care
  which it is driving over. `FieldLink` goes through the torture relay
  pool and is LOSSY, so every request retries and the absence of a
  reply is never evidence of absence (the module's own docstring quotes
  66-83% per-line delivery; UNVERIFIED here — no capture is named
  beside it, and the project's own loss figure for that desk is
  attributed to WiFi interference at the relay site, not to the robot);
  `TcpFieldLink` is a raw lossless pipe to a farm node's
  serial daemon — including a Pi riding on the robot itself, which is
  on the field and needs no cable. The `#id` contract is identical
  either way: a resend reuses its ORIGINAL id, because a fresh one
  presents as a numeric gap and stalls the stream on purpose.
- **`robotlink.py`** — one `Link` object that talks to the robot over
  USB serial or the zavaz radio relay (`--radio`); the sequencing and
  the line rules are `link.py`'s, and `_V6_VERBS` stays a literal here
  because `tests/host/test_wire_constants_drift.py` reads it as source
  text against `wire_handler.cpp`'s `kCommandTable`. **Sprint 029**: the
  channel/group are no longer a hardcoded constant
  (`ZAVAZ_CHANNEL`/`ZAVAZ_GROUP`, stale since vevov's 2026-08-30 move to
  37/43) — the relay address is derived from the board name (the same
  base-5 `!N` derivation the relay itself uses,
  `radio-address-derived-from-board-name`) or read from
  `field_calibration.json` when present, so a board reassignment no
  longer requires a source edit here to stay reachable. Both carriers
  deliver the same ASCII lines. The split matters: the USB cable only
  reaches the bench stand where the wheels are off the ground, so
  anything needing real motion runs untethered over radio.
- **`rogo/`** — `rogo`, `nc` for a robot over the Planet X WiFi module's
  TCP server on :7654. Its own pipx-installable project (`pipx install
  tools/rogo`, or from git with `#subdirectory=tools/rogo`); `just rogo`
  runs it from the checkout. Finds the
  robot's own DNS-SD announcement (`<name> robot link` on
  `_robotlink._tcp`, via `dns-sd -L`), takes the IP *and port* from
  it, falls back to `<name>.local:7654`, then pipes stdin/stdout to the
  socket: `just rogo tovez`, `just rogo tovez PING STATUS`,
  `just rogo --browse`, `just rogo --discover tovez`. Standard library
  only, no `#<id>` help — it is a raw pipe, the wire rules apply.
  **Its line handling duplicates `link.py`'s deliberately** (sprint 034
  Design Rationale 3): rogo's premise is `pipx install` with nothing
  but Python, so it must never import anything from `tools/`.
  Pinned by `tests/tools/test_rogo.py` against captured `dns-sd` output;
  MEASURED tovez 2026-09-03, `captures/rogo-tovez-20260903/notes.md`.
- **`camlink.py`** — persistent gRPC stream to the aprilcam overhead-
  camera daemon, and the ONE `Cam` class every bench tool uses.
  **Sprint 034 ticket 008**: in-process, on a background reader thread
  publishing one sample per REAL camera frame. The camera-subprocess
  wrapper that used to sit in front of it — a second `Cam`, a hardcoded
  interpreter path, an `ERR`/`NOTAG` line protocol and a respawn counter
  — existed only to bridge two Python interpreters that are now one, and
  is deleted; its consumer surface (`latest`, `fix()`, timestamped
  `samples`/`since()`, `err`/`notag`) moved here unchanged.
  **Sprint 029**: `field_calibration.json` is now the one
  calibration of record for tag mounts — `camlink.py` loads it and no
  longer re-registers a mount as a side effect of merely constructing
  `Cam` (the previous `MOUNTS` table and `ensure_registered()`'s
  unconditional `register_tag()` call are deleted). Registration only
  happens on an explicit `--register` invocation, so starting any tool
  can no longer silently overwrite the aprilcam daemon's persistent
  registry with a stale mount — the exact shape of the 2026-08-31 rails
  crash and the 2026-09-02 finding that motivated this fix
  (`one-calibration-of-record-camlink-robotlink.md`). The stored mount
  residual is the sub-degree physical correction only; the fixed +90°
  yaw convention (`tag-yaw-is-the-front-edge-not-the-hat.md`) is never
  re-derived or stored as a probe-fitted value; a residual near ±180°
  means the ROBOT is driving backwards (its motor mapping not baked),
  never a reversed plate — check the tag arrow on the camera first
  (tovez 2026-09-04, `reports/bench-acceptance-029-20260904d.md` §9).
  Units remain centimetres. `make_deploy.py` now also bakes
  `firmware_bake.motors` (`_inject_motors()`), the per-robot port and
  forward-sign mapping, beside the geometry keys.

## Build / deploy

- **`gen_config_field_enum.py`** — the only code generator in this
  directory, and the only script whose output is committed source.
  Reads `src/comms/config_fields.h` (the wire's one config
  name/ordinal/unit table) and writes `src/blocks/motion.ts`'s
  `ConfigField` enum from it, because PXT compiles a fixed TypeScript
  file set and cannot read a C++ table at build time. Run it —
  `uv run python tools/gen_config_field_enum.py` — and commit both
  files whenever a row in that header is added, renamed, renumbered, or
  removed; `--check` reports drift without writing.
  `tests/tools/test_gen_config_field_enum.py` regenerates and compares,
  so a forgotten run fails the suite rather than shipping a block layer
  that addresses a different field than the wire does. Not part of any
  build step: nothing invokes it automatically, by design (a
  pre-commit hook is a tooling change, not a cohesion one).

- **`make_deploy.py`** — builds a flashable hex in a scratch copy of
  the repo with `test/test.ts` promoted into `files` (a `files`-listed
  test would run inside every student project). `--robot <name>`
  (default `vevov`) selects more than the flash target: after `sync()`
  populates the scratch copy, the target robot's `connection.
  radio_channel` is read from radio-robot-lib's canonical per-robot
  config (`radio-robot-lib/config/robots/<robot>.json`, never a table
  in this repo) and substituted into the scratch copy's
  `src/comms/radio_transport.h` before `build()` runs — the repo's own
  checked-in source keeps one fixed placeholder (a legacy fleet-wide
  4/10 that is nobody's address any more), and an unparameterised build
  is not an uninjected one: it injects `DEFAULT_ROBOT`'s own configured
  channel and group, from the same JSON as any other robot's. A
  missing/unreadable config, or one with no `radio_channel` field,
  fails the build loudly rather than falling back to a default.
  Also drops `disablesVariants: ["mbdal"]` from the scratch copy (kept
  in the repo's own `pxt.json`, it produces a hex that is dead on the
  device). Sets `PXT_COMPILE_SWITCHES=csv-mbcodal`
  unconditionally in the `pxt build` subprocess environment (sprint
  014, `clasi/issues/never-build-the-v1-mbdal-variant.md`) — this makes
  `pxt-core` select `appTargetVariant=mbcodal` up front, a different
  mechanism from `disablesVariants` that means the legacy V1 (`mbdal`)
  variant is never built at all, not just stripped of its dependencies.
  Also defaults `PXT_FORCE_LOCAL=1` (honoring an ambient override, e.g.
  `PXT_FORCE_LOCAL=0` to opt back into the MakeCode cloud compiler), so
  a bare `uv run python tools/make_deploy.py` compiles locally via
  Docker with no env-var prefix required. The resulting single-variant
  hex lands at `built/binary.hex`, not the old multi-variant
  `built/mbcodal-binary.hex` — but that filename alone is ambiguous: a
  universal (V1+V2) hex from the old multi-variant build and a plain V2
  hex from the single-variant build are byte-for-byte different
  artifacts sharing one path. `build()` therefore counts `:0400000A`
  universal-hex block-start markers in the produced hex and hard-fails,
  before ever reporting it as ready, if the count is not exactly 0 (see
  "Build checkpoint triage" below). Deletes the hex up front and
  verifies it exists afterwards, because a packaging abort
  nondeterministically deletes it. **Sprint 023** added two more
  post-triage assertions, closing a gap where a build served wholly or
  partly from a stale `.tmp/deploy-head/built/dockercodal` cache could
  print a clean log, exit 0, and still land a real but short/under-
  compiled hex: `build()` hard-fails if `binary.hex` is smaller than
  `MIN_HEX_SIZE_BYTES`, and hard-fails if any of the ten
  `nezha-diffdrive` `.cpp` files (`EXPECTED_CPP_FILES`) is missing from
  the captured output's `Building CXX object` lines — including the
  case of **zero** such lines, which is not treated as "nothing needed
  rebuilding" (see "Build checkpoint triage" below).

### Publishing and the blocks editor

Three tools whose output leaves this repo, and one that brings the
editor to it. All four are generators over a source of truth that
lives elsewhere in the tree — none of them is hand-edited state.

- **`publish_extension.py`** — this repo is a whole engineering
  workspace; the extension students install is a small subset of it,
  published to its own repository, which is GENERATED and never edited.
  The two inputs are `pxt.json`'s `files` list (so the published tree
  is by construction the one PXT builds from here) and the
  `extension/` overlay (student README, LICENSE, sample `test.ts`).
- **`publish_wiki.py`** — renders a repo Markdown doc onto the Robot
  Garage DokuWiki. Re-run it after editing a doc that is published
  there; nothing syncs on its own.
- **`blocks_env.py`** — `just blocks`. Prepares the on-disk workspace
  `pxt serve` expects and opens the editor on the one URL that actually
  selects the filesystem workspace. Its docstring is a list of traps,
  each of which fails as a silently missing toolbox category rather
  than an error.
- **`blocks_toolbox.py`** — applies `reports/blocks-toolbox.csv` to the
  extension's block annotations (`just blocks-plan` to see the diff,
  `just blocks-apply` to write). The CSV is the source of truth for
  toolbox layout: edit it and re-run rather than hand-tuning weights in
  the source.

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
   no hex exists. One shape, observed repeatedly this session:
   - The nondeterministic packaging abort, always after a pxt-core
     cache-write `TypeError [ERR_INVALID_ARG_TYPE]`, surfaced as
     `TS9283` ("program too big"), `TS9043` ("hex file is not
     available"), or `TS9200` — the code varies run to run and is not
     itself the defect signal, per the issue's own triage principle
     ("did any `.cpp` fail to compile", not the error code).
   The retry is **bounded, not infinite**: if the same benign shape
   recurs on the retry and still produces no hex, `build()` reports
   that as a failure — the shape is expected to be transient, not
   chronic.
3. **Unknown — reported as a failure, deliberately not retried.** No
   hex, no compile diagnostic, and the benign shape didn't match
   either. Fails closed rather than risk silently retrying past a
   real, merely unrecognized defect. **This is the triage's known
   gap, stated plainly rather than overclaimed**: an abort shape that
   is genuinely benign but not yet documented here is reported as a
   hard failure requiring a human to look, exactly like a real defect
   would — the cost of failing closed is a false alarm, never a false
   pass. **As of sprint 014, this bucket also catches a resurrected
   legacy V1 `bbc-microbit-classic-gcc` hex-merge failure**
   (`srec_cat: ... contradictory ... value`): under
   `PXT_COMPILE_SWITCHES=csv-mbcodal` (see the `make_deploy.py` bullet
   above) V1 is never built at all, so this shape — formerly benign
   and retried on *every* build regardless of outcome — is no longer
   an expected, retry-worthy trap. Its only remaining meaning is "the
   switch silently failed to take effect," which is a configuration
   regression, not a transient flake, so it now falls through to
   `UNKNOWN` and hard-fails on attempt 1 with no retry
   (`clasi/issues/never-build-the-v1-mbdal-variant.md`). The
   universal-vs-plain-V2 block-marker assertion (the `make_deploy.py`
   bullet above) is the actual backstop for this scenario — failing
   fast in `classify_attempt()` means the ordinary case never gets that
   far.

**Verified against real builds** (sprint 008 ticket 006, closed
2026-08-24; the runs are recorded in that ticket's own file under
`clasi/sprints/done/008-wire-hardening-and-tests-that-can-fail/`).
Reintroducing an NSDMI-in-aggregate-init construct into a scratch copy
of `wire_handler.cpp` produced a real `error: could not convert
'{1, true}' from '<brace-enclosed initializer list>' to
'ScratchCxx14Probe'` diagnostic, classified `hard_failure` and reported
on attempt 1 with no retry spent. Separately, dropping
`src/core/heading_wrap.h` from a scratch copy of `pxt.json`'s `files`
produced a real `fatal error: heading_wrap.h: No such file or
directory` at `otos_port.cpp`'s `#include` site, classified the same
way. A real build against this sprint's own final state hit the
documented V1 hex-merge failure plus a `TS9200` packaging abort on
attempt 1, retried automatically, and produced a genuine 1,397,816-byte
flashable hex on attempt 2 — no code change required beyond the
documented retry.

**Post-triage: hex size floor and translation-unit presence (sprint
023).** A `SUCCESS` verdict from `classify_attempt()` plus a
zero-marker plain-V2 hex is still not proof the hex is *complete* — a
build served wholly or partly from a stale
`.tmp/deploy-head/built/dockercodal` cache can print a fully clean log,
exit 0, and produce a real, well-formed, but short hex, because
nothing above judges the hex's actual completeness. This recurred
repeatedly: a build once produced a `binary.hex` 27% short of the
correct size with a clean exit and nothing in the log to flag it, and
separately, a build served entirely from cache has produced a clean
log containing **zero** `Building CXX object` lines while still
exiting 0 with a hex on disk. `build()` closes both, once triage and
the block-marker check both pass, with two more assertions before a
hex is ever printed as ready to flash:

- **Size floor.** `os.path.getsize(hex_path)` must be at least
  `MIN_HEX_SIZE_BYTES` (a named constant, with the measured checkpoint
  band recorded in a comment beside it in `make_deploy.py`). The floor
  sits well above the shortest truncated hex observed and well below
  the measured band of genuine builds, so it has real margin on both
  sides.
- **Translation-unit presence.** All ten `nezha-diffdrive` `.cpp`
  files (`EXPECTED_CPP_FILES`, a literal list, not a filesystem scan at
  check time) must each appear as a `Building CXX object` line
  somewhere in the captured build output. A build output with **zero**
  such lines fails this exactly like any other missing-subset case —
  the check is written as "is each expected file found", never "is
  each found line one of the expected files", so an empty found-set
  can never vacuously satisfy it.

Both checks are pure functions with no subprocess or real build
(`_check_hex_size()` / `_check_translation_units()` in
`make_deploy.py`), unit-tested directly against synthetic size/log
fixtures in `tests/tools/test_make_deploy_triage.py`, mirroring
`classify_attempt()` / `_count_universal_hex_blocks()`'s own
testability pattern. On failure, `build()` exits the same way an
`UNKNOWN`/`HARD_FAILURE` triage verdict does, naming what was expected
vs. found and pointing at the fix: wipe the stale scratch copy (Python
`shutil.rmtree()` — `rm -rf` may be sandbox-denied in some
environments) and rebuild from a genuinely clean copy.

## Telemetry (`tlm.py`)

`tools/tlm.py` is the ONE place a v6 wire column is decoded and the ONE
place a wire-to-engineering-unit scale factor is written. Every
recorder, chart and analysis tool is a leaf consumer of it; none of
them carries a scale factor of its own. Three responsibilities:

1. **The stream parser.** `TlmStream.feed()` accepts the firmware's
   `thdr <col> <col> ...` header line and its `t <val> ...` frames and
   binds every value by COLUMN NAME from the most recent header — never
   by position. Two column sets exist and can appear in the same
   capture (a 12-column POSE set and a 20-column FULL set), so a
   position-bound reader silently reads the wrong series the moment the
   firmware switches or grows a column. Everything else on the link
   (`ack`/`nack`, `STATUS`, `GET`, `err`) is ignored rather than
   misparsed. `pose_cm()`, `otos_cm()`, `wheels_mms()` and `duty_pct()`
   are the only conversions out of wire units.
2. **The fail-loud guards**, so "the instrument returned nothing" is an
   immediate failure and not a silent empty CSV: `require_stream()`
   (`DeadTelemetryError` if no frame arrives), `write_tlm_csv()`
   (`EmptyCaptureError` on a zero-frame capture) and
   `read_meta_sidecar()`, the read-side counterpart a chart tool uses
   to refuse plotting a run whose `.meta.json` records zero frames.
3. **The on-disk pose-CSV codec** — `write_pose_csv()` /
   `read_pose_csv()` / `POSE_CSV_COLUMNS`. See "One pose-CSV schema"
   under the tour family below, which is where the rule that a reader
   binds by name and REFUSES an unknown header is spelled out.

## Tour family — run, record, chart, score

All drive the on-robot programs in `test/test.ts` via `RUN` commands
and record what comes back.

- **`tour_run.py`** — the canonical run: camera used exactly twice
  (seed at start, score at end); the robot drives all four legs on its
  own sensors; no radio round-trips inside the tour.
- **`tour_capture.py`** / **`tour_watch.py`** — telemetry recorders
  (triggered vs. button-watch); write the pose/wheel CSVs. Both select
  a tour by NAME (`--tour {world,robot,wheels}` →
  `RUN tour <name>`), like everything else that drives `test.ts`; see
  "The `RUN` vocabulary" below for why a numeric selector against that
  program is a silent no-op.
- **`tour_chart.py`** / **`practice_chart.py`** — the standard
  matplotlib plots of those CSVs. `tour_chart.py --meta` takes a
  capture JSON whose `start_world_cm` is `[x_cm, y_cm, heading_DEG]`
  and uses it to align the odometry track into the field frame. Nothing
  in this repo WRITES that file — it is operator-supplied — so the unit
  is stated on the flag's own help text and converted at the read, not
  assumed: it was consumed as radians against a value the code had
  already converted, which would have handed a future writer using the
  tools' own `yaw_deg` convention a 57x rotation and a
  plausible-looking overlay.
- **`leg_analysis.py`** — turns a recording into a per-leg
  believed-vs-target table: commanded target, believed pose at move
  end, AprilCam ground truth where available, and a classification
  (on-target / heading-miss / straight-overrun / mid-leg-truncation)
  per leg. `heading-miss` is the "distance inside tolerance, heading
  outside it" case and is tested BEFORE the distance-sign split;
  without it a 30° heading miss on a leg that overran by 5 mm was
  reported as `straight-overrun` (2026-09-02 review, TL-10). It changes
  the verdict only — both error figures are still reported separately,
  in their own columns. A leaf consumer of `tlm.py` like every other
  tool here: it never decodes a wire line or a CSV column itself.
- **`tour_practice.py`** — repeated camera-scored runs from the start
  dot, repositioning between runs.

Two further variants — one that composed a tour host-side, one
camera-in-the-loop — were kept "for reference" until sprint 034 ticket
003 deleted them: nothing imported either, and the camera-in-the-loop
one demonstrated the doctrine this repo now forbids (it left the robot
stationary 73% of a run).

**One pose-CSV schema, bound by name (sprint 034 ticket 004).** The
three recorders above used to write three different `<stem>_pose.csv`
headers — wire units, cm/degrees, and cm/degrees plus wheel speeds —
and `tour_chart.py` chose its reader by COUNTING COLUMNS while assuming
wire units throughout. The cm/degree header also has eight columns, so
it was accepted: plotted 10x too small, heading divided by 100, OTOS
series read off the wrong columns, under a confident "closure N mm"
title, with nothing raised. `tlm.py` now owns the schema
(`write_pose_csv()`/`read_pose_csv()`, beside the `thdr`-keyed
telemetry parser that already binds by name — see this sprint's Design
Rationale 8):

    t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox_mm,oy_mm,oh_cdeg

in the wire's own units, plus the optional `vl_mms,vr_mms` pair for a
recorder whose chart plots the frame's own wheel speeds
(`tour_practice.py`). A row on either side of the codec is a decoded
telemetry frame, so `pose_cm()`/`otos_cm()`/`wheels_mms()` apply to a
CSV row exactly as they do to a live frame and no tool carries a scale
factor of its own. The reader binds every column by NAME, converts the
legacy headers this repo's own tools wrote (they are listed, with their
factors, in `tlm.py`'s `_LEGACY_POSE_SCHEMAS`), and REFUSES anything
else with a message naming the file and the header it found — a
header-count guess is never made. Existing recordings under
`captures/` were not rewritten; they read through the legacy path.

## Camera-parallax correction: one owner, never two (sprint 031 ticket 002)

A tag mounted above the field plane makes the camera report a
DILATED position -- displacements scale up the higher the tag rides,
because the reading is a projection through the tag's own height, not
a flat overhead measurement. There are two ways to correct that, and
this repo now enforces exactly one per tag:

1. **Daemon-owned (the convention for a REGISTERED tag).**
   `tools/camlink.py::Cam.register()` sends the tag's `mount_z_cm` to
   the aprilcam daemon's `register_tag()`; the daemon then applies the
   correction itself, so every position it reports for that tag
   (`world.x`, `world.y`) is already undilated. A tool consuming a
   registered tag's pose (via
   `tools/field.py::pose_from_registered_samples()`, which every
   registered-tag reader in this repo goes through) must use those
   coordinates AS-IS -- see `tools/field.py::registered_pose_distance()`,
   which takes no scaling-factor argument at all, by design.
2. **Tool-owned (only for a RAW/unregistered tag).** A tag never
   registered with the daemon reports raw, dilated coordinates; a tool
   reading it must apply its own correction -- a `parallax_k` divisor
   from `field_calibration.json`, alongside a `lever_cm` and (for
   heading) `robot_heading_from_tag_yaw()`. `tools/linefollow/` is the
   one place in this repo that does this deliberately, for vevov, and
   documents why in its own `DESIGN.md`.

**These two paths must never be mixed for the same tag.** Applying
BOTH -- registering `mount_z_cm` with the daemon AND also dividing by
a tool-side `parallax_k` -- corrects the same parallax twice. This
happened: `tools/field_dance.py` registered tovez's tag (path 1) but
its `drive()` and return-home check still divided by `parallax_k`
(path 2), so every drive read ~12% short until fixed
(`clasi/issues/parallax-k-and-registered-mount-z-correct-twice.md`,
MEASURED tovez 2026-09-04,
`captures/bench-acceptance-029-20260904d/field-dance-refit-run1.log`:
17.6 cm for a commanded 20, 35.3 cm for a commanded 40). It is
structurally the same shape as the +90 deg heading double-add fixed
earlier the same day (`field.pose_from_registered_samples()`'s own
docstring) -- two layers each believing they own a correction. The fix
removed `field_dance.py`'s `parallax_k` division entirely (it now
calls `field.registered_pose_distance()`, whose signature has nowhere
to plug a scaling factor back in) and dropped the now-inert
`parallax_k` key from `field_calibration.json`'s tovez entry.

**vevov's entry is deliberately NOT changed by this fix.** vevov's tag
is registered with a non-zero `mount_z_cm` (12.0) in
`field_calibration.json`, but `tools/linefollow/`'s scripts read it via
the RAW-tag path (their own `parallax_k`, never the daemon
registration), so no double-correction currently exists for vevov --
but nothing has confirmed which path vevov's daemon registration is
actually live under at any given moment, and re-fitting it onto the
single-owner convention without a fresh capture would just move the
bug rather than fix it. Flagged as a fast-follow re-fit, not silently
resolved.

**When adding a new camera-consuming tool:** read a registered tag's
pose through `field.pose_from_registered_samples()` and compute any
distance from it through `field.registered_pose_distance()` (or
another function with the same no-scaling-argument shape) -- never
introduce a fresh `parallax_k` division against a registered tag's
coordinates.

## Ground truth and calibration

- **`pivot_truth.py`** — camera vs. OTOS vs. odometry for rotations:
  is the robot misbehaving or the sensor mis-reporting? (A second tool
  measured the same thing through a v1 camera API and five subprocess
  launches per fix; sprint 034 ticket 003 deleted it.)
- **`rotation_check.py`** — commanded vs. gyro-measured rotation
  (floor + radio only; on the bench the body never rotates).
- **`turn_sweep.py`** — turn accuracy vs. yaw rate, camera-scored.
- **`otos_levercal.py`** — fits the OTOS lever arm from pivot circles
  (produced the 38.2 mm arm baked into `test/test.ts`).
- **`arc_capture.py`** — captures the whole on-device h(t) trajectory
  of a `RUN arc` split move. It samples on the robot and dumps
  afterwards rather than polling during the move: a request/reply round
  trip DURING a move is independently dangerous here, and subscribing
  v6 telemetry and then sending a `RUN` line hangs the link
  outright (`clasi/issues/cleartext-run-hangs-the-link-under-active-
  telemetry.md`).
- **`reposition.py`** — put the robot on a world point, camera-
  verified, seeding from measured truth rather than assumed placement.
  The **one** repositioning loop (sprint 034 ticket 009); `tour_run.py`
  and `tour_practice.py` both stage through it.
- **`park.py`** — the planner beside it: it picks a forward or REVERSE
  approach to minimise total commanded rotation, and absorbs a
  sub-tolerance heading residual into the next move instead of pivoting
  it away. Rotation is where this fleet's error lives, so "shortest
  path" is the wrong objective and "least total rotation" is the right
  one.

### One repositioning loop, and it is position-first (sprint 034 ticket 009)

`reposition.Repositioner.go()` drives to the point, **then** faces the
heading — two phases, never interleaved, so no `RUN goto` is ever sent
after a `RUN face`.

That ordering is not a stylistic choice. `tour_run.py` used to carry a
second implementation, `place()`, whose comment recorded why: an
in-place pivot walks the centre of rotation a centimetre or so, which
is enough to push the position error back over tolerance, so a loop
that re-checks both errors and picks one will answer a good heading
with another goto and undo it — *two runs started facing 98 and 94
degrees instead of west that way*. `Repositioner.go()` was exactly that
re-checking loop. The merge kept `place()`'s ordering, `go()`'s
signature and `check_path()`'s refusal; `place()` is gone, and the
measurement moved into `go()`'s docstring with the code it justifies.
`tour_run.make_repositioner()` supplies the one caller-specific
number — **1.5° heading tolerance, not the class default 5°**, because
an open-loop tour turns start-heading error straight into corner error
(leg × sin θ) and 4° on a 100 cm leg is already 7 cm.

### One `wrap()`, closed at the upper end (sprint 034 ticket 009)

`field.wrap()` maps an angle into **(-180, 180]** — `wrap(180)` and
`wrap(-180)` are both **+180**, i.e. half a revolution reads as a LEFT
turn. Sprint 005 consolidated eight copies into `field.py` and four
grew back, three of them written as the modulo idiom, which closes the
*other* end (`[-180, 180)`); `leg_analysis._wrap_deg()`'s docstring
claimed this module's interval while its body returned the other one.
±180 is in the standard `PIVOTS` list, so the boundary is a value this
fleet actually commands. The upper end wins because `turn_total()` is
`commanded + wrap(measured − commanded)` and a commanded ±180 must come
back as the half-turn that was asked for. Every other definition and
every inline copy under `tools/` and `tests/calibration/` now imports
it — including `otos_levercal.py`'s `atan2(sin, cos)` spelling, which
already *agreed* and was folded in anyway, because a lookalike still
costs the next reader a derivation.
`tests/tools/test_angle_wrap_ownership.py` is the source-level guard.

### Unwrapping a pivot: `field.turn_total()` is the one owner (sprint 034 ticket 001)

`tools/field.py` already owns every angle-math primitive with no I/O of
its own, and `turn_total(commanded, measured)` joins `wrap()` there:
it returns the total physical turn in degrees by unwrapping the
measured heading difference onto the revolution the *commanded* angle
names — `commanded + wrap(measured - commanded)`, one line, no `round()`
and no revolution count.

`rotation_check.py` and `pivot_truth.py` both call it and keep no
private copy. What they each used to carry could not resolve a ±180°
pivot: `round(commanded / 360.0)` is **0** for ±0.5 under banker's
rounding, collapsing the whole expression to `wrap(after - before)`, so
a 183° physical turn (over-rotation is this fleet's norm) read **−177°**
and `gyro / commanded` came back **−0.98** — a sign-flipped term
averaged in with the rest. Anchoring on the command handles the ±180
boundary like any other angle, which is also why `pivot_truth.py` no
longer needs its "pick whichever of gyro, gyro ± 360 lands nearest the
camera" special case — a branch that made the gyro's own reading depend
on the camera being trustworthy.

`pivot_truth.py`'s `gyro_over_camera()` guards the paired division:
below `NO_ROTATION` (0.5°) of camera yaw it returns `None`, and the run
reports "camera saw no rotation" naming
`.claude/rules/playfield-testing.md`'s **robot-is-switched-OFF** check
rather than raising `ZeroDivisionError` and losing the report at the
moment it had the most to say. Odometry reports the full commanded turn
on a robot with no motor power; the camera is the only instrument that
can contradict it.

### Scoring a corner: one bounded window each (sprint 034 ticket 002)

`field.score_corners()` scores corner *k* over
`rows[used : first_approach(k + 1)]` — the samples between the previous
corner's claim and the first sample within `field.CORNER_WINDOW_RADIUS`
(15 cm) of the NEXT dot in `order`. The last corner keeps the rest of
the run. The bound is searched from `used + 1`, so a window can never
come back empty, and `used` advances to `besti + 1`, so two consecutive
corners cannot claim one sample.

Of the two remedies the 2026-09-02 review offered for TL-08 (bounded
window, or one monotone assignment across all four corners) this is the
first — it keeps the existing forward-scan shape and its monotonicity
guarantee rather than replacing the algorithm. What it fixes: the
unbounded scan let corner 0 search to the END of the recording, so a lap
that passes NW early and re-approaches it on its closing leg scored NW
from the LATE sample, pushed `used` to the tail, and left SW/SE/NE a
handful of final samples — one good run read as three bad corners
(08-26 C-16, reopened as TL-08).

### The geofence: one field size, checked by every planner (sprint 034 ticket 007)

`field.LIMITS` (±67.15 / ±44.65 cm, the 134.3 × 89.3 cm field) less
`field.MARGIN` (12 cm) is the only field size in the repo, and
**`field.usable_half_extent()` is the one place that subtraction
happens** — `(55.15, 32.65)` cm, derived, never a second typed pair.
`tests/host/test_run_tour_programs.py` used to carry its own
`_FIELD_MM`/`_MARGIN_MM` (a 55.0 × 35.0 cm usable field): x agreed to
1.5 mm, y was 2.35 cm LOOSER, so a `.tour` figure could pass its sizing
gate and still be outside the fence every driving tool enforces. That
pair is gone; the test derives from this accessor.

`field.require_clear_path(waypoints, what=...)` is the planners' gate:
it runs `check_path()` (waypoints **and** the segments between them)
and raises `field.PathRefused`, naming the offending points, the
refused move and the usable extent it applied. It **refuses; it never
clamps** — a silently shortened move ends with an operator who believes
the commanded geometry ran.

Callers today, i.e. every surviving tool that commands motion to a
COORDINATE:

- **`reposition.py`** — `Repositioner.check_path()`, called by `go()`
  ahead of the seed (the seed is already a command on the wire). Since
  sprint 034 ticket 009 this is the only repositioning gate there is:
  `tour_run.place()` carried a second copy and was merged in.
- **`tour_run.py`** — inherits it through `Repositioner.go()`; `main()`
  catches `PathRefused` and abandons the run rather than tracebacking.
- **`tour_practice.py`** — inherits it through `Repositioner.go()`;
  prints the refusal and skips the run.
- **`tests/calibration/turn_calibration.py`** — already called
  `check_path()` directly at seven sites (arcs, straights, the G5
  `WHEELS_V` travel, the square, the segment protocol).

Everything else that drives (`pivot_truth.py`, `turn_sweep.py`,
`rotation_check.py`, `arc_capture.py`, `tools/linefollow/`,
`tests/calibration/{distance,mount,lag_measure,field_dance}.py`) issues
RELATIVE moves — pivots, `MOVE_X` legs, `MOVE_V` steps — with no
coordinate to check a path against; they are out of this gate's scope,
not exempt from the rule.

The RECORDERS score the fence after the fact on rows they already hold:
`tour_run.py` and `tour_watch.py` both print `field.clears_margin()`
(clear / LEFT THE MARGIN, with the usable extent) in their score line.

**`field.py` still imports nothing but `math`** — pinned by
`tests/tools/test_field.py`. That invariant is what lets
`tests/calibration/*` and `tests/host/*` import it on a machine with no
robot attached, and it is why the geofence is wired in by having the
PLANNERS call the check, never by teaching `field.py` about a link.

## The `RUN` vocabulary: named on the robot, numeric on the rig

`RUN <name> [<arg>...] #<id>` is an ordinary sequenced v6 verb. It
decodes in `wire_handler.cpp`, is checked against the registry `FUNCS`
lists, and is handed to whichever on-robot program is flashed. (Before
2026-09-07 it was a cleartext `RUN:<name>` line matched by prefix ahead
of the v6 grammar; that carve-out is gone, and with it the unsequenced
spelling — an unsequenced `RUN` now parses as `#0` and is dropped.)

The two programs answer it differently, and which one is on the board
decides whether a numeric `RUN <n>` means anything:

| program | dispatch | numeric `RUN <n>` |
|---|---|---|
| `test/test.ts` — the playfield robot | `diffDrive.onRun("<name>", ...)`, matched on the exact string | **refused with `err 1`**: no numeric name is registered, and since 2026-09-07 an unregistered name is rejected at the wire instead of silently doing nothing. The old failure — tool runs to completion, prints numbers, robot never moved — is no longer reachable. |
| `test/testrig.ts` — the zeguz drum rig | one `diffDrive.onRunCommand()` catch-all | **works**: the catch-all makes every name dispatchable (and tells the wire so, via `registerRunCatchAll`), so `RUN 20 #1` puts `"20"` in `name` and the handler parses the number from there for `rigExec()` |

So `otos_bench.py`'s numeric vocabulary (probe, zero, stream,
calibrate, servo pin/pulse, drum speed, lever arm) is **live**, not
dead — it is the one tool in this directory that deliberately speaks
numbers, because it is the one tool that drives `testrig.ts`. It is a
console, not a bench-run recorder, and it is out of scope for
everything the tour family does. Every tool that drives `test.ts` —
the tours, the recorders, the ground-truth probes, `arc_capture.py` —
speaks named verbs (`RUN tour world`, `RUN pivot <deg>`, `RUN cal`,
`RUN arc <deg>`, `RUN fix`); `tests/tools/test_run_verbs.py` pins the
exact strings against a fake link so a numeric regression fails on the
host rather than on the field.

A defect here reads as a healthy run, which is why it is pinned:
`testrig.ts` used to parse `arg` rather than `name`, which is 0 for
every command and matches no `rigExec()` branch, so the whole rig
console was a no-op that printed plausible output. `test/testrig.ts`'s
own comment above `onRunCommand()` records the trap.

Telemetry is no longer a gap: the v6 `thdr`/`t` frame replaced the
retired cleartext `TLM:` stream, and `tools/tlm.py` (above) is its
host-side parser. `DIAG` is retired with no replacement — a recorder
that wants wheel speeds reads `vl`/`vr` out of the telemetry frame,
which needs no calibration constant and survives the radio, where
mid-move polling is forbidden outright.
