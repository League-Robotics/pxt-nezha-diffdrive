---
id: '002'
title: ID verb reports the machine name, not the baked profile constant
status: open
use-cases: [SUC-001]
depends-on: []
github-issue: ''
issue: id-verb-reports-a-baked-constant-not-the-machine-name.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# ID verb reports the machine name, not the baked profile constant

## Description

`WireHandler::execId` (`src/comms/wire_handler.cpp:704-712`) replies
`id <drivetrain> <profile> <version>`, using `identity.drivetrain`,
`identity.profile`, and `identity.version` — never `identity.name`, even
though `Protocol::buildIdentity()` (`src/comms/protocol.cpp:203-211`)
already populates `identity.name` from `microbit_friendly_name()`, the
real per-board name burned into the chip. `identity.name` already
reaches the wire once, via `sendBanner()`'s `HELLO` reply
(`wire_handler.cpp:1177-1184`, `device NEZHA2 robot %s %s\n`) — this
ticket adds a second read site for a value that already exists, not a
new data path.

Eric's direction (binding, see
`clasi/issues/id-verb-reports-a-baked-constant-not-the-machine-name.md`):
`ID` must report the machine name read from the chip. Baking a value
per-robot at deploy time was explicitly rejected as an identity source —
it re-introduces "a baked value is only as correct as the build that
produced it." Note a same-day, out-of-process commit (`90183f8`, "Bake
kProfile per-robot at deploy time") already did exactly the
rejected-for-identity thing to `kProfile`/`profile` — that commit is not
reverted by this ticket (see `sprint.md`'s Design Rationale: `profile`
is kept, but redocumented as build-target selection, not identity).

**Wire format**: append `identity.name` as a **fourth** field:
`id <drivetrain> <profile> <version> <name>`. Do not reorder or replace
existing fields — `id <drivetrain> <profile> <version>` is pinned
outside this repo in `radio-robot-lib/docs/design/protocol.md:518`,
`radio-robot-lib/tests/protocol/golden_vectors.txt:89`, and
`radio-robot-lib/src/protocol/protocol_handler.cpp:623`. None of those
three files are touched by this ticket (different repo, out of this
sprint's scope) — see `sprint.md`'s Migration Concerns for the tracked
follow-up.

**Also in scope**: `protocol.cpp`'s doc comment for `kProfile`
(currently describes it as "the robot's own fleet identity") is
corrected to describe deploy-time build-target selection instead —
`identity.name`, not `identity.profile`, is what this sprint treats as
authoritative board identity. No behavior change to `_inject_profile()`
or `tools/make_deploy.py --robot` itself.

## Acceptance Criteria

- [ ] `ID`'s wire reply is `id <drivetrain> <profile> <version> <name>`
      — a strict 4-field append, fields 0-2 byte-identical to today's
      3-field reply.
- [ ] `<name>` is `identity.name`, sourced from
      `Protocol::buildIdentity()`'s existing
      `identity.name = microbit_friendly_name();` — no new identity
      plumbing.
- [ ] `execId`'s `snprintf` buffer (`buf[96]`) is confirmed to have
      headroom for the added field (a micro:bit friendly name is a
      handful of characters; the existing 96-byte buffer already holds
      three fields plus the "id " prefix and trailing newline) — bump
      the buffer size if the implementer's check shows otherwise.
- [ ] `protocol.cpp`'s `kProfile` doc comment (added by commit `90183f8`,
      currently describing `profile` as "the robot's own fleet
      identity") is corrected to describe build-target selection, not
      identity.
- [ ] `tests/host/test_wire_grammar.py::test_id_golden_vector` is
      updated to expect the 4-field reply (currently asserts
      `id diffdrive nezha2 6.0.0\n` after `wg.set_identity(b"testbot",
      b"SN001", b"diffdrive", b"nezha2", b"6.0.0")` — becomes
      `id diffdrive nezha2 6.0.0 testbot\n`).
- [ ] No other golden-vector or grammar test regresses (`VER`, `HELLO`,
      `STATUS`, etc. are untouched by this ticket).

## Implementation Plan

**Approach**: Minimal, surgical change to `execId`'s `snprintf` call —
add `%s` and `identity.name` to the existing format string and argument
list. Pair it with the doc-comment correction in `protocol.cpp` so the
code's own explanation of `profile` doesn't contradict this sprint's
stated design (identity comes from `name`, not `profile`).

**Files to modify**:
- `src/comms/wire_handler.cpp` — `execId` (around line 704-712): extend
  the `snprintf` format string and argument list to include
  `identity.name` as a fourth field.
- `src/comms/protocol.cpp` — the `kProfile` doc comment (lines ~24-58,
  written by commit `90183f8`): correct "the robot's own fleet
  identity" framing to describe build-target/deploy-provenance
  selection, and note that `identity.name` (not `identity.profile`) is
  what `ID` now treats as authoritative board identity.
- `src/comms/wire_handler.h` — `struct Identity`'s comment (lines
  95-107) mentions "which ID/VER read alongside HELLO's own banner
  fields"; confirm/update it to reflect that `ID` now reads `name` too.
- `tests/host/test_wire_grammar.py` — update `test_id_golden_vector`
  (around line 822-826) for the new 4-field reply.

**Files to create**: None.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/
  test_wire_grammar.py` (scoped to the wire-grammar host suite this
  ticket touches).
- **New tests to write**: No new test file needed — extend the existing
  `test_id_golden_vector` assertion to the 4-field shape. Consider
  adding a second case with a different `name` value (distinct from
  `profile`) to make the "these are independent fields that can
  legitimately differ" property explicit in the test, not just implicit
  in the format string.
- **Verification command**: `uv run pytest tests/host/` and
  `node_modules/.bin/tsc --noEmit -p tsconfig.json` (host tests are the
  only trustworthy check here — no hardware needed for this ticket; see
  ticket 003 for the hardware acceptance test).
