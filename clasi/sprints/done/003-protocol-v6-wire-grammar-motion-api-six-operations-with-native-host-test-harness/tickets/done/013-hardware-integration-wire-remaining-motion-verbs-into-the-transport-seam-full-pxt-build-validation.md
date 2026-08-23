---
id: '013'
title: 'Hardware integration: wire remaining motion verbs into the transport seam,
  full PXT build validation'
status: done
use-cases:
- SUC-001
- SUC-004
depends-on:
- '005'
- 008
- 009
- '011'
- '012'
github-issue: ''
issue:
- implement-protocol-v6-wire-grammar-and-reliability.md
- implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware integration: wire remaining motion verbs into the transport seam, full PXT build validation

## Description

This sprint's final, integrating ticket. By this point, `WireHandler`/
`WireAdapter`/`MotionEngine` are fully built and host-tested (tickets
002-012); ticket 005 already put the transport seam (`protocol.cpp`)
onto the new wire path for the non-motion verbs. This ticket: (1)
confirms the transport seam requires no further change now that
`WireAdapter`'s six motion verbs are all real (ticket 005's
composition already reaches whatever `WireAdapter` methods exist — if
it needs any adjustment, make it here); (2) validates the FULL PXT
build compiles clean with every new/modified file correctly listed in
`pxt.json`; (3) confirms `test/test.ts` and `test/testrig.ts` are
unmodified and still exercise the same block API surface; (4) confirms
no PXT build trap was triggered (no `//%` shim with 5+ `int32`
params; every `//%` marker sits immediately above its signature with no
intervening comment; no file contains the word "radio" followed by a
period, even in a comment); and (5) signs off on the block-API
preservation decision recorded in sprint.md's Design Rationale — no
block added, removed, or renamed in `main.ts`.

## Acceptance Criteria

- [x] The PXT extension build (whatever local build/compile check this
      repo uses for `pxt.json`'s `microbit` target) completes with no
      errors and no warnings about a missing/unlisted source file.
      Verified via `uv run python tools/make_deploy.py`, four
      independent runs across this ticket (two before the doc-comment
      edits below, two after): every run either produced a valid
      Intel-HEX (28,900+ line, ~1.3 MB) or hit the documented
      nondeterministic V1 `TS9283`/`srec_cat` packaging abort or a
      one-off remote-compile `TS9043` network hiccup, both resolved by
      re-running per `make_deploy.py`'s own module docstring. No run
      ever failed for a source-level reason. All six new/changed
      `.cpp`/`.h` files (`wire_handler`, `wire_adapter`, `motion_engine`,
      `protocol`, `shims`, `otos_port`) compiled and linked; no
      compiler warning traced to a file touched this sprint (the two
      warnings seen — `serial.cpp` unused-function, `music.cpp`
      missing-return — are pxt-core/CODAL files untouched by this
      sprint, and the one sprint-adjacent warning, `nezha_port.cpp`
      signed/unsigned compare, is in a file this sprint did not modify
      either).
- [x] Every file this sprint added or modified under `src/` is present
      in `pxt.json`'s `files` array (`wire_handler.{h,cpp}`,
      `wire_adapter.{h,cpp}`, `motion_engine.{h,cpp}`, plus the already
      -listed, modified `protocol.{h,cpp}`, `shims.cpp`, `otos_port.h`).
      Confirmed by direct inspection — all seven were already listed;
      no `pxt.json` edit was needed.
- [x] `main.ts`'s exported block set is byte-for-byte identical to the
      set that existed before this sprint (diff the exported function
      list, do not eyeball it) — confirms sprint.md's "additive wire
      verbs, unchanged block API" decision held.
      `git diff master...HEAD -- src/main.ts` is empty — `main.ts` was
      not touched by any ticket this sprint, so its 51
      `export function` blocks are trivially identical.
- [x] `test/test.ts` and `test/testrig.ts` are unmodified (or, if
      touched only for an unrelated reason, that reason is documented
      here — the expectation is zero changes).
      `git diff master...HEAD -- test/test.ts test/testrig.ts` is
      empty. Both still speak the old cleartext `RUN:`/`OCAL:`/`TOUR:`
      MessageBus bridge, which `protocol.h`'s file comment confirms is
      deliberately preserved unchanged alongside the new v6 wire stack.
