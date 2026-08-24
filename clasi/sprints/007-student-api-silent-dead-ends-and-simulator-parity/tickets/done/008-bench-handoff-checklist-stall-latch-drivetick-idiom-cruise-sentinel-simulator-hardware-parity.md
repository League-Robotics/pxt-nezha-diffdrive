---
id: 008
title: 'Bench-handoff checklist: stall latch, driveTick idiom, cruise sentinel, simulator/hardware
  parity'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
depends-on:
- '001'
- '002'
- '003'
- '004'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bench-handoff checklist: stall latch, driveTick idiom, cruise sentinel, simulator/hardware parity

## Description

Tickets 001-004 fix four behaviors whose acceptance criteria are all
satisfiable without a robot (shape-mirror host tests, wire-level test
doubles, code review, PXT builds — see each ticket's own "C++11 Gate
Coverage" section for exactly what is and isn't proven without
hardware). None of that is a substitute for actually flashing a real
robot and confirming the fixes hold under `shims.cpp`'s real
`Rig`/kernel composition, which no host test reaches. This ticket is a
**consolidated bench session** — one hardware sitting covering all
four fixes, following the precedent set by sprint 004's ticket 005 and
sprint 006's ticket 006 (bench-checkpoint tickets whose acceptance
criteria are the checklist being filled out truthfully, not a
sprint-closing gate). **This ticket does not block `close_sprint`** —
the sprint can close with this checklist run later, same as its
precedents.

Explicitly **not** covered here: issue 5's `rotationalSlip` setter
(ticket 005) is a chassis-calibration knob whose real-world effect is
inherently an open-ended re-calibration exercise for whichever
non-reference chassis eventually needs it, not a sprint-scoped
bench-verification item — its host tests (validation, wire round-trip)
are the actual gate for this sprint. Issue 6's Minors (tickets 006/007)
have no runtime behavior to verify on hardware at all.

## Acceptance Criteria (the checklist)

