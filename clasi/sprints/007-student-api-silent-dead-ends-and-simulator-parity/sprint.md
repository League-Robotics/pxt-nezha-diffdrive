---
id: '007'
title: 'Student API: silent dead-ends and simulator parity'
status: ticketing
branch: sprint/007-student-api-silent-dead-ends-and-simulator-parity
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
- SUC-005
- SUC-006
issues:
- stall-latch-invisible-dead-end.md
- drivetick-contract-broken-idiom.md
- cruise-zero-sentinel-full-duty-lunge.md
- simulator-parity-turn-rate-and-estop.md
- rotational-slip-not-tunable.md
- runargcount-guard-and-shim-minors.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 007: Student API: silent dead-ends and simulator parity

## Goals

Theme: **when the robot won't move, the student can find out why; the
simulator tells the truth; documented idioms work.**

- Every silent refusal becomes observable. The stall latch gets a clear
  path (block + wire verb) and a readback (STATUS bit + DIAG ordinal +
  student-visible reporter) — framed, where it doesn't blow the sprint's
  scope, against the review's broader design note: e-stop, stall latch,
  watchdog, and lease expiry are four invisible "robot is off" states that
  a single unified "why won't it move" surface could retire as one class.
  At minimum the stall latch itself stops being invisible; the unified
  surface is a stretch goal, not a gate.
- The `driveTick()` continuous-drive contract is *decided*, not
  patched around: either it returns "keep ticking" while a velocity
  command is live, or a separate documented idiom (e.g. `driveHold()`)
  replaces the broken one. Code, all four doc sites (README ×2,
  specification.md §4.2, usecases.md UC-002), and a regression host test
  move together so they cannot diverge silently again.
- The wire's `cruise == 0` "configured default" sentinel resolves to a
  safe speed instead of the full-duty ~875 mm/s rail, and becomes an
  actual config field (`default_cruise`) instead of an unconfigurable
  constant.
- The browser simulator matches hardware on the two axes students
  actually feel: turn rate (kill the stray `/10` in `set wheel speeds`)
  and e-stop latching (the sim currently refuses nothing post-e-stop,
  making UC-011's "forgot to clear emergency stop" trap invisible exactly
  where students develop).
- `rotationalSlip` becomes a calibratable field (Setup group /
  `ConfigField` / `MotionEngine` setter with the same `setGeometry`-style
  validation) instead of a hard-coded, recompile-only constant, so a
  non-vevov chassis can be turn-calibrated without touching source. The
  load-bearing derivation comment for 0.952 moves with the field.
- The `runArgCount` null-guard and its batched one-to-five-line Minors
  land together as one low-risk cleanup pass.

## Problem

The 2026-08-23 code review's second major theme (after goTo geometry,
which sprint 006 owns) is that the student-facing API is full of silent
dead ends: a robot can stop responding to a program for five different
reasons, and none of them are visible to the student or the host. On top
of that, one of the four documented ways to drive the robot (the
`while (driveTick())` idiom) doesn't work as documented, the wire's "use
the default speed" sentinel instead commands maximum speed, and the
simulator disagrees with hardware on both turn rate and e-stop behavior —
so a student's simulator-tuned program does not transfer to the real
robot. `rotationalSlip` being unconfigurable is the same class of problem
one level down: a documented calibration path (`set track width`) exists
but is explicitly the wrong knob, and the right knob doesn't exist yet.

## Solution

Treat these as one sprint because they share a boundary: everything here
is student-observable API surface (blocks, wire verbs a student's program
or a host test can hit, docs, and the simulator), not transport plumbing
(sprints 004/005) or motion-geometry math (sprint 006). Detail planning
will size each issue individually — the stall-latch/driveTick/cruise
work touches `motion_engine`/`shims.cpp`/wire decode together and may
warrant more than a "compact" architecture treatment; the slip setter and
the Minors batch are likely compact or trivial on their own.

## Success Criteria

- A student (or host) can discover, after a stall latch trips, that it
  tripped and how to clear it — without a power cycle.
- The documented `driveTick()` continuous-drive idiom, as written in the
  README/spec/usecases, actually keeps the robot moving; a host test
  proves it.
- Sending `cruise 0` (or the equivalent wire field) on any of the four
  motion verbs produces a safe, documented speed — never the duty
  ceiling.
