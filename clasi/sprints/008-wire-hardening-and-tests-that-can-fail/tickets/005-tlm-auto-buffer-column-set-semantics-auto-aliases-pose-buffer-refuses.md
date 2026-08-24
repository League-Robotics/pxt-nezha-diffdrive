---
id: '005'
title: 'TLM AUTO/BUFFER column-set semantics: AUTO aliases POSE, BUFFER refuses'
status: open
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

- [ ] `TLM AUTO #<id>` accepts and behaves identically to
      `TLM POSE #<id>` — same 12-column set, same cadence; a host test
      asserts the emitted `thdr` is byte-identical between the two
      modes.
- [ ] `TLM BUFFER #<id>` is refused — `err 6 #<id>` (`kUnimplemented`)
      — at the point `mode_` would be assigned, before any telemetry
      frame is built for it. `mode_` is left unchanged (still whatever
      it was before the refused `TLM BUFFER` request), matching this
      project's existing "merits rejections don't change state" wire
      convention.
- [ ] A host test confirms `TLM BUFFER` never emits a `thdr`/`t` frame
      after being refused.
- [ ] `TLM POSE`/`TLM FULL`/`TLM OFF` behavior is unchanged — no
      regression to `test_wire_telemetry_frame.py`/
      `test_wire_telemetry_projection.py`.
- [ ] `wire_adapter.h`'s `buildSnapshot()`/`TlmMode` doc comment states
      the decision (AUTO = POSE alias; BUFFER = unimplemented) instead
      of describing the fall-through as unspecified.
- [ ] Grep `tools/` for any script sending a literal `TLM BUFFER` today
      (cheap due diligence, not exhaustive) — none is expected, but
      confirm and note the result in this ticket's own notes, same
      caveat sprint 007's `default_cruise` fix carried for `cruise 0`.

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