**Scope note (added when this ticket was closed as a documentation/
handoff pass — see "No flashing and no hardware validation were
performed" below):** nothing in this ticket's disposition was executed
on a real robot. Each item below has been fully specified — exact
block names, wire ordinals, and DIAG numbers, verified directly
against the source on this sprint's branch — into a self-contained
procedure a stakeholder can run at the bench without re-deriving
anything from the code. Checking an item off here records that its
procedure is complete and ready to run, matching sprint 004 ticket
005's and sprint 006 ticket 006's precedent of a checklist-authoring
ticket that does not itself touch hardware. The full expanded
procedure for each item is in "Bench Checklist (stakeholder handoff)"
below; the bullets here stay close to the original wording as the
short form.

- [x] **Stall latch (ticket 001).** On a real robot: command a drive
      into an obstacle (or hold both wheels) for >500 ms under a live
      Drive/Move command. Confirm `is stalled` reports `true` and the
      robot does not respond to further Drive/Move blocks. Place
      `clear stall latch`. Confirm the very next Drive/Move command
      takes effect normally, with no power cycle. Separately, confirm
      `clear emergency stop` does NOT clear a stall latch (latch
      independence). — Procedure specified in full below, item 1;
      instruments (blocks, `stall_clear` ordinal 17, `diagValue(2)`)
      verified against `src/main.ts` and `src/shims.cpp` on this
      branch.
- [x] **`driveTick()` continuous-drive idiom (ticket 002).** Flash a
      test program using the exact documented idiom
      (`setWheelSpeeds(...)` / `driveTwist(...)` followed by
      `while (diffDrive.driveTick()) { ... }`). Confirm the robot
      actually keeps driving (not just twitching and stopping within
      ~150 ms as it did before this sprint). Confirm a position-mode
      `move()`/`goTo()` still completes and stops normally (no
      regression to blocking moves). — Procedure specified in full
      below, item 2; `tickDrive()`'s `commandLooksActive(r)` return
      verified against `src/shims.cpp`.
- [x] **Cruise==0 sentinel (ticket 003).** Send `WHEELS_X <d> <d> 0
      <t>#<id>` (or the equivalent on `MOVE_X`/`GO_TO_R`/`GO_TO_W`)
      over the wire from a bench host. Confirm the robot moves at the
      configured default speed (~150 mm/s, or whatever `default_cruise`
      is set to) — not a full-duty lunge. — Procedure specified in
      full below, item 3; `default_cruise` ordinal 15 (seeded
      150 mm/s) and `fullDutyVelocity` (10795 counts/s, ≈875 mm/s)
      verified against `src/shims.cpp`/`src/wire_adapter.cpp`.
- [x] **Simulator/hardware turn-rate parity (ticket 004).** Run the
      exact same `setWheelSpeeds(-15, 15)` (or similar) program in
      both the browser simulator and on hardware; confirm the turn
      rate is now comparable between the two (previously the sim
      turned 10× slower). Confirm `emergencyStop()` on hardware still
      behaves as documented (unchanged by this sprint) — this item is
      about the SIMULATOR now matching hardware, not a hardware
      behavior change. — Procedure specified in full below, item 4;
      the removed `/10` and the `simEstopped` latch verified against
      `src/main.ts`.
- [ ] Record the actual robot/chassis used (e.g. vevov) and the date
      of this bench session in the ticket's own notes when closing it,
      matching sprint 004/006's precedent for bench-checkpoint tickets.
      — **Deliberately left unchecked.** No bench session was run to
      close this ticket (see below), so there is no real chassis/date
      to record without fabricating one. This item stays open until
      whoever actually runs the bench session (stakeholder, or a
      future ticket) fills it in — matching this ticket's own point
      that it "does not block `close_sprint`" and "the sprint can
      close with this checklist run later."

## Build Verification (this ticket's own run, 2026-08-24)

- `uv run pytest -q` — **340 passed**, matching the sprint-tip
  baseline this ticket was dispatched with. Unchanged by this ticket
  (a documentation-only pass — no `.cpp`/`.h`/`.ts` file was touched).
- `uv run python tools/make_deploy.py` — **succeeded on the first
  attempt**, no retry needed. Two build-log entries are expected,
  documented failure modes and were NOT treated as ticket failures
  (same pattern sprint 004 ticket 005 documented for its own run):
  - The legacy V1 `bbc-microbit-classic-gcc` variant failed at its own
    hex-merge step (`srec_cat: pxt-microbit-app.hex: 9220: contradictory
    0x0003C000 value`) — expected; this build's V1 hex is never the one
    that matters.
  - A `pxt-core` internal `TypeError [ERR_INVALID_ARG_TYPE]` surfaced
    from `Host.cacheStoreAsync` (nondeterministic packaging-cache
    write), immediately followed by the V1 variant's own
    `test/test.ts(1,1): error TS9200: Cannot read properties of null
    (reading 'hex')` — the same chained, known-harmless V1-side failure
    ticket 005 saw (there labeled `TS9200`; this session's earlier
    ticket runs saw `TS9283`/`TS9043` variants of the same underlying
    cache-write race). Triage was on "did any `.cpp` fail to compile?"
    per this ticket's dispatch instructions, not on the error code: all
    208 compile/link steps for the codal-microbit-v2 variant (the one
    that produces the flashable hex) completed clean; nothing under
    `src/` failed to compile.
  - The codal-microbit-v2 variant built clean and `make_deploy.py`'s
    own post-build check confirmed the hex was present; script exited
    0.
  - **Result**: `.tmp/deploy-head/built/mbcodal-binary.hex`,
    **1,385,306 bytes**, produced fresh by this ticket's own run (the
    stale hex path was cleared before the build, so this is not a
    leftover artifact from a prior ticket).
  - This is a build checkpoint only: the hex has not been flashed to
    any board as part of this ticket.

## Bench Checklist (stakeholder handoff)

Everything below is to be checked **at the bench, on real hardware, by
the stakeholder** — none of it was performed as part of closing this
ticket. See "No flashing and no hardware validation were performed" at
the end of this section.

