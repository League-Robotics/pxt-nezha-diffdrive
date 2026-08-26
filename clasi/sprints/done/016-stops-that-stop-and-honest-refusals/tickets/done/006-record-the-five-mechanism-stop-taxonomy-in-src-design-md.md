---
id: '006'
title: Record the five-mechanism stop taxonomy in src/DESIGN.md
status: done
use-cases: []
depends-on:
- '001'
- '002'
- '003'
- '005'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Record the five-mechanism stop taxonomy in src/DESIGN.md

## Description

This ticket is the sprint's designated "durable output" (per the sprint's
own Architecture section and the recorded `architecture_review` gate
notes): a table in `src/DESIGN.md` naming, for each of the five stop
mechanisms, which entry points deliver it and whether it survives the
next `step()`. **Its absence is why `deliverStopNow()` ended up used
alone (without a paired `kernel.neutral()`) in `shims.cpp`'s `endMove()`
free function** — ticket 001's bug. Write this ticket last (after 001,
002, 003, 005 have all landed) so it documents the sprint's *final*
state, not a snapshot mid-sprint.

### The five mechanisms, and the distinction the table must capture

Two independent properties matter for each mechanism, and conflating them
is exactly how ticket 001's bug happened: **(a) does it deliver an
immediate, port-level zero write (tick-independent), or does it only
*stage* a command that needs a subsequent `kernel.step()` to actually
reach the motors?** and **(b) once delivered, does it persist across
further `step()` calls on its own, or can a still-live earlier command
(a long lease, a continuous-drive velocity) re-assert itself on the next
tick unless something else also holds it down?**

Read `src/core/diffdrive.h`'s public method list (`neutral()`, `estop()`,
`estopClear()`, `emergencyStopMotors()`, lines ~197-200) and
`diffdrive.cpp`'s implementations (`neutral()` ~365, `estop()` ~371,
`emergencyStopMotors()` ~379, the `effective = kModeNeutral` gates in the
per-step evaluation ~482-490) directly — do not rely on paraphrase,
including this ticket's own, without checking the source, since the
five mechanisms have real, non-obvious differences:

1. **`kernel.neutral()`** — STAGES a neutral command (`command_ = Command{};
   ++cmdSeq_`); does **not** touch the motors itself. Requires a
   subsequent `step()` to actually zero duty. Once delivered, it DOES
   persist (the command stays neutral until a new `drive()`/`driveDuty()`
   overwrites it) — but delivery itself is contingent on a `step()`
   actually running again, which is the whole reason `deliverStopNow()`
   (mechanism 2) exists as a companion. Entry points: `MotionEngine::
   endMove()` (conditionally — only when `move_.active`), `MotionEngine::
   serviceMove()`'s own move-completion branch (unconditional, on every
   natural end), `shims.cpp::stopAll()`, `shims.cpp::endMove()` free
   function (after ticket 001 — this is the fix), the starvation
   watchdog (`watchdogEntry()`).
2. **Port-level immediate zero** (`Motor::emergencyStop()`, called on both
   motors — the primitive `deliverStopNow()` in `shims.cpp` wraps, and
   the same primitive `DifferentialDrive::emergencyStopMotors()` also
   calls directly at the kernel level). Delivers NOW, tick-independent —
   but is **momentary**: it does not itself prevent the kernel's own
   still-held command (e.g. a continuous-drive velocity command with a
   long lease) from re-asserting a nonzero duty on the very next
   `step()`. This is precisely ticket 001's bug: `deliverStopNow()` alone,
   unpaired with `kernel.neutral()`, does not survive the next tick.
   Entry points: `deliverStopNow()` (`shims.cpp::stopAll()`,
   `shims.cpp::endMove()`, `MotionEngine`'s completion path via
   `updateMove()`), the starvation watchdog, and
   `DifferentialDrive::emergencyStopMotors()`'s own internal calls.
3. **`kernel.estop()`** — sets `estopLatch_ = true` ONLY. Despite its own
   header comment ("latch: zero NOW"), the implementation does **not**
   write to the motors — it only prevents the *next* `step()` from
   applying anything but neutral (`if (estopLatch_) effective =
   kModeNeutral;`) and marks `Output.estopped`. Has the exact same
   staged-not-delivered gap as `kernel.neutral()` if called alone with no
   following `step()`. In production this method is never called alone —
   `shims.cpp::estopAll()` always pairs it with `emergencyStopMotors()`
   (redundant latch-set, harmless). Once the latch IS up, though, it is
   the most robust of the five in one sense: it is re-checked on
   **every** subsequent `step()` (`diffdrive.cpp:485`), so it holds
   regardless of what `command_` contains, until `estopClear()`.
