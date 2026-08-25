---
id: '005'
title: 'Bench verification checklist: unreachable brick at boot and mid-session'
status: done
use-cases:
- SUC-002
depends-on:
- '003'
- '004'
github-issue: ''
issue: unpowered-nezha-brick-wedges-program-at-boot.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bench verification checklist: unreachable brick at boot and mid-session

## Description

Bench-only handoff ticket (precedent: sprint 004 ticket 005, sprint 006
ticket 006, sprint 007 ticket 008, sprint 008 ticket 006) — no code,
no host test. Neither this project's `NezhaMotorPort`
(`nezha_port.cpp` requires `pxt.h`) nor `RadioTransport` has ever had a
host-portable seam for the failure paths this sprint addresses; the
robot behaviors this sprint's Success Criteria require can only be
confirmed live. This ticket produces the checklist a stakeholder runs at
the bench, informed by tickets 003 and 004's findings and by the new
`cyc=` STATUS field.

## Acceptance Criteria

**Scope note (this ticket closes as a documentation/checklist-authoring
pass — see "No flashing and no hardware validation were performed"
below).** Nothing in this ticket's disposition was executed on a real
robot. Each item below has been fully specified — exact wire commands,
`STATUS` fields, and source references, verified directly against
`src/nezha_port.cpp`, `src/diffdrive.cpp`, `src/wire_handler.{h,cpp}`,
and `src/wire_adapter.cpp` on this branch — into a self-contained
procedure a bench operator can run without re-deriving anything from
the code, following the precedent set by sprint 004 ticket 005, sprint
006 ticket 006, sprint 007 ticket 008, and sprint 008 ticket 006.
Checking an item off here records that its procedure is complete and
ready to run, not that it has actually been run. The two items below
that require an actual bench-observed measurement or result — the
wall-clock timing number, and recording results back into the issue
file — stay unchecked; only a robot can satisfy them. The full expanded
procedure is in "Bench Checklist (stakeholder handoff)" below.

- [x] A written checklist exists (in this ticket or a linked bench-notes
      file) covering, at minimum:
  - [x] **Boot-priming path**: with the Nezha brick physically powered
        down or I2C-disconnected, flash and boot the robot. Confirm: the
        boot banner and every subsequent v6 reply (`VER`/`ID`/`STATUS`/
        `GET`) are still emitted (protocol fiber alive); `STATUS` reports
        `connL=0 connR=0`; issuing a command that ticks the kernel (e.g.
        `RUN:straight:0` or a wire motion verb) advances `cyc` above 0
        (the new field from ticket 003) while `i2cFaultCount` climbs and
        `connL`/`connR` stay 0; a motion block/verb becomes a no-op
        rather than hanging the program. — Procedure specified in full
        below, item 3.
  - [x] **Mid-session disconnection**: with the robot already ticking
        (a live `while (tickDrive())` loop or an in-flight wire motion
        obligation), physically disconnect the brick. Confirm the same
        signature (`connL`/`connR` drop to 0, `i2cFaultCount` climbs,
        `cyc` keeps advancing, TLM/DIAG/protocol stay alive, motion
        stops being effective) rather than the program hanging. —
        Procedure specified in full below, item 4.
  - [x] **Never-ticked control case**: on a robot with a genuinely
        healthy, connected brick that nothing has ticked yet, confirm
        `STATUS` shows `cyc=0 connL=0 connR=0 i2cf=0 ready=0` — the same
        shape as the boot-priming case above at the instant before any
        tick — demonstrating why `cyc=` (not `ready`/`connL`/`i2cf`
        alone) is the correct disambiguator, per SUC-002. — Procedure
        specified in full below, item 2. The general shape of this
        shown-STATUS line (`ready=0 connL=0 connR=0 i2cf=0`) was already
        directly observed on tovez, 2026-08-24 (see the issue file's own
        "CORRECTION" section); only the `cyc=0` half is new and
        unverified on the wire, since `cyc` did not exist as a STATUS
        field at that session — it ships in this sprint's ticket 003.
  - [ ] Record actual wall-clock timing observed for the boot-priming
        path with a disconnected brick (how long until the boot banner/
        first reply appears) — this is the direct field measurement
        ticket 004's platform-timeout research could not make without
        hardware, and closes that ticket's own open question either way.
        — **Left unchecked.** This item asks for an actually-observed
        number, not a procedure describing how to get one; no bench
        session was run as part of closing this ticket. The checklist's
        item 3 below instructs the operator to time it with a
        stopwatch/timestamp against the boot banner when the session
        runs, and to record the result here or in the issue file.
