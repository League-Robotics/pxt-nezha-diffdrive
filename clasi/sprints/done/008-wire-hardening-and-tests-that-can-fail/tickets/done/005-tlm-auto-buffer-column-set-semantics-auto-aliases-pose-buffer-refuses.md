---
id: '005'
title: 'TLM AUTO/BUFFER column-set semantics: AUTO aliases POSE, BUFFER refuses'
status: done
use-cases:
- SUC-005
depends-on: []
github-issue: ''
issue: tlm-auto-buffer-column-set-undefined.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# TLM AUTO/BUFFER column-set semantics: AUTO aliases POSE, BUFFER refuses

## Description

`WireAdapter::buildSnapshot()` (`wire_adapter.cpp:595`) special-cases
`mode_ == Wire::TlmMode::kFull` (20 columns) and otherwise emits POSE's
12 columns for every other non-off mode — including `kAuto` and
`kBuffer`, which silently fall through to POSE's set with no decision
ever recorded anywhere (found by sprint 004 ticket 004's implementer
while reading the spec for an answer that was not there —
`tlm-auto-buffer-column-set-undefined.md`, Low priority, not a code
review finding).

## Design Rationale

See `design/DESIGN.md` §5/§14 in this sprint's overlay for the full
entry. Summary: `AUTO` becomes a **documented alias for `POSE`** —
matches today's actual de facto behavior exactly, so this is a
zero-risk documentation-and-test fix, not a feature; a real "robot
chooses its own cadence" AUTO is a genuine design surface this
Low-priority housekeeping issue does not warrant opening. `BUFFER`
becomes an explicit **`kUnimplemented` refusal** at the `TLM` verb
itself (in whatever handler sets `mode_`, before the assignment) rather
than a narrower column set invented with no consumer or transport
mechanism to validate it against — no buffering mechanism exists
anywhere in this codebase today, so refusing is honest; the issue's own
stated preference is "answering err is better than emitting a column
set no one specified."

## Acceptance Criteria

- [x] `TLM AUTO #<id>` accepts and behaves identically to
      `TLM POSE #<id>` — same 12-column set, same cadence; a host test
      asserts the emitted `thdr` is byte-identical between the two
      modes.
- [x] `TLM BUFFER #<id>` is refused — `err 6 #<id>` (`kUnimplemented`)
      — at the point `mode_` would be assigned, before any telemetry
      frame is built for it. `mode_` is left unchanged (still whatever
      it was before the refused `TLM BUFFER` request), matching this
      project's existing "merits rejections don't change state" wire
      convention.
- [x] A host test confirms `TLM BUFFER` never emits a `thdr`/`t` frame
      after being refused.
- [x] `TLM POSE`/`TLM FULL`/`TLM OFF` behavior is unchanged — no
      regression to `test_wire_telemetry_frame.py`/
      `test_wire_telemetry_projection.py`.
- [x] `wire_adapter.h`'s `buildSnapshot()`/`TlmMode` doc comment states
      the decision (AUTO = POSE alias; BUFFER = unimplemented) instead
      of describing the fall-through as unspecified.
- [x] Grep `tools/` for any script sending a literal `TLM BUFFER` today
      (cheap due diligence, not exhaustive) — none is expected, but
      confirm and note the result in this ticket's own notes, same
      caveat sprint 007's `default_cruise` fix carried for `cruise 0`.

## Implementation Notes

- `src/wire_adapter.cpp`'s `onTlm()` now refuses `TlmMode::kBuffer`
  (returns `Wire::Result::kUnimplemented`) BEFORE the `mode_ = mode`
  assignment; `kAuto` falls through to that same assignment exactly
  like every other real mode, so `mode_` can hold `kAuto` and
  `buildSnapshot()`'s existing `mode_ == kFull` branch already treats
  every other stored mode (`kOff`/`kPose`/`kAuto`) identically — no new
  branch was needed there for the alias to work.
