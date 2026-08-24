---
id: '005'
title: 'Phase C bench checkpoint: flashable hex and stakeholder handoff notes'
status: open
use-cases: [SUC-006]
depends-on: ["002", "004", "006"]
github-issue: ''
issue: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Phase C bench checkpoint: flashable hex and stakeholder handoff notes

## Description

**This is a BUILD checkpoint, not a hardware one.** Per `sprint.md`'s
own stated scope boundary, this sprint ends at a verified build, not a
verified robot — Phase D (host tooling, sprint 005) needs a wire format
the stakeholder has confirmed on real hardware first, so this ticket
must NOT flash, must NOT capture live telemetry, and must NOT claim any
hardware validation as part of this sprint's completion. The instinct
to "just try it on hardware" once a hex exists should be resisted here;
that is explicitly the stakeholder's own follow-up between sprints.

Produce a flashable hex via this project's existing deploy tooling, and
write up exactly what the stakeholder should check at the bench —
without performing those checks in this ticket.

## Acceptance Criteria

- [ ] All prior tickets (001-004, 006) are done and `uv run pytest`
      (the full suite, per this project's once-per-sprint full-run rule
      at `close_sprint`) passes.
- [ ] `uv run python tools/make_deploy.py` produces a flashable hex,
      re-running once if the documented nondeterministic V1 `TS9283`
      packaging abort occurs (expected, not a bug — do not treat a
      first-run abort as a ticket failure before retrying).
- [ ] A written bench checklist (in this ticket's own notes, or a
      short handoff doc — implementer's choice of location) tells the
      stakeholder, explicitly, to check at the bench:
      - Ticket 004's host test already confirmed the widest `FULL`
        column set's formatted byte length against `RadioTransport`'s
        200-byte silent-truncation cap — this checklist item
        RE-STATES that test's result (pass/fail and the actual byte
        count found) for the stakeholder, rather than re-deriving it;
        if that test found the width too close for comfort under real
        radio conditions (packet loss, fragmentation), say so here.
      - `diagValue(19)` (`cycleOverrunCount`) before and after the bench
        run, as a tick-overrun sanity check — a rising count during a
        live run indicates the protocol fiber's own added telemetry
        work is starving the kernel's cadence, worth catching before
        sprint 005 builds tooling that assumes clean timing.
      - Radio now speaks the full v6 grammar (ack/nack/thdr/t/etc.),
        not just `RUN:` — any existing relay/log tooling watching radio
        traffic should expect these new line shapes.
      - The `sending_` re-entrancy guard (ticket 002) has no host test
        coverage — this is its first live exercise; watch for
        unexpected radio silence under concurrent `emitLine()` +
        telemetry traffic.
      - Ticket 006's serial hardening (RX ring raised to >= 480 B, a
        bounded-retry TX guard on `SerialTransport::writeLine()`) is
        likewise un-host-tested for its real concurrency/ring behavior
        — this is ITS first live exercise too. Watch for: any dropped
        or garbled serial line under load, and `probe(26)` (the new
        serial-drop counter) staying at 0 during a normal bench run.
- [ ] This ticket's own notes state explicitly, in so many words, that
      no flashing and no hardware validation were performed as part of
      this sprint's completion.

## Implementation Plan

**Approach**: Run the existing deploy pipeline; do not touch source.
This ticket is a checkpoint/handoff, not an implementation ticket — no
new production code, no new tests beyond confirming the full suite is
green.

**Files to modify**: none under `src/` or `tests/`. This ticket's own
file (recording the bench checklist) is the only artifact it produces,
unless the implementer chooses to also add a short `NOTES.md`-style
handoff file — team-lead's/implementer's call, not mandated.

**Testing plan**:
- Run the FULL suite once (`uv run pytest`), matching this project's
  once-per-sprint full-run convention (this is the sprint's own
  natural full-run point, immediately before `close_sprint`).
- Run `uv run python tools/make_deploy.py`, retrying once on the known
  nondeterministic abort.
- **Verification command**: `uv run pytest && uv run python tools/make_deploy.py`

**Documentation updates**: the bench checklist itself (see Acceptance
Criteria) is this ticket's primary output. No `docs/design/` changes
are needed — this sprint's scope is firmware-internal and does not
change the student-facing block API or specification.md.