- [x] The checklist references ticket 004's findings (whatever guard, if
      any, shipped) so the bench operator knows what behavior to expect
      versus what remains unguarded. — See "What ticket 004 shipped, and
      what it does not settle" below; every checklist item cross-refers
      it where relevant.
- [ ] Results are recorded back into
      `unpowered-nezha-brick-wedges-program-at-boot.md` (or a superseding
      bench-notes update) once actually run — this ticket's own
      completion is the checklist existing and being ready to execute,
      not the bench run itself (see `completes_issue: false` above). —
      **Left unchecked.** No bench session was run as part of closing
      this ticket; per `completes_issue: false`, the issue stays open
      until a stakeholder runs the checklist below and records the
      outcome there.

## Implementation Plan

**Approach.** Documentation only — a precise, executable checklist, not
prose description. Depends on tickets 003 (the `cyc=` field the
checklist relies on) and 004 (whatever guard or finding it produces)
so the checklist reflects the sprint's actual shipped state rather than
its planned one.

**Files to create/modify:** a checklist section in this ticket, or a
linked file under this sprint's directory if the stakeholder prefers a
standalone bench-notes document (matching the existing convention of
`clasi/sprints/.../issues/*.md` bench-note files used elsewhere in this
project's sprint history).

**C++11 gate coverage.** N/A — no code changes.

**Testing plan.** N/A — bench-only by construction; see this sprint's
own Test Strategy section for why (`NezhaMotorPort` has no host-portable
seam for a truly non-returning I2C call).

**Documentation updates.** This ticket's own checklist; the sprint's
design overlay records the sprint-level Success Criteria this checklist
exists to satisfy.

## What ticket 004 shipped, and what it does not settle

Ticket 004's investigation (`clasi/sprints/010-.../tickets/done/004-....md`)
changed this issue's premise. Read this before running the checklist
below — it changes what a bench operator should expect to observe, not
just how to interpret it.

- **The platform bounds the wait; it is not infinite.** This project's
  real build resolves `codal-microbit-v2` v0.3.5
  (`.tmp/deploy-head/built/codal.json`), whose `target-locked.json` pins
  `codal-nrf52` at commit `1fbb7240` (2025-05-21) — confirmed (via `gh
  api` ancestry) to be a strict descendant of both upstream I2C fixes
  ("NRF52I2C: Introduce transaction timeout", 2021-06-30, and
  "NRF52I2C::waitForStop: recover from hang", 2022). Reading
  `NRF52I2C.cpp::waitForStop()` at that pinned commit:
  `NRF52I2C_TIMEOUT10US` (1,000,000 × ~10 µs ≈ **10 s**) plus
  `NRF52I2C_TIMEOUT10US_STOP` (~1 s) bounds one stuck I2C call to **~11 s
  worst case**, not an unbounded hang. So the documented "wedges the
  whole program indefinitely" premise is **very likely false** on this
  platform — the checklist's job is not to reproduce the original wedge,
  it is to **measure what actually happens** and how long it takes.
- **Two possible timeout paths, and code inspection cannot say which
  one a real dead brick hits.** `NRF_TWIM_EVENT_ERROR` is checked on
  *every* spin iteration of `waitForStop()`, not just after the ~10 s
  ceiling — so a bus with nothing answering (a floating/NACKing line,
  arguably the more literal reading of "unpowered brick") plausibly
  resolves through that fast error path, effectively immediately. The
  ~10 s silent-timeout branch is what a *partially-engaged, mid-
  transaction* hang (a device that ACKs then stops, e.g. holding a clock
  line) would need. **This is the one thing this checklist exists to
  settle that no further reading of the code can** — item 3/4 below ask
  the operator to time it and note which behavior (near-instant vs.
  ~10-11 s) was observed.
- **`begin()` now short-circuits on the first hard failure.**
  `NezhaMotorPort::begin()` (`src/nezha_port.cpp:90-101`) used to try all
  3 priming samples regardless of an earlier failure — up to 3 sequential
  ~11 s stalls per motor, 6 across both wheels in
  `DifferentialDrive::begin()` (`src/diffdrive.cpp:264-266`), ~66 s
  worst case. It now `break`s out of the loop on the first hard
  `writeFrame()`/`readEncoderRaw()` failure, capping one motor to a
  single attempt (~11-22 s including the encoder-settle sleep) and both
  wheels to roughly a third of the old worst case. **Trade-off, stated
  plainly by ticket 004 and re-stated here**: this also removes the old
  loop's tolerance for a single transient mid-sequence blip on an
  otherwise-healthy bus (e.g. sample 1 NACKs on a cold-boot brownout but
  samples 2-3 would have succeeded) — previously that still produced a
  good median-of-2 boot; now that motor reports `connected()==false` for
  the rest of the session (nothing re-attempts `begin()`'s priming after
  boot). There is no bench evidence either way yet. **Checklist item 5
  below exists specifically to watch a healthy brick's cold-boot connect
  for this regression** — it is not part of the original issue at all.
- **The steady-state per-tick path (`requestSample()`/`tick()` →
  `collect()`, `src/diffdrive.cpp:495-511`) was not changed** — it is
  already one write + one read per ~24 ms tick with no retry loop to
  short-circuit, so it inherits the same ~11 s-per-call platform bound
  with no additional guard. This is exactly why the mid-session check
  (item 4 below) matters as much as the boot check: a brick that dies
  mid-drive hits this unmodified path, not `begin()`'s.

## Bench Checklist (stakeholder handoff)

Everything below is to be run **at the bench, on real hardware, by the
stakeholder** — none of it was performed as part of closing this
ticket. See "No flashing and no hardware validation were performed" at
the end of this section. Test robot: **vevov** (this project's primary
test robot); **tovez** is also available and stakeholder-authorised and
has a working OTOS, so either may be used — record which one was
actually used when the checklist is run.

### 0. Tick-first rule — read this before diagnosing any robot as faulty

**This is the single most important instruction on this checklist.**
`ready`/`connL`/`connR`/`i2cf` are only ever written from inside
`DifferentialDrive::step()`/`collect()` (`src/diffdrive.cpp:452`,
`:510`, `:783`, `:816`) — which run only when something ticks the
kernel (a live `while (tickDrive())` loop, or a wire motion verb that
arms a real obligation). **A robot nothing has ticked yet reports
`ready=0 connL=0 connR=0 i2cf=0` — the identical line a genuinely
unreachable brick reports.** This is not hypothetical: it is exactly
what happened on tovez, 2026-08-24 (see the issue file's "Bench
observation" section) — a healthy robot was misdiagnosed as dead
because nothing had ticked it yet.

Before drawing any conclusion from `STATUS` on a silent or
unresponsive-seeming robot, **first issue a command that ticks the
kernel unconditionally** — the block-path form, e.g. `RUN:straight:15`
(the legacy colon-form RUN bridge; confirmed live this session:
`RUN:straight:60` runs a real `while (tickDrive())` loop and reliably
ticks the kernel, while the v6 `RUN` verb with no colon is a deliberate
stub that always answers `err unknown` — `WireAdapter::onRun()`,
`src/wire_adapter.cpp:806-815`, holds no registration table by design).
A wire-native motion verb (e.g. `WHEELS_X`) can accept and stage a
command without necessarily ticking the kernel promptly — the
block-path colon form is the reliable "tick it now" instrument for this
checklist. Then re-read `STATUS` and apply items 1-5 below.

**Why `i2cf=0` is also not evidence of health on its own**: fault
counting lives in `DifferentialDrive::step()`'s `collect()` call
(`src/diffdrive.cpp:510`), which — like `ready`/`connL`/`connR` — only
runs once the kernel has ticked. A never-ticked robot and a genuinely
dead brick both report `i2cf=0`. `cyc=` (below) is the field that tells
the two apart; `i2cf` alone cannot.

### 1. Wire instruments this checklist relies on

- `STATUS` reply format (`src/wire_handler.cpp:757-768`):
  `status ready=%d active=%d connL=%d connR=%d otos=%d wedge=%d
  flags=%x i2cf=%ld cyc=%lu tlm=%s next=%lu`.
- `cyc` (`Wire::StatusFields::cyc`, `src/wire_handler.h:133-149`) is
  sourced by `WireAdapter::status()` from `diagValue(kDiagCycleCount)`
  (ordinal 16, `src/wire_adapter.cpp:187,307`) — the same source
  telemetry's `cyc` column reads (`src/wire_adapter.cpp:776`), so the
  two can never disagree. **`cyc=0` means "this kernel has never
  ticked" — every other field's 0 is meaningless, not a fault. `cyc>0`
  means the kernel is running and every other field means what it
  says.** This is the ticket 003 field this whole checklist exists to
  use.
- `i2cf` (`Wire::StatusFields::i2cf`, ordinal 8) climbs whenever a
  tick's `refreshSample()` doesn't get a fresh sample from either wheel
  (`src/diffdrive.cpp:504-511`).
- `connL`/`connR` mirror `NezhaMotorPort::connected_` for each wheel —
  `false` after `begin()` gets zero good priming reads, or after any
  `collect()`/write failure (`src/nezha_port.cpp:111`, `:229`, `:290`).

### 2. Never-ticked control case (run this FIRST, before any brick is touched)

- On a **healthy, fully connected** robot, immediately after boot,
  before issuing any drive command: send `STATUS`.
- **Expected**: `cyc=0 connL=0 connR=0 i2cf=0 ready=0` — the *exact
  same shape* the boot-priming and mid-session cases below will show
  when the brick is genuinely dead. This is the control case that
  proves `cyc=` (not `ready`/`connL`/`i2cf` alone) is the correct
  disambiguator (SUC-002).
- Then issue `RUN:straight:15` (or equivalent) to tick the kernel.
  Re-send `STATUS`. **Expected on a healthy brick**: `cyc` is now
  nonzero, `connL=1 connR=1`, `i2cf` stays low/flat, `ready=1`.
- Record the actual `cyc`/`i2cf` values observed both before and after
  the tick.

### 3. Boot-priming path (the issue's original scenario)

- Physically power down or I2C-disconnect the Nezha brick (battery off,
  or unplug the brick's data connection). Flash and boot the robot with
  the brick in this state.
- Confirm the boot banner (`device NEZHA2 robot ...`,
  `src/wire_handler.cpp:1159-1166`) still appears, and every subsequent
  v6 reply (`VER`/`ID`/`STATUS`/`GET`) is still answered — the protocol
  fiber must stay alive throughout, per ticket 004's ~11 s-bound
  finding (this is the check that directly tests whether that finding
  holds on real hardware).
- **Time it.** Note wall-clock elapsed between power-on (or the boot
  banner) and the first `STATUS` reply that reflects a completed (or
  short-circuited) priming attempt. Record whether the delay reads as
  near-instant (consistent with the fast `NRF_TWIM_EVENT_ERROR` path)
  or as a multi-second stall in the ~10-11 s range (consistent with the
  silent `waitForStop()` timeout path). **This single number is what
  closes ticket 004's own open question** — record it here or in the
  issue file regardless of which way it comes out.
- Confirm `STATUS` reports `connL=0 connR=0`.
- Issue `RUN:straight:15` (or another command that ticks the kernel).
  Confirm `cyc` advances above 0 while `i2cFaultCount`/`i2cf` climbs and
  `connL`/`connR` stay `0`.
- Confirm the motion command becomes a no-op (the robot does not move)
  rather than hanging the program — no further command should ever go
  unanswered.

### 4. Mid-session disconnection

- With the robot already ticking — a live `while (tickDrive())` loop
  running, or an in-flight wire motion obligation (e.g. an accepted
  `WHEELS_X`/`MOVE_X` with a live lease) — physically disconnect the
  brick (unplug the I2C/data connection; do not just cut drive power if
  that would also kill the microbit itself).
- Confirm the same signature as item 3: `connL`/`connR` drop to `0`,
  `i2cFaultCount`/`i2cf` climbs, `cyc` keeps advancing (the kernel is
  still ticking — this is what distinguishes "brick died mid-session"
  from "nothing is ticking"), TLM/DIAG/protocol all stay alive, and any
  further motion becomes ineffective rather than the program hanging.
- This exercises the **unmodified** steady-state path
  (`src/diffdrive.cpp:495-511`) — ticket 004 made no code change here,
  so this check is the only evidence (host or bench) that the platform
  bound actually holds on this path too, not just at boot.
- Time this one too, if practical (stopwatch from disconnect to the
  first `STATUS`/`TLM` frame that reflects the drop) — it exercises a
  different call path than item 3 and may show a different delay.

### 5. Regression check: healthy-brick cold-boot connect

- On a robot with a **known-healthy, connected** brick, cold-boot it
  several times in a row (aim for at least 5-10 boots) and confirm
  `connL=1 connR=1` after the first tick, every time.
- This exists specifically because of ticket 004's own honestly-stated
  trade-off: the `begin()` short-circuit (item above, "What ticket 004
  shipped") removes the old loop's tolerance for a single transient
  mid-sequence blip. If a healthy brick occasionally shows
  `connL=0`/`connR=0` after boot where it did not before this sprint,
  that is a real regression to report — not expected, but not proven
  absent either, per ticket 004's own text ("No bench evidence either
  way yet").

### 6. Practical bench facts (useful context, not a checklist item)

- The v6 `RUN` verb (no colon, e.g. wire-native `RUN gap`) is a
  deliberate stub that always answers `err unknown`
  (`WireAdapter::onRun()`, `src/wire_adapter.cpp:806-815`) — only the
  legacy `RUN:name:arg` colon form (the MessageBus bridge,
  `Protocol::handleRun()`, `src/protocol.cpp:127`) reaches whatever test
  program is currently flashed. Confirmed live this session against a
  bench robot: `RUN:gap` → `GAP:0`, `RUN:arm`, `RUN:probe` →
  `OPROBE:95:1`, `RUN:straight:60` (drives), `RUN:tour:wheels`. These
  handler names come from whatever `.ts` test program is flashed at the
  time — they are not part of this repo's own committed firmware
  surface.
- `probe(n)` (`src/main.ts:1049`, `src/shims.cpp:1078`,
  `return diagValue(what);`) is a block/TS-level function, not a wire
  verb — it needs an on-device script to read; `STATUS`/`GET` are the
  actual wire-readable surface this checklist uses throughout.
- The square tour's OTOS corner-fix behavior is currently a stale cache
  (`tour-corner-fixes-are-stale-cache.md`, sprint 011) and reports a
  fabricated near-zero closure — **do not use tour closure as evidence
  of anything in this checklist.** Use direct `STATUS`/`TLM` reads only.

### No flashing and no hardware validation were performed

This ticket produced this written checklist only. **No flashing to any
microbit, and no hardware/bench validation of any kind — no
disconnected brick, no boot-priming timing, no mid-session
disconnection, no cold-boot regression sweep — was performed as part of
completing this ticket.** Every number and behavior described as
"expected" above is a prediction grounded in ticket 003/004's code-level
findings, not a bench-observed result. The one exception is the "RUN
grammar" bench facts in item 6, which were confirmed live against a
bench robot this session (not by this ticket's own execution, and
independent of the dead-brick scenario itself) and are recorded here
only as background context useful to whoever runs this checklist. Per
this ticket's own `completes_issue: false`, the actual dead-brick bench
checks (items 2-5 above) are the stakeholder's own follow-up; when that
session happens, its outcomes — including the wall-clock timing numbers
this checklist explicitly asks for — should be recorded back into
`unpowered-nezha-brick-wedges-program-at-boot.md`.

## Baseline

`uv run pytest -q` (host suite): **543 passed**, re-run and confirmed
after this ticket's edits — unchanged, as expected for a
documentation-only pass touching no `.cpp`/`.h`/`.ts` file.

## C++11 Gate Coverage

Not applicable — this ticket makes no code change. `nezha_port.{h,cpp}`
already sit outside the C++11 syntax gate's four-file coverage (per
ticket 004's own "C++11 gate coverage" note), and this ticket touches no
source file at all.

## Testing

- **Existing tests to run**: none (documentation-only; no source file
  changed).
- **New tests to write**: none (a checklist, not automated test code).
- **Verification command**: `uv run pytest -q`, run in the foreground —
  543 passed, same as the baseline before this ticket's edits.