4. **`kernel.emergencyStopMotors()`** — `estopLatch_ = true` **plus** an
   immediate port-level zero on both motors (calls the same primitive as
   #2, directly). Combines the persistence of #3 with the immediacy of
   #2 — the strongest single call of the five. Entry point:
   `shims.cpp::estopAll()`, reached from the `emergency stop` block
   (`stop.ts::emergencyStop()`) and the wire's `ESTOP` verb
   (`WireAdapter::onEstop()`).
5. **Lease expiry** — not an entry point a caller invokes; a passive
   property of whatever `drive()`/`driveDuty()` call last ran; every
   `step()` re-checks `validUntil` against the kernel clock
   (`diffdrive.cpp:475-483`) and forces `effective = kModeNeutral` once
   it has passed. `MotionEngine`'s own move-engine reissues a short
   rolling 500 ms lease every tick while a move is active
   (`serviceMove()`'s own comment on this), so an abandoned move degrades
   within 500 ms of servicing stopping; a wire lease-style verb
   (`WHEELS_V`/`WHEELS_X`/`MOVE_V`) sets the lease to the FULL requested
   `duration` once, at command time — it is the actual backstop against a
   dead host for those three verbs specifically (`kWheelsVDurationCeiling`'s
   own doc comment: "a dead host cannot mean a runaway"). Like #1 and #3,
   this is a persistent condition once triggered, but — same family
   caveat — it can only take effect on a `step()` that actually runs.

### Table shape (minimum columns)

| Mechanism | Immediate or staged? | Entry point(s) | Persists across subsequent `step()`s? | Requires clearing to resume? |
|---|---|---|---|---|

One row per mechanism (five rows). Cite the actual file:line for each
entry point, not just the function name, so the table stays checkable
against the source it describes.

## Acceptance Criteria

- [x] `src/DESIGN.md` gains a new numbered top-level section (the next
      available number after the current highest — check at
      implementation time, since 014/015 may have added sections since
      this ticket was planned; do not hardcode a number from this ticket
      body) titled something like "Sprint 016 — stop taxonomy," following
      the existing convention of `## 12. Sprint 006 — ...` through
      `## 16. Sprint 013 — ...`. Landed as `## 17. Sprint 016 — stop
      taxonomy` (the next number after §16), a new top-level section
      rather than a subsection under §2 (kernel) or §9 (shim/blocks): the
      taxonomy spans all three layers (kernel, motion engine, shim/wire)
      by design — that is the whole point of the entry-point table — so
      filing it under any one layer's section would misrepresent it as
      belonging there, and the Acceptance Criteria's own precedent
      (`## 12`-`## 16`, one per-sprint change-summary section) is exactly
      this shape: a standalone, cross-cutting record of what one sprint
      changed/clarified, not owned by any single module section.
- [x] That section contains the five-row table described above, with real
      file:line citations, covering all five mechanisms and both
      properties (immediate-vs-staged, persists-vs-momentary) for each.
- [x] The table explicitly states the ticket-001 finding as its own
      callout, not buried in a cell: `deliverStopNow()` alone (mechanism
      2, unpaired) is momentary and does not survive a re-assertion from
      a still-live command — this is *why* it must always be paired with
      `kernel.neutral()` (mechanism 1) or an e-stop latch (mechanisms 3/4)
      to actually constitute a stop, and that pairing rule is now
      followed at every production entry point (post ticket 001).
- [x] `src/DESIGN.md` §10 (Open questions), the sprint-007-era entry about
      a "unified 'why won't it move' surface" (the one `sprint.md`'s Out
      of Scope references — "not attempted here; this sprint reduces the
      count of silent-refusal states from six to four, which is the down
      payment on it") gets a short update noting this table now exists as
      a documented (not yet unified/aggregated) enumeration of the
      stop/refusal states, and that the aggregation work itself remains
      future work.
- [x] Every fact in the table is checked directly against current source
      (post tickets 001/002/003/005), not copied from this ticket's own
      description without verification — this ticket's own research
      (above) is a starting point, not a substitute for reading the
      actual post-fix source.

## Implementation Plan

### Approach

1. Re-read `src/core/diffdrive.h`/`.cpp` (the five mechanisms' actual
   implementations, post any changes — though this ticket does not
   modify them), `src/motion/motion_engine.cpp` (post ticket 002's
   `estopped` addition), `src/shims.cpp` (post ticket 001's `endMove()`
   fix), and `src/comms/wire_adapter.cpp` (post ticket 003's obligation
   clearing) to confirm every entry point this ticket cites is accurate
   against the sprint's final state.
2. Find the next available top-level section number in `src/DESIGN.md`
   (`grep -n "^## " src/DESIGN.md` and take the highest + 1).
3. Write the new section: intro paragraph, the five-row table, the
   ticket-001 callout, and a one-paragraph change summary in the same
   style as the existing `## 12-16` sections (architecture diagram is
   **not** required here — this is a documentation table, not a
   structural change; the sprint's own Architecture section already
   states "compact — no structural change").
4. Update §10's relevant open-question entry per the Acceptance Criteria
   above.

### Files to modify

- `src/DESIGN.md` — new section, plus the §10 update.

### Files explicitly NOT to modify

- No source files — this ticket is documentation-only.

### Testing plan

Not applicable — no code changes. Confirm `src/DESIGN.md` still renders
sensibly (no broken table syntax) by eye; there is no automated Markdown
lint gate in this project's test suite.

- **Existing tests to run**: none required.
- **New tests to write**: none.
- **Verification command**: none (documentation-only ticket).

### Documentation updates

- `src/DESIGN.md` (the entire deliverable — see Acceptance Criteria).