- Simulator turns match hardware turns for the same `set wheel speeds`
  call, and a simulated `emergency stop` refuses further motion until
  cleared, matching hardware's two-layer refusal.
- `rotationalSlip` has a setter reachable from a block or `ConfigField`,
  validated like other geometry fields, with its derivation comment
  intact.
- `runArgCount` no longer panics on an unguarded pre-RUN call, and the
  batched Minors (dead `microphone` dep, tsconfig gap, dead `maxNudges`,
  stale `goToWorld` JSDoc, spliced DIAG case 25, float→int cast UB at the
  wire boundary, under-sized verb tables) are resolved.

## Scope

### In Scope

- `src/main.ts` — block-level surface for stall clear/readback, the
  `driveTick()`/continuous-drive contract, the two simulator parity
  fixes (turn-rate `/10`, e-stop latch), the `runArgCount` guard, and the
  batched Minors that live in this file (dead `maxNudges`, stale
  `goToWorld` JSDoc, dead `microphone` dep in `pxt.json`, tsconfig gap).
- `src/shims.cpp` — wire-verb-facing surface for stall clear/readback and
  for the cruise==0 sentinel resolution; DIAG case-25 reordering.
- `src/diffdrive.*` / `motion_engine.h` — the stall latch's clear/readback
  plumbing, and the `rotationalSlip` setter (with its derivation comment
  carried along).
- `src/wire_adapter.cpp` — cruise==0 sentinel resolution, `default_cruise`
  config field, float→int cast clamp at the wire boundary, verb-table
  sizing (WIRE-09).
- Docs — README (both `driveTick()` examples), `specification.md` §4.2
  (driveTick contract) and §5 (simulator gaps, currently omits e-stop),
  `usecases.md` UC-002 (driveTick idiom) and UC-013 (chassis calibration,
  to include `rotationalSlip`).
- `tests/host` — regression tests for the driveTick idiom, the cruise
  sentinel across all four motion verbs, stall latch clear+readback, and
  the `rotationalSlip` setter.

### Out of Scope

- `goTo` geometry, pivot-split behavior, arrival tolerance, OTOS heading
  wrap, and odometry chord integration — sprint 006 (motion correctness).
- Radio/serial transport work (RX capacity, TX serialization, RX ring
  sizing, wire version drift) — sprints 004/005.
- Bench-tool/camera link-layer consolidation (stale venv, copied `Cam`
  scaffolds, numeric `RUN:<n>` vocabulary) and the comment-cleanup work
  order — separate proposed issues/sprints, unrelated to the student API
  surface this sprint targets.
- Brick-reset odometry teleport, cross-fiber stop/settle race — filed as
  their own issues, not claimed here.

## Test Strategy

(Sized in Detail Mode, per issue. Expect host-test additions in
`tests/host` for: the driveTick continuous-drive idiom end-to-end, the
cruise==0 sentinel on all four motion verbs, stall latch
clear-then-readback, and the `rotationalSlip` setter's validation. Sim
parity fixes are checked by comparing sim math against the hardware
conversion it's meant to mirror, not by a new test harness.)

## Architecture

**Sizing: Substantial.** Five modules are touched with real behavioral
effect (`main.ts`, `shims.cpp`, `motion_engine.h`, `wire_adapter.cpp/h`,
`wire_handler.h/cpp`), plus a genuine wire-protocol data-model change:
three new named fields join the `ConfigField`/`kFields` table
(`default_cruise`, `rotational_slip`, `stall_clear`), each independently
GET/SET-able and each individually host-tested. That crosses the
compact tier's "no data-model change" line on its own.

This project has opted into the persistent per-subsystem design-doc
overlay model (`design_docs: enabled`), so the full architecture
write-up — the 7-step methodology, module table, Design Rationale,
Migration Concerns, and Open Questions — lives in this sprint's
`design/` overlay, not here: see
[`design/DESIGN.md`](design/DESIGN.md) §13 "Sprint 007 — architecture
diagram and change summary" (the edited copy; inline `Sprint 007:`
annotations also land in §3, §4, §5, §9, and §10 where the changed
modules already have sections). `docs/design/design.md` (the system
doc) was evaluated and **not** seeded — the Geometry doctrine section
it already states (`rotationalSlip` is where all rotational correction
lives, never `trackWidth`) is unchanged by this sprint; this sprint
makes that already-correct doctrine's field reachable, it does not
revise the doctrine.