- [x] No `//%` shim signature in the diff has 5 or more `int32`
      parameters. Scripted scan of every `//%`-marked signature in
      `src/main.ts` and `src/shims.cpp` (the only two files in this
      repo that carry `//%` shims); none has 5+ `int32`/`number`
      parameters. `src/protocol.cpp`'s one `//%` marker
      (`startProtocol()`, 0 params) predates this sprint unchanged.
- [x] Every `//%` marker introduced or moved by this sprint sits
      immediately above its function signature with no comment between.
      Same scripted scan: zero markers in `src/shims.cpp` (the one file
      this sprint's diff touches that carries `//%` shims) have a
      comment between the marker (or its trailing run of consecutive
      `//%` lines) and the signature.
- [x] No file touched by this sprint contains the literal text "radio."
      (the word followed by a period) in a comment or string that would
      trigger PXT's dependency scanner.
      One literal match: `src/protocol.h`'s "...results have to come
      back over the radio." — pre-existing verbatim text carried
      unchanged through this sprint's rewrite of the file (present in
      `master`'s copy at the same wording; not introduced by this
      sprint). Confirmed harmless empirically: `.tmp/deploy-head/
      pxt.json` after every build run still lists only
      `{"core": "*", "microphone": "*"}` as dependencies — no `radio`
      package was auto-added, and every build produced a valid hex.
      Left unedited rather than churning a pre-existing, verified-safe
      line on the sprint's last ticket.
- [x] `uv run pytest` (the full host suite, every ticket's tests) is
      green. 220/220 passed, twice (before and after this ticket's
      doc-comment-only source edits).
- [x] Sprint.md's Success Criteria are each traceable to a passing test
      or an explicit, documented deferral (hardware validation). See
      Integration Findings below for the item-by-item trace, including
      two items (TLM telemetry projection, the settle-tick loop's host
      testability) that are explicit, documented deferrals rather than
      passing tests, and one (`STATUS` vs. the old `DIAG`'s numeric
      surface) that is a real, documented capability gap.

## Integration Findings

Findings from this ticket's assessment of the sprint's open items,
beyond the mechanical checks above. Nothing here required a code
*behavior* change; three doc-comment additions record the decisions
below at their point of relevance (`src/protocol.h`, `src/shims.cpp`,
`src/wire_adapter.cpp`).

1. **TLM `thdr`/`t` frames: genuinely absent, not implemented.**
   `wire_handler.h`'s `emitTelemetry()` sends only the reliability
   layer's own `ack`/`nack` keepalive — no data-bearing telemetry frame
   exists in this build. This was already documented in
   `wire_handler.h` as deferred future work; this ticket adds the
   missing cross-reference in `protocol.h` connecting it to host-tool
   impact: the OLD v5 loop's automatic cleartext
   `TLM:<ms>:<x>:<y>:<h>:<ox>:<oy>:<oh>:<vl>:<vr>` line is gone with no
   v6 replacement, so `tools/tour_run.py`'s `TLM:`-prefix branch (and
   `tour_capture.py`/`tour_watch.py`'s `DIAG:`-prefix branches, see
   item 4) will simply never fire on this firmware. Not a crash — the
   tools run to completion — but `tour_run.py`'s "wheel speed while
   moving" diagnostic line and its `_tlm.csv` output will be silently
   empty. **The stakeholder should know this before running any
   TLM-dependent bench tool tomorrow.**
2. **The settle-tick loop (`shims.cpp::tickDrive()`) is not
   host-testable, and stays that way.** Confirmed ticket 009's own
   finding: the up-to-12-iteration post-move settle loop lives only in
   `tickDrive()`, which includes `pxt.h` and cannot be host-compiled.
   Assessed moving it into `motion_engine.cpp` (host-portable) for this
   ticket and decided against it: the loop's own body
   (`kernel.step()`/`kernel.output()`) is portable, but its purpose is
   to fold coast counts into `odomUpdate()` — Rig-local `x`/`y`/heading
   state — before the final telemetry read, so a clean extraction would
   also require relocating odometry ownership into `motion_engine`
   (which sprint.md's own Step 5 gestures at but this sprint did not
   fully do). That is a real architectural change, not a mechanical
   one, and not appropriate to take on unreviewed on the sprint's last
   ticket. Documented in place (`shims.cpp`) rather than fixed;
   ticket 009's regression test continues to cover the loop's *shape*
   (bounded iteration, break-on-rest) against `motion_engine`'s
   portable kernel access, not `tickDrive()`'s own body.
