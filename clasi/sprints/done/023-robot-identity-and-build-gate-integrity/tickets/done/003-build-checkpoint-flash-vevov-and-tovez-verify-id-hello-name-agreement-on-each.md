---
id: '003'
title: 'Build checkpoint: flash vevov and tovez, verify ID/HELLO name agreement on
  each'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
- '002'
github-issue: ''
issue:
- id-verb-reports-a-baked-constant-not-the-machine-name.md
- make-deploy-accepts-a-silently-incomplete-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: flash vevov and tovez, verify ID/HELLO name agreement on each

## Description

This sprint's own build-checkpoint-and-flash-verification ticket,
following the established per-sprint convention (sprints 014-019, 022
each ended with one). It is the acceptance test for both of this
sprint's issues, and it is the reason ticket 001 (build-gate hardening)
must be genuinely complete and passing before this ticket runs: this
ticket's own trust in "the hex that reached each board is really this
sprint's code" now depends on `make_deploy.py`'s hardened gate meaning
what it says.

Run a real `make_deploy.py` build (through the now-hardened gate from
ticket 001, carrying ticket 002's `execId` change), flash it to **both**
vevov and tovez, and confirm on each board that `ID`'s new fourth field
agrees with that same board's `HELLO` reply. This is the acceptance test
Eric specified directly in the issue: "Flash two different boards. `ID`
must return each board's own name, and that name must agree with the
same board's `HELLO` reply. Agreement between `ID` and `HELLO` is the
acceptance test."

**Hardware notes** (from `.claude/rules/playfield-testing.md` and this
sprint's own briefing):
- vevov: channel 4, reachable via the zavaz relay.
- tovez: channel 3, but the getez relay is **not connected** — USB only.
- Both boards are on the bench, charged.
- `mbdeploy probe` is the only authority on ports and intermittently
  reports a present board as `CONN=no` — don't take one `CONN=no` read
  as proof a board is absent; re-probe.
- Opening/reopening a USB serial port resets the target program (pose
  and any other in-memory state re-zeros) — plan each board's
  verification as one serial/radio session, don't assume state survives
  a port close between `ID` and `HELLO`.

This ticket needs no camera and no motion — it is a wire-protocol
identity check, not a driving test. Do not drive either robot as part
of this ticket.

## Acceptance Criteria

- [x] A full `make_deploy.py` build for vevov (`--robot vevov`) passes
      the hardened gate from ticket 001 (hex size floor, all-ten-files
      translation-unit check) with no failures.
- [x] A full `make_deploy.py` build for tovez (`--robot tovez`)
      similarly passes the hardened gate.
- [x] vevov, flashed with its build, replies to `ID` with its own name
      as the fourth field, and that name matches vevov's `HELLO` reply
      name.
- [x] tovez, flashed with its build, replies to `ID` with its own name
      as the fourth field, and that name matches tovez's `HELLO` reply
      name.
- [x] vevov's and tovez's `ID` name fields **differ from each other**
      (proving this isn't two boards coincidentally both showing a
      stale shared constant — the original defect this sprint fixes).
- [x] Both boards' `ID` replies still show fields 0-2
      (`drivetrain`/`profile`/`version`) in the pre-existing 3-field
      shape, undisturbed by the append.
- [x] Build evidence recorded in this ticket (or its completion note):
      hex byte sizes for both builds, and the full set of ten
      `Building CXX object` lines confirmed present for both, matching
      the documentation convention of prior build-checkpoint tickets
      (e.g. sprint 016 ticket 007).

## Implementation Plan

**Approach**: Sequential, one board at a time (matching sprint 022
ticket 003's proven pattern): build for vevov, flash, verify over its
relay; build for tovez, flash, verify over USB. Use `tools/robotlink.py`
(or equivalent existing wire-session tooling) to send `ID` and read
`HELLO`'s banner or an explicit `HELLO` request within one serial/radio
session per board, per the reopen-resets-state note above.

**Files to modify**: None — this ticket is verification, not code. If
verification surfaces a defect in tickets 001 or 002's work (e.g. a
buffer truncation, a build that doesn't actually carry the code change),
fix it here or reopen the relevant ticket, per normal practice.

**Files to create**: None, beyond this ticket's own recorded build
evidence.

## Testing

- **Existing tests to run**: The full suite gate happens once at
  `close_sprint`, not per-ticket (per `.claude/rules/source-code.md`) —
  this ticket's own verification is the hardware check described above,
  not a pytest run.
- **New tests to write**: None — this ticket is a hardware acceptance
  check, not a host-testable change. (Tickets 001 and 002 already carry
  the host-level regression tests for their respective code changes.)
- **Verification command**: `uv run python tools/make_deploy.py --robot
  vevov --flash` and `uv run python tools/make_deploy.py --robot tovez
  --flash`, followed by manual `ID`/`HELLO` comparison on each board
  over its own transport.

## Verification Evidence (2026-08-26)

**Before-evidence (the defect, captured live from vevov over USB prior
to this ticket's work, provided in the ticket brief):**

```
HELLO -> device NEZHA2 robot vevov 1198504156
ID    -> id diffdrive tovez 1.0.10
```

vevov answered `ID` with a stale `tovez` profile and no fourth field —
exactly the defect this sprint's issues describe.

### 1. Builds

**vevov, attempt 1 — gate FIRED (correctly).** `uv run python
tools/make_deploy.py --robot vevov` against the `.tmp/deploy-head`
scratch copy left over from prior session work failed with:

> `BUILD FAILED: not all nezha-diffdrive translation units were
> compiled (missing 'Building CXX object' lines for:
> src/comms/radio_transport.cpp, src/comms/serial_transport.cpp,
> src/core/diffdrive.cpp, src/motion/motion_engine.cpp,
> src/platform/nezha_port.cpp, src/platform/otos_port.cpp,
> src/shims.cpp)`

Only 3 of 10 nezha-diffdrive translation units had fresh `Building CXX
object` lines (`protocol.cpp`, `wire_handler.cpp`, `wire_adapter.cpp` —
the files ticket 002 touched); the other 7 were served from a stale
incremental cmake cache in the leftover scratch copy. This is exactly
the failure mode ticket 001's gate exists to catch — a clean exit with
a real but under-compiled hex — and it fired correctly, not a
ticket-001 regression. Remedy applied per the gate's own message and
this ticket's brief: `shutil.rmtree('.../.tmp/deploy-head')` (Python),
then rerun.

**vevov, attempt 2 (post-wipe) — gate passed silently.** Full clean
build: 180 total `Building CXX object` lines, all 10 nezha-diffdrive
files confirmed present (`src/comms/protocol.cpp`,
`src/comms/radio_transport.cpp`, `src/comms/serial_transport.cpp`,
`src/comms/wire_adapter.cpp`, `src/comms/wire_handler.cpp`,
`src/core/diffdrive.cpp`, `src/motion/motion_engine.cpp`,
`src/platform/nezha_port.cpp`, `src/platform/otos_port.cpp`,
`src/shims.cpp`). `hex: .../deploy-head/built/binary.hex (1467296
bytes) [attempt 1]`. Independently verified: `os.path.getsize` ==
1,467,296 bytes (3,690 bytes above the previously-measured band's high
end of 1,463,606 — expected, since this build newly carries ticket
002's `execId` fourth-field append, which grows the binary slightly);
zero `:0400000A` universal-hex markers (plain V2 hex); no `dockeryt/`
references anywhere under the scratch tree. Radio channel confirmed
read from `radio-robot-lib/config/robots/vevov.json`
(`connection.radio_channel` = 4); baked profile confirmed = `vevov` (as
read back live from the board's own `ID` reply, see below). Boot-banner
injection independently confirmed by rebuilding the same scratch copy a
third time (build-only, no reflash — the board was already correctly
flashed from attempt 2's byte-identical hex, same 1,467,296-byte size)
and reading `.tmp/deploy-head/test/test.ts` directly: `const
BOOT_VERSION = "26.08"` / `const BOOT_ROBOT = "vevov"`. The on-device
skate-icon display itself was not observed — that check is the
operator's.

**tovez — gate passed silently, first attempt.** `.tmp/deploy-head`
wiped preemptively before this build to guarantee a full clean compile
(avoiding the same stale-cache shape hit on vevov's first attempt).
Full clean build: 180 total `Building CXX object` lines, all 10
nezha-diffdrive files confirmed present. `hex: .../deploy-head/built/
binary.hex (1467251 bytes) [attempt 1]`. Independently verified:
`os.path.getsize` == 1,467,251 bytes; zero `:0400000A` markers; no
`dockeryt/` references. Radio channel confirmed read from
`radio-robot-lib/config/robots/tovez.json` (`connection.radio_channel`
= 3); baked profile confirmed = `tovez` (via live `ID` reply, below).
Boot-banner injection confirmed directly by reading
`.tmp/deploy-head/test/test.ts` right after this build (before it was
wiped again for the vevov re-check above): `const BOOT_VERSION =
"26.08"` / `const BOOT_ROBOT = "tovez"`.

### 2. Flashing

**vevov.** `mbdeploy probe` re-run immediately before flashing (never
trusted from an earlier read): `tovez` CONN=yes
`/dev/cu.usbmodem2121202`, `vevov` CONN=yes `/dev/cu.usbmodem2121102`,
`zavaz` CONN=yes `/dev/cu.usbmodem212202` (ROLE/COMMON NAME columns
ignored per `.claude/rules/playfield-testing.md` — they still show the
stale cached registry, e.g. blank/`RADIOBRIDGE`, not the live `NEZHA2
robot` identity). `mbdeploy deploy vevov --hex
.../deploy-head/built/binary.hex`:
- Invocation 1: hit `SWD/JTAG communication failure (Unexpected ACK
  '0')` on the initial erase; mbdeploy's own CTRL-AP mass-erase
  recovery ran automatically; the retry hit the **same** SWD/JTAG
  failure again. This invocation failed outright (not the documented
  "normally succeeds" case).
- Re-probed: vevov still `CONN=yes` on the same port, so retried with a
  fresh invocation rather than treating this as a hard failure per the
  debugging protocol (gather evidence before concluding).
- Invocation 2: initial erase again hit `SWD/JTAG communication
  failure`; automatic CTRL-AP mass-erase recovery ran; the retry
  **succeeded**: `Erased 398336 bytes (98 sectors), programmed 398336
  bytes (98 pages), identical 0 bytes (0 pages)`.

**tovez.** Re-probed immediately before flashing (same three boards,
same ports as above, all `CONN=yes`). `mbdeploy deploy tovez --hex
.../deploy-head/built/binary.hex`: single invocation, hit the
documented `flash erase sector failure (address 0x00000000, result
code 0x67)` on the initial erase; automatic CTRL-AP mass-erase recovery
ran; the retry succeeded within the same invocation: `Erased 398336
bytes (98 sectors), programmed 398336 bytes (98 pages), identical 0
bytes (0 pages)`. This matches the ticket brief's "normal" pattern
exactly.

### 3. Wire-protocol verification (the acceptance test)

All reads below were taken with `tools/robotlink.open_link()`, one
serial/radio session per board/transport (HELLO unsequenced, ID
sequenced via `#<id>` per `.claude/rules/playfield-testing.md`).

**vevov, over USB (`/dev/cu.usbmodem2121102`):**
```
HELLO -> device NEZHA2 robot vevov 1198504156
ID    -> id diffdrive vevov 1.0.10 vevov
```

**vevov, over the zavaz relay (radio, channel 4)** — repeated for
belt-and-suspenders coverage, not required since USB already suffices:
```
HELLO -> device NEZHA2 robot vevov 1198504156
ID    -> id diffdrive vevov 1.0.10 vevov
```
Identical over both transports.

**tovez, over USB (`/dev/cu.usbmodem2121202`)** — radio not attempted;
getez is not connected, per the ticket brief:
```
HELLO -> device NEZHA2 robot tovez 2314287040
ID    -> id diffdrive tovez 1.0.10 tovez
```

**Agreement check:**
- vevov: `ID` field 3 (`vevov`) == `HELLO`'s name field (`vevov`). MATCH.
- tovez: `ID` field 3 (`tovez`) == `HELLO`'s name field (`tovez`). MATCH.
- vevov's `ID` name field (`vevov`) != tovez's (`tovez`) — confirms this
  is not two boards coincidentally sharing one stale constant.
- Fields 0-2 (`diffdrive` / profile / `1.0.10`) are byte-identical in
  shape to the pre-existing 3-field reply on both boards; profile now
  also correctly reads each board's own name (`vevov`/`tovez` — no
  longer the pre-ticket cross-wired `tovez` on vevov). Per ticket 002's
  own documentation this profile/name agreement is expected and
  correct here, not something to "fix" — a profile/name *mismatch*
  would mean the board was flashed with the wrong robot's build, which
  did not occur.

### 4. Gates (foreground)

- `uv run pytest` — **738 passed** (baseline 718 before this sprint;
  tickets 001 and 002 together added 20 tests, matching expectations).
- `uvx ruff check tools tests` — All checks passed!
- `node_modules/.bin/tsc --noEmit -p tsconfig.json` — clean, no output.
- `clasi design validate` — `Design doc set valid.` (three informational
  `docs/design/{overview,specification,usecases}.md` notices, not
  failures — pre-existing, unrelated to this ticket).

No source, test, or documentation files were modified by this ticket —
it is a verification-only build/flash/wire-protocol checkpoint. Only
this ticket file itself carries new content.