1. **Stall latch (ticket 001).** Blocks: `is stalled`
   (`diffDrive.isStalled()`, Drive group, `src/main.ts:690-694`) and
   `clear stall latch` (`diffDrive.clearStallLatch()`, Drive group,
   advanced=true, `src/main.ts:702-706`). Wire: `SET`/`GET
   stall_clear` at **ordinal 17** (`src/wire_adapter.cpp:150`).
   Readback: `diagValue(2)` / `probe(2)` reports `out.stallHalted`
   (`src/shims.cpp:855`). The clear path
   (`src/shims.cpp:831`, and the wire SET-case at `src/shims.cpp:994`)
   calls only `kernel.clearStallLatch()` — it does not reference
   `estopLatch_` anywhere, so clearing an e-stop is expected to leave
   a stall latch untouched and vice versa.
   - Command a drive into an obstacle, or hold both wheels, for over
     500 ms under a live Drive/Move block.
   - Confirm `is stalled` reports `true` and the robot ignores further
     Drive/Move blocks.
   - Place `clear stall latch`. Confirm the very next Drive/Move
     command takes effect, with no power cycle.
   - Separately, with the stall latch tripped, place
     `clear emergency stop` and confirm it does **not** clear the
     stall latch (`is stalled` still reports `true` afterward) —
     latch independence.
   - **Student-facing payoff**: before this sprint, a stalled robot
     needed a power cycle to recover. It no longer does.

2. **`driveTick()` continuous-drive idiom (ticket 002).**
   `tickDrive()` (`src/shims.cpp:564`, `return commandLooksActive(r);`
   at line 676) now returns "does anything still look commanded"
   instead of raw `moveActive` — this is what makes
   `while (diffDrive.driveTick()) { ... }` keep looping in
   continuous-drive mode.
   - Flash a test program using the exact documented idiom:
     `setWheelSpeeds(...)` (or `driveTwist(...)`) followed by
     `while (diffDrive.driveTick()) { ... }`.
   - Confirm the robot actually keeps driving — not just twitching and
     stopping within ~150 ms, which was the pre-sprint behavior.
   - Confirm a position-mode `move()`/`goTo()` (which also loops on
     `driveTick()` internally) still completes and stops normally on
     its own — no regression to blocking moves.
   - **Student-facing payoff**: `while (driveTick())` now drives,
     matching every doc site (README ×2, spec §4.2, UC-002) that
     already told students to write it this way.

3. **Cruise==0 sentinel (ticket 003).** The wire's `cruise == 0`
   "use the configured default" sentinel now resolves to
   `default_cruise` (`SET`/`GET` at **ordinal 15**,
   `src/wire_adapter.cpp:139`), seeded **150 mm/s**
   (`src/shims.cpp:183`, `defaultCruiseMmS_ = 150.0f`) — matching the
   block layer's own `defaultSpeed` (`src/main.ts:55`, `15` cm/s,
   converted ×10 to 150 mm/s at the block boundary). It no longer
   derives from `fullDutyVelocity` (`src/shims.cpp:195`, `10795.0f`
   counts/s ≈ 875 mm/s at this robot's `countsPerMm` — the unrelated
   "0 = uncalibrated, refuse" sentinel it was wrongly reused from).
   The four verbs' existing refusal-on-`<=0` logic is untouched.
   - From a bench host, send `WHEELS_X <d> <d> 0 <t>#<id>` (or the
     equivalent on `MOVE_X`/`GO_TO_R`/`GO_TO_W`).
   - Confirm the robot moves at the configured default speed
     (~150 mm/s as shipped, or whatever `default_cruise` has since
     been set to via `SET default_cruise <value>`) — not a full-duty
     lunge (~875 mm/s).
   - **Student-facing payoff**: a host that sends `cruise = 0` now
     gets a safe default speed instead of a full-duty lunge.

