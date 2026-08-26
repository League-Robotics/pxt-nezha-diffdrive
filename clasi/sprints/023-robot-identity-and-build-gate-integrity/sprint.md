---
id: '023'
title: Robot identity and build-gate integrity
status: ticketing
branch: sprint/023-robot-identity-and-build-gate-integrity
use-cases: [SUC-001, SUC-002]
issues:
- id-verb-reports-a-baked-constant-not-the-machine-name.md
- make-deploy-accepts-a-silently-incomplete-hex.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 023: Robot identity and build-gate integrity

## Goals

- Make `ID` report the actual per-board machine name, not a fleet-wide
  constant, so `ID` and `HELLO` agree on which robot answered.
- Make `make_deploy.py`'s build-checkpoint gate actually detect a
  truncated or under-compiled hex, including the zero-compiled-files
  case, so "flashable hex confirmed" is trustworthy again.
- Sequence the build-gate fix first, so the ID fix's own hardware
  acceptance test (flash two boards, compare `ID` vs `HELLO`) rests on a
  gate that means what it says.

## Problem

Two related integrity gaps in this repo's identity and build tooling:

1. `WireHandler::execId` (`src/comms/wire_handler.cpp:704`) replies
   `id <drivetrain> <profile> <version>` using `kProfile`, a
   compile-time constant. Every board that runs an unparameterized build
   reports the same `profile` value regardless of which physical robot
   it is; a robot was misidentified from its `ID` reply during sprint
   022's flash verification. `Protocol::buildIdentity()` already reads
   the real per-board identity (`microbit_friendly_name()`) into
   `identity.name`, but `execId` never emits it.

2. `make_deploy.py`'s build-output triage (`classify_attempt()`) judges
   success purely from the compile log. A stale vendored
   `codal-microbit-v2` checkout produced a `binary.hex` 27% short
   (1,046,410 vs 1,442,546 bytes) with a clean exit status and nothing
   in the log to flag it (sprint 016 ticket 007). The same class of
   failure — a build serving entirely from a stale cache, compiling
   nothing — recurred during sprints 018 and 022, and again on
   2026-08-26, each time producing zero `Building CXX object` lines and
   passing anyway.

The two are ordered: fixing (1) requires flashing two boards and
trusting that the hex which reaches them actually contains this
sprint's code. That trust doesn't currently exist, so (2) must land
first.

## Solution

**Build-gate integrity** (`make_deploy.py`): add two post-build
assertions, both pure functions parallel to the existing
`classify_attempt()`/`_count_universal_hex_blocks()` pattern, both
unit-testable without a real build:
- A size floor on `binary.hex`, set below the measured
  1,423,241–1,463,606 byte band of real checkpoints and comfortably
  above the 1,046,410-byte truncated hex that exposed the gap.
- A translation-unit presence check: all ten `nezha-diffdrive` `.cpp`
  files must appear as `Building CXX object` lines in the build output.
  Zero compiled lines (the recurring stale-cache shape) must fail this
  check the same as any other missing subset — not be special-cased as
  "nothing to rebuild, therefore fine."

Both checks run inside `build()`, after the existing universal-hex
check, before a hex is ever reported ready. A genuine clean build must
still pass; a truncated or cache-served build must fail loudly with a
specific reason, the same failure shape `classify_attempt()` already
uses.

**Robot identity** (`ID` verb): append `identity.name` (already
populated from `microbit_friendly_name()`) as a fourth field on `ID`'s
reply: `id <drivetrain> <profile> <version> <name>`. This is additive —
no cross-repo consumer parses the reply today — so the three files that
pin the 3-field shape outside this repo
(`radio-robot-lib/docs/design/protocol.md`,
`.../tests/protocol/golden_vectors.txt`,
`.../src/protocol/protocol_handler.cpp`) are unmodified by this
sprint; this repo's `ID` reply becomes a superset of the pinned spec,
not a fork of it, until that sibling repo is updated to describe the
fourth field (tracked as a follow-up, not fixed here — see Migration
Concerns).

`profile`'s own documented meaning is corrected to match reality: it
names which robot's config this hex was built *against* (deploy-time
target selection, via `tools/make_deploy.py --robot`), not which
physical board is running it. `name` is the only field this sprint
treats as authoritative identity, because it is read from silicon at
runtime and cannot be stale. This directly reverses the direction of a
same-day, out-of-process commit (`90183f8`, "Bake kProfile per-robot at
deploy time") that treated `profile` as identity — Eric's direction for
`ID` explicitly rejects that approach for identity purposes. This
sprint keeps the `_inject_profile()` deploy-time-baking mechanism (a
legitimate, if lower-stakes, piece of build provenance) but stops
presenting its output as proof of which board is on the wire.

Not addressed here: the three-way contradiction over which robot's
measurement the kernel's *tuning* defaults (`Rig::travelCalib`,
`trackWidth`, ...) actually come from
(`clasi/issues/three-way-contradiction-on-which-tuning-bake-the-kernel-defaults-are.md`).
That is a measurement question, unrelated to wire identity, and
explicitly out of scope.