3. **No encoder-odometry `PoseSource` fallback: confirmed intended end
   state.** `GO_TO_W` answers `Wire::Result::kUnimplemented` when no
   live OTOS is connected (ticket 012), matching `wire_adapter.h`'s own
   extensive documented rationale (protocol.md S6.1's "recognized, not
   wired on this build"). motion-api.md §3.6's encoder-odometry
   fallback remains explicitly out of scope (ticket 010's own
   Description). No action needed; already correctly documented in
   code.
4. **`DIAG` is dropped; `STATUS` covers its BOOLEAN surface but NOT its
   NUMERIC surface — a real, documented gap.** The v6 verb catalog has
   no `DIAG` verb at all (by sprint.md's own Scope). `STATUS`'s `flags`
   field reproduces the eight boolean `diagValue()` reads the old
   `DIAG` line also carried (ready/estopped/stall/lease/conn×2/wedge×2)
   — but the old `DIAG` line's NUMERIC bench-diagnosis fields (I2C
   fault counter, per-wheel position/duty/velocity, cycle count,
   saturation, deficit/overrun/error counters, line/verb dispatch
   counters — 15+ fields) have **no v6 wire-reachable equivalent at
   all**. `GET`/`SET`'s field table doesn't carry them either (it
   addresses tunable config, not live telemetry). Concretely: the
   wedged-I2C-bus bench workflow this ticket was asked to check `DIAG`
   against has no v6 replacement — a host can learn "something is
   wrong" from `STATUS.flags` but not "the I2C fault counter just
   jumped." Documented in `wire_adapter.cpp` above `status()`; adding a
   wire verb for it is out of this sprint's fixed catalog and is not
   this ticket's job, but the stakeholder should know the bench
   diagnosis workflow for this specific failure mode has no wire-level
   tool in this build.
5. **Block API preservation: confirmed clean, trivially.** `main.ts`
   has zero diff against `master` for the entire sprint — see AC 3
   above.
6. **`pxt.json`: confirmed complete.** All seven touched/added source
   files were already listed; no edit needed.
7. **Old (v5) protocol: confirmed genuinely retired.** No `COBS`,
   `CRC16`, or old binary verb name (`MOVE`, `WHEELS`, `CONFIG`,
   `SET_FIELD`, `GET_CONFIG`, `CALIBRATE`, `CFG`) string remains
   anywhere under `src/`. `protocol.h`'s file comment documents exactly
   what was deleted and what was deliberately kept (the old cleartext
   `RUN:` MessageBus bridge, for `test.ts`'s own bench tooling — see AC
   4). `tools/*.py` still speak v5/old-cleartext by design — out of
   this sprint's scope per sprint.md's own Open Question 1, unaffected
   by this ticket.
8. **Documentation (`README.md`/`docs/design/specification.md`):
   confirmed nothing to update.** Neither file describes the wire/
   serial protocol at all, old or new (checked for `HELLO`, `PING`,
   `TLM`, `DIAG`, `MOVE`/`WHEELS`/`CONFIG` verb-set references — zero
   hits in either file). The only "protocol" section in
   `specification.md` (§7.1) is the Nezha brick's I2C bus protocol, an
   unrelated hardware layer. No edit made.

## Implementation Plan

**Approach**: This is primarily a verification/integration ticket, not
new feature work — the expectation is that tickets 001-012 already did
the real work correctly and this ticket confirms it, fixing only
small, mechanical integration gaps (a missing `pxt.json` entry, a
transport-seam call site that needs updating now that all six verbs
are real) rather than adding new behavior.

**Files to modify**: `pxt.json` (if any entry is missing),
`src/protocol.{h,cpp}` (only if ticket 005's composition needs a small
adjustment now that `WireAdapter` has no remaining stub methods — not
expected to be substantial).

**Files to create**: none expected.

**Testing plan**: Run the full host suite (`uv run pytest`) and the
PXT build check; manually enumerate `main.ts`'s exported functions
before and after this sprint's branch to confirm the block-API-parity
criterion (e.g. `git diff master -- src/main.ts` reviewed for any
`export function` line added/removed/renamed).

**Documentation updates**: Update `README.md`/`docs/design/
specification.md` if either still describes the retired v5 wire format
(confirm and update references to the old `MOVE`/`WHEELS`/binary verb
set to the new v6 catalog) — flagged here rather than assumed, since
`specification.md` is this project's authoritative reference and must
not be left describing a retired protocol.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/` (every ticket
  in this sprint).
- **New tests to write**: none expected beyond what tickets 001-012
  already wrote; this ticket's job is validation, not new coverage.
- **Verification command**: `uv run pytest` (full suite) plus the PXT
  build check.