- `src/wire_handler.cpp`'s `execTlm()` previously **hardcoded**
  `errCode = 0` and discarded `adapter_.onTlm(mode)`'s return value
  entirely — this is *why* the fall-through was invisible even to a
  host asking for something already wrong: no `TlmMode`, mocked or
  real, could ever have produced an `err` line for TLM before this
  ticket, regardless of what any `Adapter::onTlm()` implementation
  returned. Fixed to read `errCode = resultCode(adapter_.onTlm(mode))`,
  the same "ack unconditionally, then err on top of a merits refusal"
  shape every other verb in this dispatcher already follows. This
  mirrors ticket 001's own precedent exactly: a semantic refusal is a
  MERITS rejection (ack + err), not a decode failure (nack) —
  `decodeTlm()`/`parseTlmMode()` already accept the `BUFFER` token as
  well-formed; only the accepted line's *meaning* is refused.
- `tools/` grep: no script anywhere in `tools/` sends a literal wire
  `TLM AUTO` or `TLM BUFFER` command (`grep -rn "TLM BUFFER\|TLM
  AUTO\|TlmMode::kBuffer\|TlmMode::kAuto" tools/` — no hits). Every
  `TLM` occurrence found in `tools/*.py` is a `startswith('TLM:')`
  match against an unrelated, older PXT-block-layer log-line prefix,
  not this protocol's `TLM` verb or its `thdr`/`t` frame — so there is
  no existing host anywhere in-tree that could be relying on the old
  undocumented fall-through.
- Red/green proof (this sprint's own convention, ticket 003): stashed
  the three production edits (`wire_adapter.cpp`, `wire_adapter.h`,
  `wire_handler.cpp`), reran the new BUFFER-specific tests — 4 failed
  red (`test_tlm_buffer_refused_via_direct_on_tlm`,
  `..._leaves_a_prior_mode_untouched`, `..._acks_then_err_6`,
  `..._never_emits_a_thdr_or_t_frame`) — then restored and confirmed
  green. The two AUTO tests pass in BOTH states by design: AUTO already
  behaved as POSE's de facto alias before this ticket (the Design
  Rationale's own "zero-risk, matches existing behavior" point) — they
  pin a decision, not a behavior change, so they were never expected to
  discriminate.
- No `WaHandle` test-double resync needed (unlike ticket 003): `TLM`'s
  dispatch and mode logic lives entirely in `wire_adapter.cpp`/
  `wire_handler.cpp`, which are the REAL production sources, compiled
  directly into the host test shared library (`_SHIM_SOURCES` in
  `tests/host/test_wire_motion_verbs.py`) — there is no separate
  host-side reimplementation of this logic to drift out of sync with.
- Full `uv run pytest`: 411 passed (404 baseline + 7 new tests: 1 in
  `test_wire_grammar.py`, 6 in `test_wire_telemetry_projection.py`).

## C++11 Gate Coverage

- **Inside the gate**: `wire_adapter.h`/`.cpp` — already covered by
  `test_cxx11_syntax_gate.py`. This ticket's change is a small
  conditional in an already-gate-covered file.
- **Outside the gate**: none — this ticket touches no CODAL-bound file.
  A green host suite here is meaningful evidence for this ticket's own
  change (similar to ticket 001, unusual among this sprint's other
  tickets).

## Testing

- **Existing tests to run**: `tests/host/test_wire_telemetry_frame.py`,
  `tests/host/test_wire_telemetry_projection.py`,
  `tests/host/test_wire_grammar.py` — confirm no regression to POSE/
  FULL/OFF telemetry behavior or general TLM dispatch.
- **New tests to write**: `TLM AUTO` vs `TLM POSE` byte-identical
  `thdr` test; `TLM BUFFER` refusal test (asserts `err 6` and no
  frame emitted).
- **Verification command**: `uv run pytest tests/host/ -k "tlm or
  telemetry"` during development, then a full `uv run pytest` before
  marking this ticket done.