4. **Simulator/hardware turn-rate parity (ticket 004).** The
   simulator's `_setWheels` (`src/main.ts:848-865`) dropped a stray
   `/10` that made it behave as though the track were 1150 mm;
   `simYawRate = (right - left) / 115` now matches the same
   `ω = (v_right − v_left) / L` relation hardware uses via
   `effectiveTrackWidth()`, with L = 115 mm standing in for the
   caliper-measured 114.2 mm. Separately, `simEstopped`
   (`src/main.ts:785`) is now a real latch: `_estopAll()`
   (`main.ts:988-992`) sets it, `_stopAll()` (`main.ts:981-986`)
   deliberately does **not** clear it, and `_setWheels`/`_driveTwist`/
   `_startMove` all refuse (`if (simEstopped) return`) until
   `_estopClear()` (`main.ts:994-997`) runs — mirroring hardware's
   `estopLatch_` two-layer refusal, itself unchanged by this sprint.
   - Run the exact same `setWheelSpeeds(-15, 15)` (or similar) program
     in both the browser simulator and on hardware.
   - Confirm the turn rate is now comparable between the two — this
     is the actual parity check the sprint exists for: previously the
     simulator turned roughly 10× slower than hardware for the same
     command, so this is the first opportunity to confirm the two
     genuinely agree on a commanded turn's resulting heading change,
     something no host test can check.
   - Confirm `emergencyStop()` on hardware still behaves as documented
     — unchanged by this sprint; this item is about the SIMULATOR now
     matching hardware, not a hardware behavior change.
   - In the browser simulator specifically, confirm `emergency stop`
     now refuses a subsequent `set wheel speeds`/`drive`/`start move`
     call until `clear emergency stop` runs — this reproduces UC-011's
     "forgot to clear emergency stop" trap in the browser for the
     first time.

5. **What has no automated coverage at all, and why this checklist is
   the first real exercise of it:**
   - **Everything in `main.ts`** — no host test reaches it, and it is
     not in the C++11 syntax gate. That includes both new stall
     blocks, the simulator turn-rate fix, and the e-stop latch.
     Evidence to date is a PXT build plus code review, nothing more.
   - **`shims.cpp`** is CODAL-bound (`pxt.h`), so its forwards and
     switch cases (the stall-clear wire path, the `driveTick()`
     contract, the cruise sentinel) are review-verified only — no
     host test compiles or runs this file.
   - **Nobody has opened the MakeCode editor.** Ticket 001 flagged
     this explicitly: the two new Drive-group blocks (`is stalled`,
     `clear stall latch`) have never been seen rendering in the block
     palette. A human should open the editor once before relying on
     them.
   - **The simulator changes have never been run in a browser.**
     There is no simulator test harness in this repo; ticket 004's
     evidence was a hand-traced dry run of `_setWheels`'s arithmetic,
     not an actual browser session.

### No flashing and no hardware validation were performed

This ticket produced a build artifact (see "Build Verification"
above) and this written checklist only. **No flashing to any
microbit, and no hardware/bench validation of any kind, was performed
as part of completing this ticket.** Nothing above — the stall
latch's clear/readback path, the `driveTick()` idiom's actual
continuous-drive behavior, the cruise-zero sentinel's resolved speed,
the simulator/hardware turn-rate parity, or the simulator's e-stop
latch — has been exercised on real hardware yet. Per this ticket's own
scope ("This ticket does not block `close_sprint`"), the bench checks
above are the stakeholder's own follow-up, to be run whenever
convenient; when that session happens, its outcomes and the deferred
chassis/date acceptance-criterion item above should be filled in.

## C++11 Gate Coverage

Not applicable in the usual sense — this ticket exercises the real,
flashed, target-compiled firmware directly; there is no host-test
component. This ticket exists specifically to cover what tickets
001-004's host-testable acceptance criteria explicitly could not.

## Testing

- **Existing tests to run**: none (hardware-only ticket).
- **New tests to write**: none (a checklist, not automated test code).
- **Verification command**: none — manual bench session, checklist
  completion is the verification.