**Correction found during self-review:** `specification.md` and
`usecases.md` were initially seeded into this overlay alongside
`DESIGN.md`, but `validate_design` correctly rejected both —
`sources:` in `.clasi/config.yaml` is `[src, tools, tests, test]`, and
the canonical doc set this project's overlay/apply machinery
recognizes is `docs/design/design.md` plus one `DESIGN.md` per
declared source root; `specification.md`/`usecases.md` (and
`overview.md`) are pre-opt-in legacy docs at `docs/design/` that
`validate_design` explicitly flags as "not a known canonical design
doc" when seeded. They have been removed from this overlay
(`design/_sources.json` now lists only `DESIGN.md`). The edits this
sprint needs there (specification.md §2/§4.2/§4.8/§5; usecases.md
UC-002/UC-011/UC-012/UC-013/UC-015/UC-016) are instead written directly
into the relevant tickets' Implementation Plans below, to be applied by
the programmer agent during normal ticket execution on the sprint
branch — the same treatment this sprint already gives `README.md`,
`tsconfig.json`, and `pxt.json`, none of which are canonical-doc-set
members either.

**Known tooling gap, not a content defect:** `validate_design` also
reports `design/DESIGN.md has no corresponding diff file` — this
project's installed CLASI build exposes no `generate_diffs` MCP tool
or CLI subcommand (`clasi design validate`, `clasi tool`, `clasi
sprint`, and the `clasi.design.overlay` module were all checked; none
exposes it). The overlay's actual *content* — what `close_sprint`
applies verbatim — is complete; only the reviewer-convenience
`.diff.md` sibling `architecture-review` normally reads could not be
generated. This review instead diffed `design/DESIGN.md` directly
against its seed commit (`git diff <seed-commit>`) as a substitute —
the same mechanism the stakeholder's own review path already uses.
Flagging for the team-lead/stakeholder: either add the missing tool,
or treat `git diff` against the seed commit as the standing substitute
for `.diff.md` generation project-wide.