## Success Criteria

- `uv run pytest` includes new tests proving: a synthetic short hex
  fails the size floor; a synthetic build log with fewer than ten
  `Building CXX object` lines (including zero) fails the
  translation-unit check; a genuine clean build log/hex still passes
  both checks.
- `ID`'s golden-vector test
  (`tests/host/test_wire_grammar.py::test_id_golden_vector`) expects
  the appended name field.
- Two different boards (vevov, tovez), each flashed from a build gated
  by the hardened `make_deploy.py`, each report their own name over
  `ID`, and that name agrees with the same board's `HELLO` reply.
- Full suite still passes at (or above) the 718-test baseline;
  `uvx ruff check tools tests`,
  `node_modules/.bin/tsc --noEmit -p tsconfig.json`, and
  `clasi design validate` are all clean.

## Scope

### In Scope
- `tools/make_deploy.py`: size-floor and translation-unit-count
  post-build checks, plus their negative and positive tests.
- `src/comms/wire_handler.cpp`: `execId` emits `identity.name` as a
  fourth field.
- `src/comms/protocol.cpp`: `kProfile`'s doc comment corrected to
  describe build-target selection, not board identity.
- `tests/host/test_wire_grammar.py`: golden-vector update for `ID`'s
  new reply shape.
- Hardware build-checkpoint + flash + `ID`/`HELLO` agreement check on
  vevov and tovez.

### Out of Scope
- Stale-vendored-checkout detection by comparing resolved `dockercodal`
  revision against the `codal.json` pin (explicitly deferred by the
  issue itself).
- Resolving the three-way tuning-bake contradiction (separate issue,
  needs hardware measurement).
- Updating radio-robot-lib's pinned protocol spec/fixture/
  implementation to describe the fourth `ID` field (different repo,
  outside this sprint's write scope) — flagged as a follow-up.
- Any change to `src/core/diffdrive.{h,cpp}` (vendored, byte-stable).

## Test Strategy

Both code tickets are host-testable without hardware:
- `make_deploy.py`'s two new checks are pure functions taking
  already-captured build output / a hex path, tested the same way
  `classify_attempt()` and `_count_universal_hex_blocks()` already are
  — synthetic fixtures, no subprocess, no real build — in
  `tests/tools/test_make_deploy_triage.py`. Required negative tests:
  short hex under the floor; build log missing one or more of the ten
  `.cpp` files; build log with zero `Building CXX object` lines.
  Required positive test: a real clean-build log/hex-size fixture still
  passes.
- The `ID` wire-format change is host-testable via
  `tests/host/test_wire_grammar.py`'s existing mock-adapter harness
  (`wg.set_identity(...)`, `wg.feed(b"ID #1\n")`) — no hardware needed
  to prove the reply shape.
- Only the final ticket needs hardware: a real `make_deploy.py` build
  (through the now-hardened gate) flashed to both vevov and tovez, then
  `ID`/`HELLO` compared on each over their own transport (vevov via
  zavaz relay ch4, tovez via USB — getez not connected on ch3).

## Architecture

**Sizing: Substantial**, by module count rather than inherent
per-change complexity — this sprint touches two unrelated modules
(`tools/` deploy tooling and `src/comms/` wire protocol) with no
relationship to each other, which exceeds the compact tier's literal
"one module" test even though neither change alone introduces a new
module, cross-module dependency, dependency-direction change, or
data-model change.

### What Changed

**`tools/make_deploy.py` (deploy/build-gate tooling)** — `build()`
gains two post-build assertions after the existing
universal-hex-block check: a `MIN_HEX_SIZE_BYTES` floor (pure
comparison against `os.path.getsize(hex_path)`) and a translation-unit
presence check (pure function scanning the captured build output text
for `Building CXX object` lines naming each of the ten
`nezha-diffdrive/src/**/*.cpp` files — `src/comms/protocol.cpp`,
`src/comms/radio_transport.cpp`, `src/comms/serial_transport.cpp`,
`src/comms/wire_adapter.cpp`, `src/comms/wire_handler.cpp`,
`src/core/diffdrive.cpp`, `src/motion/motion_engine.cpp`,
`src/platform/nezha_port.cpp`, `src/platform/otos_port.cpp`,
`src/shims.cpp` — confirmed by `find src -name '*.cpp'` during
planning), explicitly treating a zero-match result as failure rather
than a distinguishable "nothing to build" case. Both follow the
existing `classify_attempt()`/`_count_universal_hex_blocks()` shape:
pure, unit-testable against saved/synthetic text, no subprocess. The
real log format was confirmed against sprint 016 ticket 007's captured
build evidence: `[ 93%] Building CXX object
CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/comms/protocol.cpp.obj`.

**`src/comms/` (wire protocol stack)** — `WireHandler::execId`
(`wire_handler.cpp`) appends `identity.name` to its reply.
`Identity::name` is already populated by `Protocol::buildIdentity()`
from `microbit_friendly_name()` and already reaches the wire via
`HELLO`'s banner (`sendBanner()`, `wire_handler.cpp:1177`); this sprint
adds a second read site for a value that already exists, not a new
data path. `protocol.cpp`'s doc comment for `kProfile` (introduced by
the just-landed `90183f8` OOP commit, which is not this sprint's own
work but sits directly in this sprint's path) is corrected to describe
deploy-time build-target selection rather than board identity — no
runtime behavior changes there; `_inject_profile()`/
`tools/make_deploy.py --robot` are unchanged.

Neither module gains a new dependency on the other, on a new external
system, or on new stored state. No component/module diagram is
included: the two changes don't compose with each other in any way
beyond ticket ordering, so a diagram would show two disconnected boxes
and clarify nothing beyond what this section's prose already says (same
reasoning sprint 020 used to omit its diagram).

