---
id: 008
title: Wire hardening and tests that can fail
status: ticketing
branch: sprint/008-wire-hardening-and-tests-that-can-fail
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
- SUC-005
- SUC-006
issues:
- wire-timeout-hardening.md
- wire-constants-single-source.md
- host-harness-double-drift.md
- settle-tick-loop-is-not-host-testable.md
- tlm-auto-buffer-column-set-undefined.md
- host-tests-compile-newer-standard-than-target.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 008: Wire hardening and tests that can fail

> **Arc position.** Fourth planned sprint out of the 2026-08-23 code review
> (`docs/code-review/2026-08-23/review.md`), after sprint 004 (radio/wire
> transport, currently in `ticketing`), sprint 005 (bench tooling, roadmap,
> blocked on 004's hardware checkpoint), sprint 006 (motion correctness,
> roadmap), and sprint 007 (student API, roadmap). It is placed after 006/007
> in sequence but has only one soft dependency on either: this sprint's
> settle-loop extraction
> (`settle-tick-loop-is-not-host-testable.md`) touches the same
> `shims.cpp::Rig::tickDrive()` neighborhood as sprint 006's stop-timing fix
> (`cross-fiber-stop-settle-window-race.md`, R-08) — both sprints
> read/modify code around the settle tick, and 006's own sprint.md already
> flags the one-ticker-per-move constraint this sprint must not violate.
> Running 006 first (or at minimum landing its settle-window fix before this
> sprint touches the same loop) avoids two independent rewrites of the same
> few lines. Sprint 007 has no code-path overlap with this sprint at all —
> it is sequenced after only because it was triaged before this one, not
> because it blocks anything here. This sprint's wire-layer scope
> (`wire_handler.*`, `wire_adapter.*`, `protocol.*`) also overlaps files
> sprint 004 is actively ticketing; if 004 lands first, this sprint's detail
> plan should re-check those files against 004's changes before ticketing.

## Goals

Theme: **mirrored constants can't drift silently, timeouts have edges, and
the host suite can actually catch the regressions it claims to.** Four
issues, none large enough alone to be its own sprint, share this thread —
every one of them is a place where the wire protocol or the test harness
can be silently wrong and nothing turns red:

- **Timeout edges** (`wire-timeout-hardening.md`, HIGH, R-06 + R-18):
  reject or clamp `timeout 0` at decode instead of letting the motion
  obligation die at `now+0` while a ~10 s kernel lease stays armed; define
  one meaning for 0 across all X verbs (`WHEELS_X` vs `MOVE_X` currently
  disagree); cap timeouts at decode (e.g. ≤ 2^31−1) so values above 2^31 ms
  stop wrapping the deadline arithmetic negative and killing an acked move
  at ~150 ms. Add the boundary values (0, 2^31−1, 2^31, uint32-max) to the
  existing host-test parametrize, which currently maxes at 5000 ms.
- **Constants single-sourced** (`wire-constants-single-source.md`, MED,
  R-17 + R-21): stop hand-mirroring `kVersion` against `pxt.json` (currently
  `1.0.0` vs `1.0.10` — ten bumps drifted) — generate it or drift-test it.
  Give `emitLine`'s line cap and the transports' `kMaxLineBytes` one shared
  constant instead of two (`200` vs `240`, silently truncating long bench
  result lines) and fix the radio transport's now-false "equals
  SerialTransport's cap" comment. Pin the smaller duplicated pairs (radio
  group `0x2001` in `main.ts` vs `protocol.cpp`; `kDiag*` ordinals
  re-declared across files) with drift tests of the same shape.
- **Harness doubles re-synced** (`host-harness-double-drift.md`, MED,
  R-25): fix the three confirmed drifts between the `WaHandle` test doubles
  and production — wedge field pairs (`wedgeLeft/Right` vs
  `wedgeSuspectLeft/Right`), `setWheelsTimed` skipping
  `MotionEngine::wheelsV()`'s `cancelMove()` call, and truncation vs
  `std::lround` in config rounding — then add a drift test that fails when
  either side changes alone, so "mirrors field-for-field" stops being a
  comment nobody checks.
- **Settle loop made host-testable** (`settle-tick-loop-is-not-host-testable.md`,
  pre-review, filed after sprint 003 ticket 009): extract the settle
  loop's logic (bounded iteration count, break-on-rest, never re-energize)
  out of `shims.cpp::Rig::tickDrive()` into a host-portable helper in
  `motion_engine`, leaving only CODAL platform glue behind the
  `pxt.h`/`shims.cpp` boundary. Preserve the one-fiber-ticks-a-move
  constraint — protocol co-ticking caused heisenbugs before. Grouped into
  this sprint because it is the same "tests must be able to fail" disease
  as the harness-double issue: a passing test suite currently proves
  nothing about whether this loop still exists.