**Summary for readers of this file alone** (see the overlay for full
detail): the stall latch (already correctly detected and readable
inside the kernel's `Output`) gets its first caller for
`clearStallLatch()` — a dedicated block plus a SET-able `stall_clear`
wire field — and a named, documented readback (`isStalled()` block;
`probe(2)`'s doc comment gains its ordinal's name). `tickDrive()`
(`shims.cpp`) and its simulator mirror `_tickDrive()` (`main.ts`) start
returning "does anything still look commanded" — reusing
`commandLooksActive()`, a helper sprint 006 already proved correct in
production for the starvation watchdog — instead of raw move-engine
state, which is what makes the documented `while (driveTick())`
continuous-drive idiom (README ×2, spec §4.2, UC-002) actually work;
no doc-site prose needs rewriting, only a cross-reference to the new
regression test that now pins the contract. The wire's `cruise == 0`
"configured default" sentinel stops deriving from `fullDutyVelocity`
(the kernel's unrelated "0 = uncalibrated, refuse" sentinel) and reads
a new, independently configured `default_cruise` field instead (seeded
150 mm/s, matching the block layer's own `defaultSpeed`) — the four
motion verbs' existing refusal-on-`<=0` logic is untouched. The browser
simulator's `set wheel speeds` drops a stray `/10` (10× too slow) and
gains a `simEstopped` latch so `emergency stop` now refuses further
motion in the browser exactly as it does on hardware (UC-011's "forgot
to clear" trap is no longer invisible where students develop).
`MotionEngine::setRotationalSlip()` joins the two existing geometry
setters, reachable through the existing generic `set config` block plus
a new `rotational_slip` wire field. Six independent, low-risk hygiene
items round out the sprint: a null-guard for `runArgCount()`, a
derived-size `kCommandTable` (closing an under-initialization hazard),
a reordered `diagValue()` switch case, two clamped wire-boundary casts,
a dead-code/JSDoc/build-config cleanup batch, and a documented (not
deleted) rationale for the `microphone` `pxt.json` dependency. The
vendored kernel (`diffdrive.{h,cpp}`) is untouched throughout — every
kernel primitive this sprint needs already existed and was already
correct; this is a missing-caller and wrong-field-reused problem above
the kernel, not a kernel change.

**Known behavior change, not a risk:** a bench host or Python tool that
has learned to send `cruise 0` *because* it wants full-duty speed will
get ~150 mm/s instead once ticket 003 lands — the entire point of issue
3. No in-tree tool does this today (not checked exhaustively — flagged
in the overlay's Migration Concerns for whoever executes that ticket to
grep `tools/` before merging).

## Use Cases

Sized to the substantial tier: full narrative treatment for the two
use cases students most directly feel (SUC-001, SUC-002), proportional
treatment for the rest. All six map onto existing project use cases
(`docs/design/usecases.md`), updating them in place rather than adding
new UC numbers — none of this sprint's work is a new capability the
use-case doc doesn't already describe (or misdescribe); it corrects
existing UCs' error flows and postconditions to match fixed behavior.

### SUC-001: Student discovers a stall latch and clears it without a power cycle

**Actor**: Student/Teacher. **Maps to**: UC-002 (error flow), UC-012
(sibling clear operation).

**Main flow**: A student's robot pushes into an obstacle for over
500 ms while a Drive/Move command is in effect. The kernel's existing
stall detector latches (`stallHalted_ = true`, unchanged kernel
behavior). The student's program keeps running — no exception, no
crash — but the robot no longer responds to any Drive/Move block.
The student checks `is stalled` (new block): it reports `true`. The
student (or a recovery routine in their own program) places
`clear stall latch` (new block, advanced group). The latch clears; the
very next Drive/Move command takes effect normally.

**Postconditions**: The robot is no longer latched; STATUS flags bit 2,
DIAG ordinal 2, and the new `stall_clear` wire field's GET all agree the
latch is clear.

**Error flows**: Calling `clear stall latch` when nothing is latched:
no-op (mirrors `clearEmergencyStop()`'s own precedent). Calling
`is stalled` in the simulator: always reports `false` — the simulator
has no stall model (documented, not a defect).

**Updates**: UC-002's error flows bullet on motor stall changes from
"kernel self-halts... until `clearStallLatch` (not currently exposed as
a block — see gap noted in the report to team-lead)" to describe the
new block + wire field. UC-012 gains a sentence pointing at the now-
available, separate stall-latch clear path instead of only noting the
gap.

### SUC-002: The documented continuous-drive idiom actually keeps the robot moving

**Actor**: Student/Teacher. **Maps to**: UC-002 (main flow, step 4).

**Main flow**: A student places `set wheel speeds`/`drive ... turning
...` followed by `while (driveTick())`, exactly as the README, spec
§4.2, and UC-002 already instruct. Under the fixed contract, each
`driveTick()` call returns `true` for as long as the wheels are
actually being commanded (move-engine active, or nonzero applied duty)
— so the loop body keeps running once per ~24 ms cycle, matching every
doc site's existing prose. The robot keeps driving until the student's
own loop body calls `stop()`/`emergencyStop()`, or nothing ticks the
loop for ~150 ms (starvation watchdog, unchanged, non-latching).

**Postconditions**: identical to UC-002's existing postconditions —
this SUC changes what is *true*, not what is *documented*.

**Error flows**: A position-mode move (`move()`/`goTo()`, which also
loop on `while (_tickDrive())` internally) still ends the loop on the
same tick the move completes — `commandLooksActive()` reads
`appliedDuty == 0` by then because the settle loop (sprint 006,
unchanged) already drove it there. No behavior change for blocking
moves; this SUC is exclusively about the continuous-mode case.

**Updates**: No doc-site content changes (README ×2, spec §4.2, UC-002
step 4 already describe this correctly) — each gains a one-line
cross-reference to the new regression test that now pins the contract,
per the sprint's requirement that all four sites "move together."

### SUC-003: A wire host's `cruise 0` produces a safe, documented speed

**Actor**: A bench host or Python tool issuing raw wire commands (not
a student's blocks — the block layer has its own independent
`defaultSpeed` and never emits a literal wire `0`).

**Main flow**: A host sends `WHEELS_X 500 500 0 5000#7` (or the
equivalent on `MOVE_X`/`GO_TO_R`/`GO_TO_W`). The adapter resolves `0`
to the new `default_cruise` field (seeded 150 mm/s) instead of
`fullDutyVelocity`'s ~875 mm/s. A host that wants a different default
can `SET default_cruise <value>` first.

**Postconditions**: the commanded move runs at the configured default,
not the duty ceiling. `GET default_cruise` reports the configured
value on any of the four verbs' behalf.

**Error flows**: `default_cruise` set to `0` (or never configured):
the existing refusal-on-`<=0` logic in all four verb handlers
(unchanged) refuses with `kRange`, exactly as it does today when
`fullDutyVelocity` was the unconfigured source — no new refusal path
was written, the existing one just now guards a different field.

### SUC-004: Simulator turn rate and e-stop behavior match hardware

**Actor**: Student/Teacher developing in the browser simulator
(UC-016's actor).

**Main flow**: A student tunes `set wheel speeds` in the simulator; the
resulting turn rate now matches the `/115` mm-track formula
`_driveTwist`'s sim body already used correctly, instead of being 10×
too slow. Separately, a student calls `emergency stop` in the
simulator; a subsequent `set wheel speeds`/`drive`/`start move` call is
now silently refused (mirroring hardware's two-layer refusal) until
`clear emergency stop` — the UC-011 "forgot to clear" trap is now
reproducible in the browser, where students actually develop.

**Postconditions**: simulator behavior for both axes matches the
hardware conversion it is meant to mirror.

**Updates**: `specification.md` §5 gains the e-stop-latch bullet it
currently omits, and its `/115` formula description is unchanged
(it was already correct — only the code was wrong).

### SUC-005: A non-reference chassis's turn slip is calibratable without recompiling

**Actor**: Teacher/builder setting up a non-reference kit (UC-013's
actor).

**Main flow**: A teacher measures rotational slip against camera truth
for their chassis (the doctrine `docs/design/design.md`'s Geometry
doctrine already describes) and places
`set config rotational slip to <value>` (generic escape hatch, `>0`
validated, silently ignored otherwise — matching `setGeometry()`'s own
error-flow precedent).

**Postconditions**: `MotionEngine::effectiveTrackWidth()` reflects the
new slip value on every subsequent move/turn.

**Updates**: UC-013 gains a third calibration step (rotational slip)
alongside the existing track-width/wheel-calibration steps, with the
same "value <= 0 silently ignored" error flow.

### SUC-006: Boot-safety guard and shim/build hygiene

**Actor**: Any program calling `runArgCount()` before the first RUN
event; maintainers reading the affected files.

**Main flow**: `runArgCount()` mirrors `runArgText()`'s existing guard
(`if (!runParts) return 0`) instead of dereferencing an uninitialized
array. The seven batched Minors (dead `microphone` rationale
documented, `tsconfig.json` gains `serial.ts`, dead `maxNudges`
deleted, `goToWorld`'s JSDoc corrected, DIAG case-25 reordered, two
wire-boundary casts clamped, `kCommandTable`'s size derived) are each
independent, no-behavior-visible-to-students fixes.

**Postconditions**: no observable change to any documented block/wire
behavior; the boot-panic class of failure (measured on vevov,
2026-08-21) is closed for `runArgCount()` specifically.

**Updates**: none to `usecases.md` — none of these are use-case-level
behavior; `specification.md` §2 gains the `microphone` rationale
sentence (Design Rationale above).

## GitHub Issues

None — this sprint claims six local CLASI issues (`clasi/issues/`,
now moved to this sprint's `issues/` directory), sourced from the
2026-08-23 code review. No GitHub issue is filed for this sprint.

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [x] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [x] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Issue | Depends On |
|---|-------|-------|------------|
| 001 | Stall latch: clear path and readback (block, wire SET-action field, docs) | `stall-latch-invisible-dead-end.md` | — |
| 002 | driveTick() continuous-drive contract: return commandLooksActive, pin with a regression test | `drivetick-contract-broken-idiom.md` | — |
| 003 | Wire cruise==0 sentinel: split default_cruise from fullDutyVelocity (config field + test-double update) | `cruise-zero-sentinel-full-duty-lunge.md` | — |
| 004 | Simulator parity: fix set-wheel-speeds turn-rate divisor and latch emergency stop | `simulator-parity-turn-rate-and-estop.md` | 002 |
| 005 | rotationalSlip setter: MotionEngine + ConfigField/wire field, derivation comment intact | `rotational-slip-not-tunable.md` | — |
| 006 | runArgCount null guard + main.ts/build-config Minors (dead code, JSDoc, tsconfig, pxt.json) | `runargcount-guard-and-shim-minors.md` | — |
| 007 | Wire/shims Minors: DIAG case-25 reorder, wire-boundary cast clamps, derived-size kCommandTable | `runargcount-guard-and-shim-minors.md` | — |
| 008 | Bench-handoff checklist: stall latch, driveTick idiom, cruise sentinel, simulator/hardware parity | (spans 001-004) | 001, 002, 003, 004 |

Tickets execute serially in the order listed. 004 depends on 002
because both touch `main.ts`'s simulator state in the same handful of
functions — landing 002's `_tickDrive()` contract fix first means 004's
`simEstopped` gate composes against the already-fixed tick contract.
006/007 split the same Minors issue by file cluster (TS-side vs.
C++/wire-side) and testing-evidence profile, not by dependency — either
could run first; they are listed adjacently for narrative continuity.
008 is a hardware-only checklist that does not block `close_sprint`
(see its own ticket) — listed last because it depends on 001-004's
code landing first, not because the sprint's own completion waits on
it.

## Issues Claimed

All filed under `clasi/issues/`, from the 2026-08-23 code review
(`docs/code-review/2026-08-23/review.md`). Not yet linked via
`link_sprint_issues` — that step is left to whoever runs Detail Mode on
this sprint.

| Issue file | Priority | Review IDs | Covers |
|---|---|---|---|
| `stall-latch-invisible-dead-end.md` | High | R-01 | No clear path or readback for the stall latch; includes the review's "unify the invisible robot-is-off states" design note |
| `drivetick-contract-broken-idiom.md` | High | R-10 | Documented `while (driveTick())` idiom stops the robot in ~150 ms; every doc site prescribes it |
| `cruise-zero-sentinel-full-duty-lunge.md` | High | R-11 | Wire `cruise == 0` resolves to full-duty ~875 mm/s instead of a safe default |
| `simulator-parity-turn-rate-and-estop.md` | Med | R-12, R-13 | Simulator `/10` turn-rate bug; simulator never latches e-stop |
| `rotational-slip-not-tunable.md` | Low | R-14 | `rotationalSlip` hard-coded 0.952, no setter on any surface |
| `runargcount-guard-and-shim-minors.md` | Low | R-15 + Minors | `runArgCount` null-guard one-liner, batched with small shim/build Minors |

## Ordering Rationale

This sprint is the third track in the post-review arc, after:

- **004** (`Radio full v6 transport + telemetry frame`, firmware) and
  **005** (`Retrofit bench tooling onto the v6 telemetry stream`) — the
  transport/telemetry track, already executing/roadmapped.
- **006** (`Motion correctness: goTo geometry and odometry truth`) — the
  motion-geometry track, just roadmapped.

007 is sequenced *after* 006 specifically (not just "later in the
backlog") because both sprints touch `motion_engine.h`/`shims.cpp`:
006 rewrites the `goTo` arc-encoding and pivot-split logic there, and 007
adds the stall-latch clear/readback surface and the `driveTick`/cruise-
sentinel contract in the same files. Landing 006's geometry fix first
avoids two detail-planned sprints editing the same motion-engine methods
concurrently on divergent branches. Within 007 itself, no further
internal ordering is fixed yet — that's a Detail Mode ticketing decision
— but the natural dependency shape is: stall-latch surface and
driveTick-contract and cruise-sentinel resolution first (they share
files and the "invisible dead end" theme), simulator parity next (touches
`main.ts` sim bodies, independent of the wire-side fixes), then the
`rotationalSlip` setter and the Minors/guard batch last (lowest risk,
least coupled to the rest).

007 is ordered ahead of the tooling-consolidation work implied by the
review's proposed issues #13/#14 (bench-tool venv/`Cam`-scaffold/numeric-
`RUN` cleanup) because that tooling should be built and tested against
the *fixed* stall-latch/driveTick/cruise-sentinel wire behavior, not
patched twice.
