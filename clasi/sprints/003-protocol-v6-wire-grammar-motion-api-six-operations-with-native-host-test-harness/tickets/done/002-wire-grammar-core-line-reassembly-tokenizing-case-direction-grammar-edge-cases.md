---
id: '002'
title: 'Wire grammar core: line reassembly, tokenizing, case-direction, grammar edge
  cases'
status: done
use-cases:
- SUC-002
depends-on:
- '001'
github-issue: ''
issue: implement-protocol-v6-wire-grammar-and-reliability.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire grammar core: line reassembly, tokenizing, case-direction, grammar edge cases

## Description

Create `src/wire_handler.h`/`.cpp` — a new, host-portable module (no
`pxt.h`, no CODAL type, anywhere) implementing protocol v6's ASCII line
grammar mechanics only: `feed(data, length)` reassembling arbitrary
byte chunks into `'\n'`-terminated lines, tokenizing on runs of `' '`,
case-as-direction (a lowercase-led line is another robot's reply and is
dropped silently, not counted malformed), the 240-byte line cap
(overlong discarded to the next `\n`, counted malformed), a lone `'\r'`
stripped before `'\n'`, and a blank/all-whitespace line ignored
silently. This ticket deliberately does NOT implement the mandatory
`#<id>`/ack/nack reliability layer (ticket 003) or any sequenced verb
— it wires up `HELLO` (resets nothing yet, just proves dispatch),
`PING` (`pong <now>`), and `ESTOP` (the bare `estop` reply) as the
three verbs that will never need the reliability layer at all, so this
ticket's own tests can exercise the grammar in isolation. Modeled on
`radio-robot-lib/src/protocol/protocol_handler.{h,cpp}` §2-§3, §8.3 —
this project conforms to that grammar, it does not vendor that C++.

## Acceptance Criteria

- [x] `feed()` correctly handles: several complete lines in one block;
      a block ending mid-line (remainder buffered to the next `feed()`
      call); a block that is only a line fragment; a lone `'\r'`
      immediately before `'\n'`; a blank/all-whitespace line (ignored,
      not malformed); a line longer than 240 bytes (discarded to the
      next `'\n'`, counted malformed — never truncated into a
      still-parseable prefix).
- [x] Verb lookup is case-sensitive; a lowercase-led line is dropped
      silently and does NOT increment `malformedCount()`.
- [x] A run of spaces collapses to one separator; leading/trailing
      line whitespace is ignored.
- [x] `HELLO` replies the lowercase `device NEZHA2 robot <name>
      <serial>` banner; `PING` replies `pong <now>`; `ESTOP` always
      replies the bare word `estop` regardless of trailing junk on the
      line (`ESTOP`, `ESTOP 1 2 3`, `ESTOP #5` all execute and reply
      identically).
- [x] Golden wire vectors exist for all three verbs, both directions.
- [x] The adversarial input set from sprint.md's Test Strategy is
      exercised: overlong lines, embedded NULs, a lone `\r`,
      all-whitespace lines, partial lines split across `feed()` calls,
      a lowercase verb.
- [x] `src/wire_handler.{h,cpp}` are added to `pxt.json`'s `files`
      array (the PXT build-silent-exclusion trap flagged in
      sprint.md's Migration Concerns).

## Implementation Plan

**Approach**: Port the shape of `protocol_handler.h`'s `feed()`/
`tokenizeLine()`/dispatch skeleton, but write it fresh for this
project's own verb catalog and object model (no vendoring). A minimal
`Sink` interface (one `write(data, length)` method) decouples this
module from any real transport, matching the reference's own split.
Start with only `HELLO`/`PING`/`ESTOP` wired so this ticket's tests do
not depend on the reliability layer (ticket 003) or any Adapter beyond
a trivial stub providing `now()`/identity strings.

**Files to create**:
- `src/wire_handler.h` — `Sink`, `WireHandler` class declaration
  (`feed()`, `sendBanner()`-equivalent, `malformedCount()`).
- `src/wire_handler.cpp` — implementation.
- `tests/host/wire_grammar_shim.cpp` — `extern "C"` shim over
  `WireHandler` + a `RecordingSink` + a trivial stub adapter (`now()`,
  identity only — enough for `HELLO`/`PING`).
- `tests/host/test_wire_grammar.py` — golden vectors + adversarial set.

**Files to modify**: `pxt.json` (`files` array).

**Testing plan**: All new — this module has no prior test coverage
because it has no prior existence. Covered entirely by the new host
harness; no PXT/hardware build is exercised by this ticket.

**Documentation updates**: A short header comment in `wire_handler.h`
stating the grammar this module implements and citing
`radio-robot-lib/docs/design/protocol.md` §2 as the specification
authority, matching this project's existing convention of citing the
canonical doc rather than restating it.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/test_kernel_harness.py`
  (ticket 001's smoke test — confirms this ticket did not break it).
- **New tests to write**: `tests/host/test_wire_grammar.py` per
  Acceptance Criteria above.
- **Verification command**: `uv run pytest tests/host/ -k "kernel_harness or wire_grammar"`