### Design Rationale

**Decision: append `name` as a fourth `ID` field rather than replacing
`profile` or reordering fields.**
- *Context*: `id <drivetrain> <profile> <version>` is pinned in three
  files in `radio-robot-lib` (spec, golden-vector fixture, an
  independent handler implementation), none writable from this repo
  this sprint. Confirmed by reading all three during planning:
  `docs/design/protocol.md:518`'s table row, `tests/protocol/
  golden_vectors.txt:89`'s `SETUP identity ... / IN ID #1` vector, and
  the parallel handler implementation.
- *Alternatives considered*: (a) replace `profile` with `name` in
  place — rejected; it destroys the still-useful build-provenance
  signal rather than adding to it, for no positional-parsing benefit.
  (b) reorder fields so `name` leads (matching `HELLO`'s
  `<name> <serial>` order) — rejected; `HELLO`'s shape isn't `ID`'s
  shape, and no consumer parses either reply positionally today, so
  there's nothing to gain by matching it. (c) append as field 4 —
  chosen; a cross-repo grep (per the issue) found zero consumers that
  parse `ID`'s reply at all, so appending is safe now and is the
  smallest textual diff against the pinned spec for whoever updates
  `radio-robot-lib` later.
- *Consequences*: this repo's `ID` reply is a strict superset of the
  pinned spec until `radio-robot-lib`'s three files are updated to
  describe the fourth field — a real, acknowledged divergence, tracked
  as a follow-up (see Migration Concerns), not fixed here because it's
  a different repo.

**Decision: keep `_inject_profile()`/`kProfile` deploy-time baking,
redefine its documented meaning, rather than removing it.**
- *Context*: `kProfile` was made deploy-time-baked by an out-of-process
  commit (`90183f8`, same day) specifically to fix the "every board
  says tovez" bug — using exactly the mechanism (bake a value at
  deploy time from the robot JSON) that Eric's direction for `ID`
  explicitly rejects as an identity source, for the same reason
  `radio-robot-elite`'s `Config::kRobotProfileName` was rejected: a
  baked value is only as correct as the build that produced it.
- *Alternatives considered*: (a) revert `90183f8` and
  `_inject_profile()` entirely, restoring a fixed `profile`
  placeholder — rejected; it throws away a working, tested
  build-provenance signal (which robot's config this hex was built
  against) that is a legitimately different fact from board identity
  and remains useful for spotting "this board is running the wrong
  robot's build." (b) keep `_inject_profile()`, redocument `profile` as
  build-target selection (not identity), let `name` carry identity —
  chosen; smallest change, keeps a genuinely useful signal, and
  directly answers this sprint's own open question about what
  `profile` still means once `name` is on the wire.
