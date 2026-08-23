---
id: '003'
title: 'Reliability layer: mandatory sequence id, cumulative ack/nack, decode-failure-is-NAK'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-005
depends-on:
- '002'
github-issue: ''
issue: implement-protocol-v6-wire-grammar-and-reliability.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Reliability layer: mandatory sequence id, cumulative ack/nack, decode-failure-is-NAK

## Description

Add protocol v6's reliability layer to `wire_handler`: the mandatory,
trailing, digits-only `#<n>` sequence id on every sequenced verb;
handler state limited to exactly `expectedNext_`/`gapOutstanding_` (no
clock, no timer — `feed()` stays a pure function of its input bytes
plus this state); the three-way classification of every inbound id
(`== expectedNext_` decode-then-ack, `< expectedNext_` re-ack the
already-accepted id WITHOUT re-executing, `> expectedNext_` discard and
nack); and decode-failure-is-NAK (an unknown verb, wrong arity, or an
unparseable field on an in-order id nacks that SAME id and does not
advance the sequence, distinct from a merits rejection which acks and
advances). Wire this reliability machinery against the non-motion
sequenced verb catalog — `ID`/`VER`/`STATUS`/`HELP`/`GET`/`SET`/`TLM`/
`STOP`/`RUN` — via a `MockAdapter`-style test double (recording calls,
canned return values), so the full reliability contract is exercised
without any motion verb or real kernel involved. `HELLO`/`ESTOP`/`PING`
(ticket 002) stay unsequenced, per the exemption set.

## Acceptance Criteria

- [x] Every sequenced verb requires a well-formed `#<n>` id; `#+5`,
      `#-5`, `# 5`, and a missing id are all malformed (no reply,
      `malformedCount()` increments) — a dedicated digits-only parser
      is used for the id, not the general signed-integer field parser.
- [x] The full three-way table is tested, INCLUDING an explicit
      assertion that the retransmit row (`id < expectedNext_`) does
      NOT re-invoke the mock adapter a second time.
- [x] A numeric gap (`id > expectedNext_`) does not increment
      `malformedCount()` (it is a normal, expected occurrence on a
      lossy/reordering transport, not a protocol violation).
- [x] Decode-failure-is-NAK is tested and distinguished from a merits
      rejection: a decode failure nacks the SAME id and does not
      advance; a merits rejection (mock adapter configured to refuse)
      acks, advances, and is paired with `err <code> #<id>`.
- [x] Gap stalling and self-healing are tested: once a gap opens, every
      subsequent well-formed command is nacked identically until the
      missing id arrives; a lost `nack` self-heals via the next
      telemetry-piggybacked reliability line (`emitTelemetry`
      equivalent) without any new timer.
- [x] `#0` is not specially handled anywhere in the code (it is simply
      always `< expectedNext_` since ids start at 1) — verified by a
      test, not just by absence of special-case code.
- [x] `err <code> #<id>` field order is `err <code> #<id>` (code
      first, id last) — not the other way around.
- [x] Golden wire vectors exist for `ID`/`VER`/`STATUS`/`HELP`/`GET`/
      `SET`/`TLM`/`STOP`/`RUN`, both directions, each including its
      `#<id>`.

## Implementation Plan

**Approach**: Add `expectedNext_`/`gapOutstanding_` and the
decode-then-dispatch ordering to `wire_handler`'s `dispatch()`. Each
sequenced verb gets a decode/execute pair (decode is pure — no adapter
call, no sink write — so `dispatch()` can decide ack-vs-nack before any
side effect runs), mirroring `protocol_handler.h`'s own DecodeFn/
ExecuteFn split. Introduce a small `WireMockAdapter` test double
(recording call counts and last-call arguments, canned `Result`
returns) — this is test scaffolding only, never linked into production
code, matching `mock_adapter.h`'s own scope note.

**Files to modify**: `src/wire_handler.h`/`.cpp` (add reliability state
+ the nine non-motion sequenced verbs' decode/execute pairs).

**Files to create**:
- `tests/host/wire_mock_adapter.h` — the recording test double.
- `tests/host/test_wire_reliability.py` — the three-way table,
  decode-failure-is-NAK, gap stalling/self-healing.
- Extend `tests/host/test_wire_grammar.py` (or a new
  `test_wire_verbs.py`) with golden vectors for the nine verbs.

**Testing plan**: Entirely new host tests; no PXT/hardware build
exercised.

**Documentation updates**: Extend `wire_handler.h`'s header comment
with the reliability contract summary (mirroring
`protocol_handler.h`'s own file-header documentation style), citing
`protocol.md` §8/§8.9 as the specification authority for each rule.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/ -k "kernel_harness or wire_grammar"`
- **New tests to write**: `tests/host/test_wire_reliability.py` plus
  golden-vector additions, per Acceptance Criteria above.
- **Verification command**: `uv run pytest tests/host/`