## Problem

All four issues are places where the test suite — or the wire protocol
itself — cannot detect its own drift or its own edge cases:

- A `timeout 0` on `WHEELS_X` acks and appears to succeed while leaving a
  stale ~10 s kernel lease armed, and `MOVE_X`'s `timeout 0` means
  something different (instant no-op) — the same input means two things
  depending on verb. A timeout above 2^31 ms wraps the deadline arithmetic
  negative and re-triggers the ticket-011 starvation bug (an acked move
  dying at ~150 ms) for an input class no existing test reaches.
- `kVersion` has drifted ten version bumps from the value it claims to
  mirror, defeating the deploy-verification flow (`mbdeploy` → `VER`
  check) — the build a host thinks it's talking to may not be the build
  actually flashed. `emitLine`'s line cap silently truncates long bench
  result lines below what the transports can actually carry, and the
  comment claiming the radio transport's cap "equals SerialTransport's" is
  false since ticket 005 raised the serial cap alone.
- The `WaHandle` host-test doubles diverge from production in three
  load-bearing ways, and the comments asserting fidelity are worse than no
  comment — they tell the next reader not to check. Wedge state, command
  supersession via `cancelMove()`, and config rounding are all effectively
  untested as wired, because the double being exercised isn't the code
  that ships.
- The settle-tick loop that stages the kernel's neutral duty to the motors
  at move end lives entirely inside `shims.cpp`, which the host harness
  never links. A regression that deleted or shortened that loop — leaving
  the wheels coasting at full duty until the ~150 ms watchdog fires —
  would pass the entire host suite. The behavior is pinned by argument
  (sprint 003's regression test proves the *need* for the step), not by
  executing the actual loop.

## Solution

Per-issue, at the level of detail each issue file's "What to do" section
already states in full (read `clasi/issues/<file>` at detail-planning time
for the exact approach):

1. `wire-timeout-hardening.md` — reject/clamp timeout 0 and cap at 2^31−1
   at decode time in the wire layer, unify `WHEELS_X`/`MOVE_X` semantics
   for 0, ensure the kernel lease is capped/cleared alongside the
   obligation, and extend the host-test boundary-value parametrize.
2. `wire-constants-single-source.md` — single-source or drift-test
   `kVersion` against `pxt.json`; introduce one shared line-capacity
   constant for `emitLine` and both transports; drift-test the smaller
   duplicated-constant pairs (radio group ordinal, `kDiag*`).
3. `host-harness-double-drift.md` — re-sync the `WaHandle` doubles'
   wedge-field reads, route `setWheelsTimed` through
   `MotionEngine::wheelsV()` (or an equivalent path that preserves
   `cancelMove()` semantics), match the `std::lround` config-rounding
   behavior, and add a drift test that fails when only one side changes.
4. `settle-tick-loop-is-not-host-testable.md` — extract the settle loop's
   logic into a host-portable helper consumed by both `shims.cpp` and the
   host harness, preserving the single-ticking-fiber constraint; add a
   host test that exercises the extracted loop directly (not just its
   necessity, as the sprint 003 test does).

Detail planning will size each issue individually; the timeout-hardening
and constants-single-source issues are likely compact-or-smaller (each
touches one or two files with no new cross-module dependency), while the
settle-loop extraction may warrant more scrutiny since it moves logic
across the `shims.cpp`/`motion_engine` boundary that sprint 006's
stop-timing fix also touches.

## Success Criteria

- Host tests parametrized at timeout 0, 2^31−1, 2^31, and uint32-max all
  produce the intended (rejected/clamped/consistent) behavior for every
  X verb; none regress to the pre-fix wrap or stale-lease behavior.
- `kVersion` matches `pxt.json` by construction or a host test fails the
  build the moment they diverge; `emitLine` and both transports agree on
  one line-cap constant, and the radio transport's parity comment is
  either true or removed.
- A host test fails when the `WaHandle` doubles' wedge fields, the
  `setWheelsTimed`/`cancelMove()` path, or the config-rounding behavior is
  changed on only one side (double or production).
- The settle loop's bounded-iteration/break-on-rest/never-re-energize
  logic runs under a host test that would fail if the loop were deleted or
  shortened — not merely a test that proves the loop's necessity.
- All new/changed host tests pass; no regression in existing `tests/host`
  coverage; the full suite stays green.

## Scope

### In Scope

- `src/wire_handler.*`, `src/wire_adapter.*`, `src/protocol.*` — timeout
  decode/clamp logic, `kVersion`/line-cap single-sourcing, duplicated
  radio-group and `kDiag*` constant pairs.
- `tests/host` — `WaHandle` test-double re-sync, new boundary-value
  timeout tests, drift tests for constants and for the doubles, and a
  host test for the extracted settle-loop helper.
- `src/motion_engine.*` — only as far as the settle-loop extraction
  requires (a new host-portable helper consuming the loop's logic); no
  other motion_engine change.
- `src/shims.cpp` — reduced to platform glue around the extracted
  settle-loop helper; no behavior change to the loop itself, just where
  its logic lives.

### Out of Scope

- The transports' buffer/RX-ring work (`serial-transport-rx-ring-and-tx-serialization.md`)
  — that amends sprint 004, not this sprint.
- Motion geometry, stop-timing, continuous-mode odometry, heading wrap,
  and brick-reset rebaseline — sprint 006's domain, even where its
  stop-timing fix shares the settle-loop neighborhood with issue 4 here.
- Blocks, simulator parity, stall-latch visibility, `driveTick` contract,
  cruise sentinel, and `rotationalSlip` — sprint 007's domain.
- Any backlog issue not listed above (see the code review annex and
  `clasi/issues/` for the rest — notably the tools/link-layer
  consolidation and vendored-kernel re-diff items, not claimed here).
- Detail planning, architecture, use cases, and tickets — this is a
  roadmap-phase sprint; those are produced when this sprint is
  detail-promoted.

## Test Strategy

Host-only (`tests/host`), consistent with this project's practice of
catching wire/kernel defects without hardware wherever possible:

- Boundary-value parametrize extension for timeout decode: 0, 2^31−1,
  2^31, and uint32-max (4294967295), across every X verb, asserting
  consistent reject/clamp behavior and no stale kernel lease.
- A drift test reading `pxt.json`'s version alongside `protocol.cpp`'s
  `kVersion` (or asserting build-time substitution occurred), and a
  similar text-level drift test for the radio-group ordinal and
  `kDiag*` pairs across `main.ts` and the C++ headers/sources.
  Constants that no longer need mirroring because they were
  single-sourced don't need a drift test — only remaining duplicated
  pairs do.
- A drift test pinning the `WaHandle` doubles against production for the
  three confirmed divergences (wedge fields, `setWheelsTimed`/`cancelMove()`,
  config rounding) — designed so changing only one side fails it.
- A new host test that links against the extracted settle-loop helper
  directly and asserts its bounded-iteration/break-on-rest/never-
  re-energize behavior by execution, not by argument; the existing
  sprint-003 regression test stays as the "why this matters" test, this
  one becomes the "does the loop still do it" test.

## Architecture

**Sizing: Substantial.** Six issues touch real behavior across
`wire_handler.h/.cpp`, `wire_adapter.h/.cpp`, `protocol.cpp`,
`radio_transport.h`, `main.ts`, `motion_engine.h/.cpp`, `shims.cpp`, and
a wide swath of `tests/host/` — well past the compact tier's "one
module" line on module count alone. It also crosses the compact tier's
"no new cross-module dependency" line for real: the settle-loop
extraction (issue 4) gives `shims.cpp::tickDrive()` a new dependency on
a host-portable `motion_engine` helper it did not call before, and that
same helper becomes a new dependency of `tests/host/` (a new shim
consuming it directly) — a genuine new edge in the module graph, not a
field added to an existing table the way sprint 007's `kFields` growth
was compact-adjacent but still ruled substantial. No data-model change
this sprint (the wire's field set is unchanged; `TlmMode`'s existing
enum values get defined semantics, not new ones).

This project has opted into the persistent per-subsystem design-doc
overlay model (`design_docs: enabled`), so the full architecture
write-up — the 7-step methodology, module table, Design Rationale,
Migration Concerns, and Open Questions — lives in this sprint's
`design/` overlay, not here: see
[`design/DESIGN.md`](design/DESIGN.md) (the seeded copy of
`src/DESIGN.md`) §14 "Sprint 008 — architecture diagram and change
summary" (inline `Sprint 008:` annotations also land in §4, §5, §6,
§8, §9, and §11 where the changed modules already have sections) and
[`design/host-DESIGN.md`](design/host-DESIGN.md) (the seeded copy of
`tests/host/DESIGN.md`) for the host-harness-side detail (new shim, new
tests, gate-coverage growth, the WaHandle re-sync). `docs/design/design.md`
(the system doc, seeded copy at [`design/design.md`](design/design.md))
**was**
seeded and edited — its "Host-vs-target language standard" global
convention paragraph is updated with the standing per-sprint
build-checkpoint convention this sprint establishes (see the Design
Rationale summary below); `specification.md`/`usecases.md`/`overview.md`
were evaluated and **not** seeded, same as sprint 007's finding — they
are pre-opt-in legacy docs `validate_design` does not recognize as
canonical-doc-set members, and none of this sprint's fixes changes
student-facing block behavior in a way that needs a spec/UC edit (this
is a wire/test-infrastructure hardening sprint, not a student-API
sprint).

**The centerpiece decision (issue 6, target-viability gap).** Three
independent defect classes have now escaped the host suite because
nothing in the per-ticket or per-sprint flow requires a real target
build: a non-aggregate struct under C++11 (sprint 004 ticket 005), a
`uint8_t`-truncated buffer size (`-Woverflow`, same build), and a
`pxt.json` manifest omission that blocked every hex entirely (sprint
007 ticket 001). This sprint does **not** attempt to wire a hard,
automated build gate into `close_sprint` itself — that tool is part of
the CLASI MCP server, not this project's own source tree, so no ticket
here can implement it, and the two documented "known-benign, tolerate a
retry" failure modes (the legacy V1 `bbc-microbit-classic-gcc`
hex-merge failure, and the nondeterministic `TS9283`/`TS9043`/`TS9200`
packaging abort) make a hard pass/fail gate the wrong shape regardless
— a gate that cannot reliably distinguish "the compiler rejected a
`.cpp`" from "packaging aborted for an unrelated, retriable reason"
would either block sprints on ghosts or, if loosened to avoid that, stop
meaning anything. Instead this sprint formalizes what sprints 004 and
007 already did **informally** (each one's own last ticket happened to
run `make_deploy.py` and only that accident caught the defect): a
**mandatory, always-last, per-sprint build-checkpoint ticket** — the
same shape as sprint 004 ticket 005 and sprint 007 ticket 008, now
written down as a standing convention in `design.md` and `src/DESIGN.md`
§11 rather than left as something two sprints happened to do the same
way. The one piece of this that IS a real code change lands in
`tools/make_deploy.py` (unprotected, not part of the canonical
`docs/design/` doc set, edited directly by its ticket rather than
through the overlay): today `build()` only checks "does a hex exist,"
with no triage of *why* one doesn't — this sprint adds the triage the
issue asks for ("did any `.cpp` fail to compile," not the error code)
plus one automatic retry on the two documented benign abort shapes, so
the checkpoint ticket's own acceptance criterion — reintroduce a known
C++14-only construct or a manifest omission and confirm the checkpoint
catches it without a human reading raw compiler output — is something
the tool itself proves, not something a human has to eyeball each time.

