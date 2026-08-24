---
id: '005'
title: 'Phase C bench checkpoint: flashable hex and stakeholder handoff notes'
status: open
use-cases:
- SUC-006
depends-on:
- '002'
- '004'
- '006'
github-issue: ''
issue: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
completes_issue: true
exception:
  thrown_by: programmer
  thrown_at: '2026-08-24T05:55:09.368540+00:00'
  attempted: 'Ran `uv run pytest tests/host` first (253 passed, matching baseline),
    then `uv run python tools/make_deploy.py`. The build failed -- but NOT with the
    documented nondeterministic V1 `TS9283 program too big` packaging abort this ticket''s
    AC anticipates and says to retry once. Instead, the cloud compile (makecode.com/compile)
    produced a hard, deterministic C++ compile error in BOTH build variants it runs
    in parallel (the legacy mbed-classic/yotta `bbc-microbit-classic-gcc` target AND
    the codal-microbit-v2 target), at every single `columns_[i++] = {...}` line inside
    `WireAdapter::buildSnapshot()` (`src/wire_adapter.cpp:539-579`, ~20 identical
    errors per build): "error: no match for ''operator='' (operand types are ''Wire::Column''
    and ''<brace-enclosed initializer list>'')", with GCC''s own notes showing the
    only two candidates are Column''s implicit copy-assignment and move-assignment
    operators, neither of which accepts a braced-init-list. Root cause confirmed by
    inspection: `Wire::Column` (`src/wire_handler.h:157-161`, added by ticket 004)
    has default member initializers (`const char* name = ""; int32_t value = 0; bool
    hex = false;`), which under strict C++11 (the standard both real embedded toolchains
    compile with -- `-std=c++11` is baked into the pxt-microbit target''s own yotta/CMake
    toolchain files, not overridable from this project''s pxt.json) disqualifies a
    class from being an aggregate. That makes `{"seq", ..., false}` neither valid
    aggregate-initialization nor constructible via any declared constructor, so the
    assignment has no way to build the temporary it needs. The host test toolchain
    evidently compiles with a newer effective standard (C++14+ restored this aggregate
    rule), which is why 253 host tests already pass against this exact code and never
    caught it. Ruled out staleness/sync bugs before concluding this is real: `diff
    src/wire_handler.h .tmp/deploy-head/src/wire_handler.h` and the same for `wire_adapter.cpp`
    are byte-identical to the committed, ticket-004-approved source, and `git status`
    shows no local modifications to either file. Did not re-run a second time hoping
    for a different result: this is a deterministic type-system error, not the documented
    flaky packaging abort, and it reproduced identically across both parallel build
    variants at every column line -- a second cloud round-trip would not change a
    type error inherent in the committed code. Separately (read-only, not blocked):
    confirmed via the same build log''s own `-Woverflow` warning on `src/serial_transport.cpp:47-48`
    ("large integer implicitly truncated to unsigned type") plus the real codal-core
    header (`inc/driver-models/Serial.h`, fetched via `gh api repos/lancaster-university/codal-core/contents/...`)
    that `setRxBufferSize`/`setTxBufferSize` take `uint8_t size` -- confirming ticket
    006''s flagged-but-unconfirmed concern: `kRingBytes` (480) silently truncates
    to 224, below `kMaxLineBytes` (240). That finding is documented in this ticket''s
    notes as a known defect for bench verification, per this ticket''s own instructions
    not to fix it here.'
  conflict: 'Ticket 005''s own Description and Implementation Plan explicitly bar
    any change to `src/` in this ticket ("This is a BUILD checkpoint, not a hardware
    one... this ticket is a checkpoint/handoff, not an implementation ticket -- no
    new production code"; "Files to modify: none under `src/` or `tests/`"), while
    Acceptance Criterion #2 requires `uv run python tools/make_deploy.py` to produce
    a flashable hex. Both cannot be satisfied simultaneously: the only fix for the
    compile error is a source change to `Wire::Column` (`src/wire_handler.h:157-161`)
    and/or the column-assignment lines in `WireAdapter::buildSnapshot()` (`src/wire_adapter.cpp:539-579`)
    -- e.g. giving `Column` an explicit 3-arg constructor, or replacing brace-assignment
    with field-by-field assignment. That code is ticket 004''s already-closed, already-reviewed
    implementation (`004-wireadapter-telemetry-projection-buildsnapshot-shared-computeflags-pose-full-columns-status-i2cf.md`,
    status: done, six scale tests + golden-frame test all passing on the host toolchain)
    -- reopening and editing it is outside ticket 005''s assigned scope and its explicit
    no-src/-changes constraint. No flashable hex can currently be produced by this
    project''s existing deploy tooling at all, on either real build target, until
    that fix lands somewhere.'
  surface: internal
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