- *Consequences*: `profile` and `name` on one `ID` reply can
  legitimately disagree (`profile` says which robot's config the hex
  targeted; `name` says which physical board is answering) — that
  disagreement is itself diagnostic (a board flashed with the wrong
  robot's build), not a bug, and must not be "fixed" by forcing them to
  match.

### Migration Concerns

- **Cross-repo spec drift, acknowledged not fixed**:
  `radio-robot-lib/docs/design/protocol.md:518`,
  `.../tests/protocol/golden_vectors.txt:89`, and
  `.../src/protocol/protocol_handler.cpp:623` still describe/assert the
  3-field `ID` reply. This repo's reply becomes a 4-field superset. No
  known consumer parses positionally past field 2, so nothing breaks
  today, but this is real drift a human should resolve by filing a
  follow-up in `radio-robot-lib` to document (and optionally assert on)
  the optional fourth field. Not filed as part of this sprint —
  outside this repo's write scope; flagged for team-lead/stakeholder
  follow-up.
- **No data migration**: no persisted state changes shape in either
  ticket.
- **Deployment sequencing**: the build-gate ticket must be implemented
  and verified before the hardware-verification ticket runs, per the
  ORDERING constraint — encoded as ticket numbering (001 before 003),
  not a formal `depends-on`, since ticket 002 (the `ID` code change)
  has no code dependency on ticket 001.

### Open Questions

1. Should `radio-robot-lib`'s pinned protocol spec/fixture be updated
   in the same timeframe as this sprint (a separate PR in that repo),
   or left to drift until something actually needs the fourth field?
   This sprint recommends filing a follow-up issue there but does not
   decide its priority — that's a cross-repo/stakeholder call.
2. `MIN_HEX_SIZE_BYTES`'s exact value is a planning-time suggestion
   (see ticket 001), not a fixed requirement — the implementer should
   confirm it against the current measured band before landing it,
   since the band may have shifted since sprint 022's checkpoint.

## Use Cases

### SUC-001: Operator identifies a board unambiguously over the wire
Parent: None — this is an internal wire-protocol identity guarantee;
`docs/design/usecases.md` covers the PXT extension's block-level API
(driving, pivoting, telemetry), not the wire protocol's own identity
contract, so no existing UC applies.

- **Actor**: Operator/tooling querying a robot over USB or radio (e.g.
  `tools/robotlink.py`, or a human doing manual flash verification, as
  in sprint 022).
- **Preconditions**: The robot is flashed with this sprint's firmware
  and is reachable over its transport.
- **Main Flow**:
  1. Operator sends `ID #<id>`.
  2. Firmware replies `id <drivetrain> <profile> <version> <name>`,
     where `<name>` is read from `microbit_friendly_name()` at call
     time.
  3. Operator sends `HELLO` (or receives its unsolicited banner) and
     reads `<name>` from `device NEZHA2 robot <name> <serial>`.
  4. Operator confirms the two `<name>` values agree.
- **Postconditions**: The operator has confirmed which physical board
  answered, independent of which build/config it was flashed with.
- **Acceptance Criteria**:
  - [ ] `ID`'s reply includes the board's `microbit_friendly_name()` as
        its fourth field.
  - [ ] `ID` and `HELLO`'s name fields agree on every flashed board
        (verified on vevov and tovez).
  - [ ] `tests/host/test_wire_grammar.py::test_id_golden_vector` (and
        any renamed/added equivalent) exercises the four-field reply.

### SUC-002: Build-checkpoint gate rejects an under-compiled hex before it is trusted
Parent: None — internal deploy-tooling guarantee, not user-facing; no
corresponding UC in `docs/design/usecases.md`.

- **Actor**: `tools/make_deploy.py`'s `build()`, invoked by a human or
  agent running a sprint build checkpoint.
- **Preconditions**: A `pxt build` attempt has completed with a clean
  exit and produced a `binary.hex`.
- **Main Flow**:
  1. `build()` runs the existing triage (`classify_attempt`) and
     universal-hex-block check.
  2. `build()` checks `binary.hex`'s size against `MIN_HEX_SIZE_BYTES`.
  3. `build()` scans the captured build output for `Building CXX
     object` lines naming all ten `nezha-diffdrive` `.cpp` files.
  4. If either check fails — including the all-zero-lines case —
     `build()` exits with a specific, actionable reason, the same way
     an `UNKNOWN`/`HARD_FAILURE` verdict does today.
  5. Only a hex that passes every check (existing + these two new
     ones) is reported ready to flash.
- **Postconditions**: A hex that reaches `flash()` has been confirmed,
  mechanically, to be full-sized and fully compiled — not just
  log-clean.
- **Acceptance Criteria**:
  - [ ] A synthetic short hex (below the floor) fails `build()`.
  - [ ] A synthetic build log missing one or more of the ten `.cpp`
        files' `Building CXX object` lines fails `build()`.
  - [ ] A synthetic build log with zero `Building CXX object` lines
        fails `build()` (not treated as "nothing to rebuild, therefore
        fine").
  - [ ] A genuine clean-build log and correctly-sized hex still pass
        `build()`.

## GitHub Issues

(None — this sprint's two issues are local CLASI issues in
`clasi/issues/`, not GitHub issues.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [x] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [x] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan
- [x] Both robots (vevov, tovez) on the bench and charged, for ticket
      003's hardware verification

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Harden make_deploy.py's build gate: hex size floor and translation-unit presence check | — |
| 002 | ID verb reports the machine name, not the baked profile constant | — |
| 003 | Build checkpoint: flash vevov and tovez, verify ID/HELLO name agreement on each | 001, 002 |

Tickets execute serially in the order listed.