**Summary for readers of this file alone** (see the overlay for full
detail): wire-layer timeout handling gets one enforcement point instead
of six ad hoc ones — `timeout`/`duration` is rejected at 0 and clamped
at 2^31−1 for every one of the six motion verbs at decode time in
`wire_handler.cpp`, before any verb handler or the kernel's own lease
math ever sees an out-of-range value, closing both the stale-armed-lease
class (R-06) and the wrapped-negative-deadline class (R-18) at the same
choke point. `kVersion` stops hand-mirroring `pxt.json`; `emitLine`'s
200-byte clip and both transports' line caps collapse onto one shared
constant, and `radio_transport.h`'s now-false "equals SerialTransport's"
comment is corrected to state the truth (it is deliberately *not*
coupled, sized to a bare-Column literal that has drifted); the
`RUN_EVENT_SOURCE`/`kRunEventSource` `0x2001` duplicate between
`main.ts` and `protocol.cpp` gets a drift test, as does the `kDiag*`
ordinal set shared by name-only convention between `wire_adapter.cpp`
and `shims.cpp`'s two independent switch statements. The `WaHandle`
test doubles are re-synced to the three confirmed drifts (wedge fields,
`setWheelsTimed` routing through `MotionEngine::wheelsV()`'s
`cancelMove()`, `std::lround` config rounding) with no production
change required — the doubles were wrong, not the code they mirror —
plus a drift test proven, by demonstration, to fail when only one side
changes. The settle-tick loop's bounded-iteration/break-on-rest logic
is extracted into a new `MotionEngine` method consuming only the
already-host-portable kernel port (`kernel.step()`/`kernel.output()`),
leaving `shims.cpp::tickDrive()` with only the platform-specific
`odomUpdate()` call and the loop-invocation glue; a new host test
exercises the extracted loop directly, closing the gap the sprint 003
regression test could only argue for. `TLM AUTO` becomes a documented
alias for `TLM POSE` (matches today's de facto behavior — zero risk);
`TLM BUFFER` becomes an explicit `kUnimplemented` refusal instead of a
silent, unspecified fall-through, since no buffering mechanism actually
exists to give it real semantics yet (a genuine behavior change for any
host currently sending `TLM BUFFER` unknowingly — see Migration
Concerns below).

**Known behavior changes, not risks:**
- A host currently sending `TLM BUFFER` and unknowingly receiving
  POSE's 12 columns will now receive `err 6 #<id>` (`kUnimplemented`)
  instead — the point of the fix (issue 5). No in-tree tool sends this
  today (not exhaustively checked — cheap due diligence for whoever
  executes that ticket, same caveat sprint 007's `default_cruise` fix
  carried).
- A host sending a motion verb with `timeout 0`/`duration 0` today gets
  `ok` and either an instant no-op (MOVE_X) or a stale-lease lurch
  (WHEELS_X); after this sprint every one of the six motion verbs
  refuses `0` outright (`err 3 #<id>`, `kRange`) instead. This is a
  strict behavior change for any caller that relied on either of the
  old, disagreeing meanings of `0` — the review's own framing treats
  both old meanings as bugs, not features, so no caller should be
  relying on either deliberately, but it is a wire-visible change worth
  stating plainly.
- A host sending a `timeout`/`duration` above 2^31−1 today either wraps
  the deadline negative (killing the move almost immediately, R-18) or,
  post-fix, gets the value silently clamped to 2^31−1 (~24.8 days) — a
  strict improvement (the move now actually runs), not a new refusal.

**Risk (known, not newly introduced):** none of this sprint's own
changes touches `diffdrive.{h,cpp}` (the vendored kernel stays
byte-unchanged, so no cross-repo resync is triggered) or any CODAL-only
file's *logic* — the settle-loop extraction moves logic, it does not
change what that logic does, and the constants work is pure
single-sourcing. The one item worth tracking procedurally, not
architecturally: the settle-loop extraction's call-site change in
`shims.cpp::tickDrive()` is, like every `shims.cpp` change, invisible to
every host test by construction (§1's layering table) — this sprint's
own build-checkpoint ticket is what proves that call site still
compiles and links against the new signature, exactly the class of gap
issue 6 exists to close, applied to this sprint's own riskiest change.

## Use Cases

None of `docs/design/usecases.md`'s UC-001..UC-016 cover wire-protocol
or test-infrastructure behavior (they are all student-facing block use
cases) — every SUC below is bench/host/maintainer scope, following
sprint 004's own precedent for this project's wire-protocol work (its
SUC-001..007 are the model this sprint's SUCs reuse). Sized to the
substantial tier: full treatment for the two SUCs with real wire-visible
behavior change (SUC-001, SUC-005), proportional treatment for the rest.

### SUC-001: A wire host's malformed timeout can no longer arm a stale move or wrap into an early kill
Parent: N/A (bench/host use case; closes `wire-timeout-hardening.md`,
R-06 + R-18)

- **Actor**: A bench host or Python tool issuing raw wire motion verbs
  (`WHEELS_X`/`WHEELS_V`/`MOVE_X`/`MOVE_V`/`GO_TO_R`/`GO_TO_W`).
- **Preconditions**: The robot is connected and commandable.
- **Main Flow**:
  1. Host sends any of the six motion verbs with `timeout`/`duration`
     field `0`. Decode rejects it before the verb's handler or the
     kernel's own lease math ever runs: `err 3 #<id>` (`kRange`), no
     motion obligation armed, no kernel lease staged.
  2. Host sends the same verb with `timeout`/`duration` above
     2^31−1 (up to the wire's full `uint32` range, 4294967295). Decode
     clamps it to 2^31−1 before the handler runs — the move is
     accepted and commanded for the full clamped duration, not killed
     ~150 ms in by a wrapped-negative deadline comparison.
  3. Host sends a `timeout`/`duration` in the previously-tested range
     (1..5000 ms): behavior is unchanged.
- **Postconditions**: `0` means the same thing — refusal — on every one
  of the six motion verbs; no value a host can send produces either a
  stale-armed kernel lease with no ticking obligation, or a
  wrap-induced early kill.
- **Acceptance Criteria**:
  - [ ] A host test parametrized at `0`, `2^31−1`, `2^31`, and
        `4294967295` (uint32-max) exercises all six motion verbs and
        asserts the documented reject/clamp/unchanged behavior for each.
  - [ ] `0` on `WHEELS_X` no longer leaves `MotionEngine`'s kernel lease
        armed while `WireAdapter::hasLiveMotionObligation()` reports
        false — a host test drives this specific R-06 sequence and
        asserts no obligation/lease mismatch.
  - [ ] A value above 2^31−1 no longer reproduces the ticket-011
        starvation pattern (an acked move dying at ~150 ms) — a host
        test drives the exact R-18 sequence and asserts the move keeps
        running past 150 ms.

### SUC-002: A maintainer trusts kVersion, emitLine's cap, and the radio parity comment because they can no longer silently drift
Parent: N/A (bench/host use case; closes `wire-constants-single-source.md`,
R-17 + R-21)

- **Actor**: A firmware maintainer relying on `VER`'s reply during
  `mbdeploy`'s deploy-verification flow, or reading
  `radio_transport.h`'s header comments.
- **Preconditions**: `pxt.json`'s version has been bumped since the last
  time `protocol.cpp`'s `kVersion` was hand-updated (the actual,
  ten-bump-drifted state at sprint start).
- **Main Flow**:
  1. Maintainer builds and flashes; `ID`/`VER`'s reply matches
     `pxt.json`'s version by construction (single-sourced) or a host
     test fails the build the moment they diverge (drift-tested) —
     either mechanism is acceptable, chosen during ticket execution
     against what the build toolchain actually allows.
  2. A bench tool sends a maximal 240-byte `RUN:` result line through
     `emitLine()`; it is no longer clipped at the old bare `200`.
  3. Maintainer reads `radio_transport.h`'s `kMaxPayloadBytes` comment;
     it states the true relationship to `SerialTransport`'s cap
     (deliberately uncoupled, not "equals") instead of a claim the
     ticket-005 serial-cap raise already falsified.
- **Postconditions**: `kVersion`, the line-cap constants, the
  `RUN_EVENT_SOURCE`/`kRunEventSource` pair, and the `kDiag*` ordinal
  set each have exactly one source of truth or an automated test that
  fails the moment two copies disagree — never neither.
- **Acceptance Criteria**:
  - [ ] A host test (or the build itself) fails when `kVersion` and
        `pxt.json`'s version disagree.
  - [ ] `emitLine` and both transports read one shared line-capacity
        constant; a host test pins its value and confirms `emitLine` no
        longer truncates below it.
  - [ ] `radio_transport.h`'s parity comment states the true
        relationship to `SerialTransport`'s cap.
  - [ ] A host test fails if `main.ts`'s `RUN_EVENT_SOURCE` and
        `protocol.cpp`'s `kRunEventSource` diverge.

### SUC-003: A test that exercises DIAG wedge state, command supersession, or config rounding through WaHandle is exercising what production actually does
Parent: N/A (bench/host use case; closes `host-harness-double-drift.md`,
R-25)

- **Actor**: A future test author extending `tests/host/test_wire_motion_verbs.py`
  or a similar `WaHandle`-based suite.
- **Preconditions**: None of the three confirmed drifts have been
  exercised by any existing test (the issue's own finding: "no WaHandle
  test drives wedge at all").
- **Main Flow**:
  1. A test reads `WaHandle`'s DIAG ordinal 6/7 (wedge); it reflects the
     same field production's `diagValue()` reports
     (`wedgeSuspectLeft/Right`), not the double's previous
     `wedgeLeft/Right` substitution.
  2. A test drives `WHEELS_V` through `WaHandle`'s `setWheelsTimed`
     while a move-engine move is in flight; the new command supersedes
     it via the same `cancelMove()` path production's
     `MotionEngine::wheelsV()` takes, not a direct `kernel.drive()` call
     that skips it.
  3. A test reads a config field back through `WaHandle`'s
     `getConfigValue` double; its rounding matches production's
     `std::lround(v * 1000.0)`, not a truncating `static_cast<int>(v *
     1000.0f)`.
- **Postconditions**: The three fields/paths above are drift-tested — a
  new host test that fails if either side (double or production)
  changes alone, demonstrated by temporarily reverting the double's fix
  and confirming that new test goes red, then restoring it green.
- **Acceptance Criteria**:
  - [ ] `WaHandle`'s DIAG shim reads `wedgeSuspectLeft/Right`.
  - [ ] `WaHandle`'s `setWheelsTimed` routes through the same
        `cancelMove()`-triggering path production's `setWheelsTimed`
        uses (directly or via an equivalent call sequence).
  - [ ] `WaHandle`'s config-rounding double matches `std::lround`
        semantics, including the double-vs-float precision production
        uses.
  - [ ] A new drift test is shown, by demonstration, to fail when only
        one side of any of the three pairs above changes.

### SUC-004: A regression that deletes or shortens the post-move settle loop fails a host test, not just a hardware session
Parent: N/A (bench/host use case; closes
`settle-tick-loop-is-not-host-testable.md`, filed after sprint 003
ticket 009)

- **Actor**: A future contributor editing `shims.cpp::tickDrive()` or
  the extracted settle-loop helper; the host test suite acting on their
  behalf.
- **Preconditions**: A move-engine move has just ended
  (`wasActive && !moveActive`, `tickDrive()`'s existing gate, unchanged
  by this sprint).
- **Main Flow**:
  1. `tickDrive()` calls the new `MotionEngine` settle helper instead of
     its own inline loop; the helper steps the kernel up to its bounded
     iteration cap, breaking early once both wheels measure at or below
     the rest threshold, exactly as the inline loop did.
  2. `shims.cpp` calls `odomUpdate(r)` once, after the helper returns,
     exactly as today — odometry ownership does not move into
     `motion_engine`, only the settle/rest decision does (the sprint 003
     comment's stated objection to extraction — "would mean moving
     odometry ownership into motion_engine too" — does not apply to this
     narrower cut).
  3. A new host test drives the extracted helper directly (via a new
     `kernel_shim.cpp`/`fake_ports.h`-based shim, reusing the
     `FakeSleeper::onSleep` hook where useful) and asserts the
     bounded-iteration/break-on-rest/never-re-energize behavior by
     executing the loop, not by argument.
- **Postconditions**: The loop's shape (max iterations, rest threshold,
  no re-energizing) is provably present by running it; the
  one-fiber-ticks-a-move constraint is unaffected — no new fiber or
  ticker is introduced, and the helper is called from the same single
  call site `tickDrive()` already owned.
- **Acceptance Criteria**:
  - [ ] A host test constructs the settle scenario (wheels coasting
        above rest threshold at move end) and asserts the helper steps
        the kernel until rest or the iteration cap, matching the
        pre-extraction loop's measured behavior
        (`tests/host/test_regression_post_move_neutral.py` stays green,
        unchanged).
  - [ ] A host test proves the iteration cap is enforced (wheels held
        artificially above rest threshold for longer than the cap) —
        the helper returns after the cap, not indefinitely.
  - [ ] `shims.cpp::tickDrive()`'s own body shrinks to platform glue
        plus the helper call plus `odomUpdate()` — no settle-decision
        logic left inline.
  - [ ] The new helper is added as a method on the existing
        `MotionEngine` class, defined in `motion_engine.cpp` — already
        one of the four files `test_cxx11_syntax_gate.py`'s
        `-std=c++11 -fsyntax-only` gate covers, so no new gate
        registration is needed (unlike sprint 006's `heading_wrap.h`/
        `encoder_glitch_armor.h`/`encoder_pose_source.h`, which needed
        new dedicated syntax-check translation units because they were
        new files); a passing gate run after the change confirms
        coverage extends to the new method with no further action.

### SUC-005: TLM AUTO and TLM BUFFER stop being an implementer's accident
Parent: N/A (bench/host use case; closes
`tlm-auto-buffer-column-set-undefined.md`)

- **Actor**: A telemetry consumer selecting a `TLM` mode other than
  `POSE`/`FULL`/`OFF`.
- **Preconditions**: `TLM AUTO #<id>` or `TLM BUFFER #<id>` is sent.
- **Main Flow**:
  1. Host sends `TLM AUTO #<id>`. It is now a **documented alias** for
     `TLM POSE` — the same 12-column set, on the same existing 50 ms
     protocol cadence. This matches today's de facto fall-through
     behavior exactly; the only change is that it is now a stated
     decision (pinned by a host test on the emitted `thdr`), not an
     accident of an unhandled `switch` default.
  2. Host sends `TLM BUFFER #<id>`. It is now refused —
     `err 6 #<id>` (`kUnimplemented`) — because no buffering mechanism
     exists anywhere in this codebase to give "buffer" real, narrower
     semantics yet; answering `err` is more honest than emitting an
     unspecified column set (the issue's own preferred resolution).
  3. Host sends `TLM POSE`/`TLM FULL`/`TLM OFF #<id>`: unchanged.
- **Postconditions**: Every `TLM` mode either has documented, tested
  semantics or is an explicit, documented refusal — no mode silently
  falls through to a column set nobody specified.
- **Acceptance Criteria**:
  - [ ] A host test asserts `TLM AUTO`'s emitted `thdr` is
        byte-identical to `TLM POSE`'s.
  - [ ] A host test asserts `TLM BUFFER` returns `err 6 #<id>` and
        never emits a `thdr`/`t` frame.
  - [ ] `wire_adapter.h`'s `buildSnapshot()` doc comment states the
        decision (`AUTO` = alias for POSE; `BUFFER` = unimplemented)
        instead of describing the fall-through as unspecified.

### SUC-006: A sprint cannot close having only proven its host suite is green
Parent: N/A (bench/host use case; closes
`host-tests-compile-newer-standard-than-target.md`, the sprint's
centerpiece issue)

- **Actor**: The firmware maintainer closing out this sprint (mirrors
  sprint 004's own SUC-006, now formalized as a standing per-sprint
  practice rather than a one-sprint precedent).
- **Preconditions**: All host tests pass; every other ticket in this
  sprint is done.
- **Main Flow**:
  1. Maintainer runs the (now triage-aware) `tools/make_deploy.py`. A
     genuine `.cpp` compile failure on either real target variant is
     reported as a hard failure, distinguished from the two documented
     benign abort shapes (legacy V1 hex-merge failure; the
     nondeterministic `TS9283`/`TS9043`/`TS9200` packaging abort after a
     pxt-core cache-write `TypeError`), which are retried once
     automatically rather than surfaced as a false failure.
  2. A flashable hex is produced from this sprint's own final state —
     proof that every change this sprint made, including the ones no
     host test can see (`shims.cpp`'s settle-loop call site,
     `protocol.cpp`'s `kVersion`/`emitLine`, `radio_transport.h`), still
     compiles and links for both real embedded targets.
  3. Maintainer confirms the triage logic itself: reintroducing a known
     C++14-only construct (or a `pxt.json` manifest omission) into a
     scratch copy is reported as a real failure, not swallowed by the
     retry-on-benign-abort logic.
- **Postconditions**: A flashable artifact exists; the sprint's own
  target-viability claim is proven by a real build, not inferred from a
  green host suite. No hardware flashing or live telemetry capture is
  performed or claimed — building a hex needs network access to the
  cloud compiler, not a robot, so this SUC's acceptance criteria are
  satisfiable with no bench session.
- **Acceptance Criteria**:
  - [ ] `tools/make_deploy.py` distinguishes a real `.cpp` compile
        failure from the two documented benign abort shapes, retrying
        the latter once automatically.
  - [ ] A real build produces a flashable hex from this sprint's final
        state, with no code change required beyond the documented
        retry.
  - [ ] Reintroducing a known C++14-only construct (or omitting a file
        from `pxt.json`) is confirmed to make the checkpoint fail, not
        silently pass via the retry path.
  - [ ] `src/DESIGN.md` §11 and `docs/design/design.md`'s "Host-vs-target
        language standard" convention both state the standing
        per-sprint build-checkpoint practice this ticket establishes.

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Issue | Depends On |
|---|-------|-------|------------|
| 001 | Wire timeout hardening: reject 0, clamp above 2^31-1, unify across all six motion verbs | `wire-timeout-hardening.md` | — |
| 002 | Wire constants single-sourced: kVersion, emitLine/line-cap, RUN_EVENT_SOURCE, kDiag* drift tests | `wire-constants-single-source.md` | — |
| 003 | Host-harness WaHandle re-sync: wedge fields, setWheelsTimed/cancelMove, config rounding, drift test | `host-harness-double-drift.md` | — |
| 004 | Settle-tick loop extraction: host-testable MotionEngine settle helper | `settle-tick-loop-is-not-host-testable.md` | — |
| 005 | TLM AUTO/BUFFER column-set semantics: AUTO aliases POSE, BUFFER refuses | `tlm-auto-buffer-column-set-undefined.md` | — |
| 006 | Target-viability build checkpoint: triage-aware make_deploy.py and the standing per-sprint convention | `host-tests-compile-newer-standard-than-target.md` | 001, 002, 003, 004, 005 |

Tickets execute serially in the order listed. Tickets 001-005 are
mutually independent (each touches a distinct concern; ordering among
them is by issue priority — High, Med, Med, pre-review, Low — not by
dependency) and could in principle run in any relative order; they are
sequenced 001-005 for narrative clarity (wire-layer hardening, then
constants, then test-harness hygiene, then the settle-loop's own
module-boundary change, then the small TLM decision). Ticket 006 is the
sprint's own build-checkpoint and depends on all five, by design — it
exists to validate the sprint's *combined* final state, not any one
ticket in isolation, and must run last.
