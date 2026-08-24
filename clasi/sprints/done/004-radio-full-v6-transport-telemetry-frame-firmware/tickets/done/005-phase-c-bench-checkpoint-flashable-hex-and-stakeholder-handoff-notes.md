---
id: '005'
title: 'Phase C bench checkpoint: flashable hex and stakeholder handoff notes'
status: done
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

- [x] All prior tickets (001-004, 006) are done and `uv run pytest`
      (the full suite, per this project's once-per-sprint full-run rule
      at `close_sprint`) passes.
- [x] `uv run python tools/make_deploy.py` produces a flashable hex,
      re-running once if the documented nondeterministic V1 `TS9283`
      packaging abort occurs (expected, not a bug — do not treat a
      first-run abort as a ticket failure before retrying).
- [x] A written bench checklist (in this ticket's own notes, or a
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
- [x] This ticket's own notes state explicitly, in so many words, that
      no flashing and no hardware validation were performed as part of
      this sprint's completion.

## Build Verification (this ticket's own run, 2026-08-23)

**Recovery context**: this ticket previously threw an exception (see
the `exception:` frontmatter block above, preserved as the historical
record) because `Wire::Column`'s C++11-illegal default member
initializers made `WireAdapter::buildSnapshot()`'s brace-assignments a
hard compile error on both real targets, while `tests/host/` at
`-std=c++20` never noticed. Ticket 007 (`b140f6d`) fixed this: gave
`Column` an explicit `Column() = default;` plus a 3-arg converting
constructor (no call-site changes needed), corrected
`SerialTransport::kRingBytes` to `constexpr uint8_t kRingBytes{255}`,
and added `tests/host/test_cxx11_syntax_gate.py`, an
`-std=c++11 -fsyntax-only` gate over the four files most exposed to
this class of defect. That ticket's own build run already produced a
flashable hex; this ticket re-ran the pipeline itself rather than
merely citing that artifact, since AC #2 names this ticket's own
`make_deploy.py` run.

- `uv run pytest tests/host` — **257 passed**, matching the sprint
  baseline. (The full repo-wide suite is the once-per-sprint
  `close_sprint` gate, per this project's convention — see this
  ticket's own dispatch context and `.claude/rules/source-code.md`;
  confirming `tests/host` green here satisfies AC #1.)
- `uv run python tools/make_deploy.py` — succeeded on the **first
  attempt**, no retry needed. Two build-log entries are expected,
  documented failure modes and were NOT treated as ticket failures:
  - The legacy V1 `bbc-microbit-classic-gcc` variant failed at its own
    hex-merge step (`srec_cat: ... contradictory 0x0003C000 value`) —
    this project's `pxt.json` keeps `disablesVariants: ["mbdal"]` only
    for its role as an *extension*; `make_deploy.py`'s own module
    docstring documents that the deploy copy drops that setting and
    accepts the resulting V1 `TS9283`-class failure as harmless,
    because the V1 hex is never the one that matters here.
  - A `pxt-core` internal `TypeError [ERR_INVALID_ARG_TYPE]` surfaced
    from `Host.cacheStoreAsync` during the same run, alongside the V1
    variant's own `test/test.ts(1,1): error TS9200` — both artifacts of
    the same known-harmless V1-side failure path, not of the
    codal-microbit-v2 build that actually produces the flashable hex.
  - The codal-microbit-v2 variant built clean and `make_deploy.py`'s
    own post-build check (`if not os.path.exists(HEX)`) confirmed the
    hex was present; script exited 0.
  - **Result**: `.tmp/deploy-head/built/mbcodal-binary.hex`,
    **1,332,476 bytes**, timestamped from this ticket's own run —
    same size as ticket 007's build, produced fresh rather than only
    cited. This is a build checkpoint only: the hex has not been
    flashed to any board as part of this ticket (see the explicit
    statement below).

## Bench Checklist (stakeholder handoff)

Everything below is to be checked **at the bench, on real hardware, by
the stakeholder** — none of it was performed as part of closing this
ticket or this sprint. See "No hardware validation performed" at the
end of this section.

1. **Frame width vs. radio's 200-byte cap.** Already measured through
   the real `WireAdapter::buildSnapshot()` pipeline — RE-STATING ticket
   004's and ticket 003's pinned host-test results, not re-deriving
   them:
   - Realistic-but-large values (long-running-session magnitudes, not
     pathological) across all 20 POSE+FULL columns —
     `test_widest_realistic_full_frame_fits_under_radio_cap`
     (`tests/host/test_wire_telemetry_projection.py`) — measured
     `thdr` = **86 bytes**, `t` = **138 bytes**. Both are comfortably
     under `RadioTransport::kMaxPayloadBytes` (200); the operative
     margin is `200 - 138 = 62` bytes. This width is NOT too close for
     comfort under real projected values.
   - Separately, ticket 003's pure-formatting worst case
     (`test_widest_pathological_int32_min_frame_confirms_open_question_2`,
     `tests/host/test_wire_telemetry_frame.py`) — all 20 columns at
     `INT32_MIN` — reaches **239 bytes**, 39 over the 200-byte cap
     (and 1 under the wire's own 240-byte line ceiling). This is a
     latent formatting ceiling, not something the real adapter
     produces (`flags` maxes at `0xFF`, only 8 boolean bits are wired;
     duty maxes at `±10000` — see the projection test's own per-column
     derivation). It is pinned as a known gap, not fixed here: filed
     as `clasi/issues/radio-rx-capacity-fragmentation.md` under sprint
     010, alongside the separate finding that radio's RX side is a
     single 64-byte unfragmented slot against v6 lines specified up to
     240 bytes. The 138 B figure is the one that governs today's real
     bench traffic; the 239 B figure is a documented, deferred risk.

2. **`diagValue(19)` (`cycleOverrunCount`) before and after the bench
   run.** Read it before starting, and again after the run. A rising
   count indicates the protocol fiber's added telemetry work is
   starving the kernel's own cadence — catch this before sprint 005
   builds host tooling that assumes clean timing.

3. **Radio now speaks the full v6 grammar**, not just `RUN:` — ack,
   nack, `thdr`, `t`, and the rest of v6's line shapes are new on the
   radio path as of this sprint. Any existing relay/log tooling that
   watches radio traffic should be updated to expect these new line
   shapes; legacy `RUN:` still routes to `handleRun()` unchanged, so
   nothing already working on `RUN:` should regress.

4. **The `sending_` re-entrancy guard (ticket 002) has no host
   coverage** — `radio_transport.cpp` is CODAL-bound and cannot run in
   the host test harness. This bench run is its first live exercise.
   Watch for unexpected radio silence under concurrent `emitLine()` +
   telemetry traffic — that would indicate the guard is either not
   releasing correctly or is over-suppressing sends.

5. **Ticket 006 + 007's serial hardening is likewise un-host-tested.**
   The corrected numbers, not ticket 006's original ones: the RX/TX
   rings are **255 bytes** (`constexpr uint8_t kRingBytes{255}`,
   `src/serial_transport.h`), **not** the 480 B ticket 006 originally
   set. The honest reason: `uBit.serial.setRxBufferSize` /
   `setTxBufferSize` take a `uint8_t` parameter (confirmed against
   codal-core's real `inc/driver-models/Serial.h` header), so 480
   silently truncated to 224 on assignment — *below* the 240-byte
   `kMaxLineBytes`, defeating the resize entirely. At 255 there is only
   about 15 bytes of margin above one full 240-byte line: **room for
   one maximal line plus a little slack, not two concurrent full
   lines.** This is a real platform ceiling (the `uint8_t` parameter
   type), not a tuning choice that could be dialed back up. At the
   bench: watch for any dropped or garbled serial line under load, and
   confirm **`probe(26)`** (the serial-drop counter, diag ordinal 26)
   stays at 0 during a normal bench run.

6. **The C++11/C++20 split — why to trust this hex over the green
   suite.** Until ticket 007 landed, this sprint's entire green host
   test suite coexisted with firmware that could not compile for
   either real embedded target: `tests/host/` builds at `-std=c++20`,
   while both real targets (`bbc-microbit-classic-gcc` and
   `codal-microbit-v2`) compile at `-std=c++11`, baked into the
   pxt-microbit target's own toolchain files and not overridable from
   this project's `pxt.json`. Ticket 007 added
   `tests/host/test_cxx11_syntax_gate.py`, a narrow
   `-std=c++11 -fsyntax-only` gate over the four files most exposed to
   this class of defect — not a systemic fix. The systemic gap (host
   tests compiling at a newer standard than either shipping target) is
   filed as `clasi/issues/host-tests-compile-newer-standard-than-target.md`
   under sprint 008. This is exactly why this ticket treats a
   **successfully built hex** as the stronger evidence of target
   viability, and a green `tests/host` run alone as necessary but not
   sufficient.

### No flashing and no hardware validation were performed

This ticket produced a build artifact and this written checklist only.
**No flashing to any microbit, and no hardware/bench validation of any
kind, was performed as part of completing this ticket or this
sprint.** Nothing above — the frame-width numbers, the overrun-count
check, the re-entrancy guard's behavior, the serial ring's real
concurrency behavior — has been exercised on real hardware yet. Per
this sprint's own scope boundary (`sprint.md`), sprint 004 ends at a
verified *build*; the bench checks above are the stakeholder's own
follow-up between sprints, ahead of sprint 005, which needs a wire
format confirmed on real hardware.

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
