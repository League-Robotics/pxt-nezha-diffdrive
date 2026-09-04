---
id: '005'
title: execRun buffer relocation and protocol-fiber stack high-water mark
status: done
use-cases:
- SUC-005
depends-on: []
github-issue: ''
issue: code-review/protocol-fiber-stack-high-water-mark-and-execrun-buffers.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# execRun buffer relocation and protocol-fiber stack high-water mark

## Description

**This ticket has two independent parts — read the split below before
starting.** Part A is a host-completable code change a programmer agent
does in the normal way. Part B is a hardware-only measurement that the
**team-lead runs directly, in one scripted bench session** — it is not
dispatched to a programmer agent (on-robot acceptance for this kind of
single measurement is run by the team-lead, not cycled through
programmer dispatches). A programmer working this ticket should
complete Part A, mark Part B's acceptance criteria as pending
team-lead action, and hand back rather than attempting Part B.

Since sprint 028 the protocol fiber hosts the entire TS job call chain:
`run()` → `serviceOnce()` → `dispatchJob()` → `runAction0()` → handler
→ `tickDrive()` → the service hook → `serviceOnce()` again →
`drainEmitQueue()` (a 241-byte local) → `emitLineNow()` → `sendLine()`.
Every yield in that chain pays CODAL's stack-copy cost for whatever
depth it currently is — this fiber has already hard-faulted once from
large stack locals (the radio scratch-buffer overflow,
`src/DESIGN.md` §6, measured pre-sprint-004).

`WireHandler::execRun()` (`src/comms/wire_handler.cpp:1439-1475`)
declares `argv[kMaxRunArgs]` (16 pointers) and
`result[kMaxRunResultBytes]` (224 bytes) before `adapter_.onRun()` can
even return a refusal (the `if (outcome != Result::kOk) return;` check
comes after both are already live on the stack), then
`sanitized[kMaxRunResultBytes]` (224 bytes) and
`buf[kMaxLineBytes + 1]` (241 bytes) before the final write — all
committed regardless of whether the call chain above is ever deep
enough for it to matter. Confirmed still the current layout.

## Part A — buffer relocation (host-completable, do this)

- Move `sanitized` and `buf` below the `if (outcome != Result::kOk)
  return;` / `if (!hasResult) return;` early returns they already
  follow textually — C++ locals are live for their entire enclosing
  scope from declaration, not from first use, so simply reordering the
  declarations to after the returns (rather than at the top of the
  function) removes them from the pre-refusal stack footprint.
- If that alone does not sufficiently shrink the pre-refusal
  high-water mark (`argv`/`result` are still declared before the first
  return, since `onRun()` needs them as arguments), move `result` to a
  `WireHandler` member — the same pattern `emitBuf_` already
  establishes for this class — sized `kMaxRunResultBytes` as today.
  `argv` stays a local (it is genuinely needed before `onRun()` can be
  called at all, so there is no early-return point ahead of it to move
  below).
- This change is unconditional: it ships regardless of what Part B's
  measurement finds.

## Part B — stack high-water-mark measurement (hardware-only, team-lead runs this)

- Build with `DIFFDRIVE_FAULT_SPIN` and a stack-canary fill.
- Run one full `RUN:tour` plus a `RUN x #1` sent over radio mid-tour.
- Read the stack high-water mark with pyOCD.
- Record the result as MEASURED (capture artifact, board, date) per
  `.claude/rules/measurement-citations.md`, or explicitly UNVERIFIED
  with what was tried if the session cannot complete it. Either
  outcome is acceptable to close this ticket — Part A's relocation is
  not conditioned on this number, only informed by it (if margin is
  still tight, that is a finding for a future sprint, not a blocker
  here).

## Acceptance Criteria

- [x] (Part A) `sanitized`/`buf` are declared after `execRun()`'s early
      returns; `result` is a `WireHandler` member if needed to further
      shrink the pre-refusal footprint (state which was done and why).

      **What was done and why.** Read the actual source
      (`src/comms/wire_handler.cpp:1439-1477`) before changing anything,
      per this ticket's own "confirm, don't assume" instruction:
      `sanitized`/`buf` were ALREADY declared, textually, after both
      early returns (`outcome != kOk`, `!hasResult`) — no reordering was
      needed there, and none was made. That textual position alone,
      however, is not a guarantee: a flat function body (no nested
      braces) commonly gets ONE fixed-size stack frame allocated at
      entry regardless of where in the body a local is declared, so
      whether the compiler actually shrinks the pre-refusal frame from
      this alone is a fact about the target's specific compiler/
      optimization level that only a hardware measurement (Part B)
      could settle — and this ticket has no hardware. `argv` stays a
      local (unavoidable: `onRun()` needs it as an argument, and no
      early return exists ahead of it). `result` — the one item this
      ticket's own text flags as the fallback when reordering alone
      cannot be confirmed sufficient — moved to a new `WireHandler`
      member, `runResult_` (`src/comms/wire_handler.h`, same pattern
      `emitBuf_` already establishes for this class). This is a
      guaranteed reduction independent of any compiler behavior: member
      storage is never part of `execRun()`'s stack frame at all, on any
      compiler, at any optimization level. `execRun()` now clears
      `runResult_` explicitly before calling `onRun()` (`std::memset`),
      preserving the exact behavior the old `char result[...] = {}`
      stack-local's per-call zero-init gave (no observable behavior
      change: confirmed by the existing RUN golden-vector tests below).
- [x] (Part A) Existing wire-grammar host suite
      (`wire_handler.cpp`'s own RUN-verb host tests) passes unchanged —
      this is a pure refactor with no behavior change.

      Verified: `uv run pytest tests/host/test_wire_grammar.py
      tests/host/test_exec_run_stack_footprint_source_pin.py
      tests/host/test_protocol_stack_canary_source_pin.py
      tests/host/test_wire_constants_drift.py
      tests/host/test_archaeology_marker_budget.py -q` → 121 passed.
      Two new source-pin tests were added (see Testing below) to pin
      the stack-layout facts a functional host test structurally cannot
      observe (a host machine's stack has no relationship to the
      target's).
- [x] (Part A) `git diff` on `src/core/diffdrive.{h,cpp}` is empty
      (this ticket does not touch the kernel).

      Verified: `git diff --stat -- src/core/diffdrive.h
      src/core/diffdrive.cpp` produces no output.
- [ ] (Part B, team-lead session) The stack high-water mark under the
      tour-plus-radio-`RUN` scenario is measured and recorded with a
      MEASURED citation, or the ticket explicitly states UNVERIFIED and
      what was tried.

      **UNVERIFIED.** This programmer dispatch has no hardware and did
      not attempt Part B, per this ticket's own split. What it DID do,
      in support of Part B: added a stack-canary fill scaffold
      (`Protocol::paintStackCanary()`, `src/comms/protocol.{h,cpp}`),
      gated behind the same `DIFFDRIVE_FAULT_SPIN` macro
      `src/platform/nezha_port.cpp` already uses for fault forensics —
      a normal build compiles it as a literal no-op (`{}`), so it is
      inert in every build except the one Part B's own session builds
      on purpose. It runs as the very first statement of
      `Protocol::run()` (the protocol fiber's entry point), filling the
      currently-unused region of that fiber's own stack — from
      `currentFiber->stack_bottom` up to (but never past) a ceiling
      derived from a local variable's own address, so it can never
      overwrite memory the painting call itself is still using — with
      the byte `0xA5`. This code has NOT been compiled for the target
      (no ARM toolchain build was attempted in this dispatch — see
      below) and has NOT run on any board; it is source-reviewed only,
      pinned by `tests/host/test_protocol_stack_canary_source_pin.py`
      for shape, not behavior. Treat it as a draft the team-lead should
      sanity-build before relying on it.

      **Exact recipe for the team-lead session:**
      1. Build with the canary scaffold and fault-forensics both
         active: `DIFFDRIVE_FAULT_SPIN` must be defined for the build
         (check how `tools/make_deploy.py` plumbs compiler defines
         through to the PXT/yotta build, or add a temporary define at
         the top of `src/comms/protocol.cpp`/`src/platform/nezha_port.cpp`
         if it does not already expose one). First confirm the build
         actually compiles — this has not been done.
      2. Flash the resulting hex to the bench board (see
         `.claude/rules/connecting-to-a-robot.md`).
      3. Run one full `RUN:tour` (the existing tour test-program
         verb), then, before the tour completes, send one `RUN x #1`
         over the radio link (any bound, cheap-to-call test.ts
         function will do — the point is exercising the RUN wire path
         while the tour job is still live on the same fiber).
      4. Halt the board with pyOCD (`pyocd cmd -t
         <target> halt`), then read the protocol fiber's stack region:
         `currentFiber->stack_bottom`/`stack_top` bound it (the same
         fields `paintStackCanary()` reads); dump that range and find
         the lowest address whose byte is no longer `0xA5` — the gap
         between that address and `stack_top` is the high-water mark,
         in bytes.
      5. Record the result as `MEASURED <board> <date>,
         <capture-artifact-path>: <N> bytes of <total fiber size> used`
         per `.claude/rules/measurement-citations.md` — or, if the
         session cannot complete some step above, record precisely
         which step failed and why, still as UNVERIFIED, not silently
         dropped.
      6. A pass/fail bar: the sprint's own Success Criteria does not
         set a numeric threshold — the fiber is documented elsewhere in
         this codebase as 2 KB (`.claude/rules/fiber-yield-safety.md`).
         A high-water mark comfortably under that (rule-of-thumb
         margin: at least 25% headroom, i.e. under ~1536 bytes used) is
         a clean pass; anything closer is a finding for a future sprint
         ticket, not a blocker for closing this one — this ticket's own
         text says as much ("if margin is still tight, that is a
         finding for a future sprint, not a blocker here").

## Testing

- **Existing tests run**: `wire_handler.cpp`'s existing RUN-verb host
  test coverage (`tests/host/test_wire_grammar.py`'s RUN golden
  vectors), plus `test_wire_constants_drift.py` and
  `test_archaeology_marker_budget.py` (the relocation added zero new
  archaeology-marker lines — still 387/388). All pass unchanged.
- **New tests written**: two source-pin tests, since neither property
  is observable by compiling and running anything on this host:
  - `tests/host/test_exec_run_stack_footprint_source_pin.py` — pins
    `execRun()`'s local-variable shape in `wire_handler.cpp` (a file
    the host CAN compile, but stack-frame layout has no host-side
    analog to compile-and-observe).
  - `tests/host/test_protocol_stack_canary_source_pin.py` — pins the
    `paintStackCanary()` scaffold in `protocol.cpp` (a file the host
    CANNOT compile at all — it pulls in `pxt.h`), the same
    can't-compile-it-here reason every other `_source_pin.py` file in
    this directory exists.
- **Verification command run**: `uv run pytest tests/host/test_wire_grammar.py
  tests/host/test_exec_run_stack_footprint_source_pin.py
  tests/host/test_protocol_stack_canary_source_pin.py
  tests/host/test_wire_constants_drift.py
  tests/host/test_archaeology_marker_budget.py -q` → 121 passed. Full
  `uv run pytest` deferred to `close_sprint`, per this sprint's own
  testing convention. Part B has no pytest equivalent — pyOCD read,
  team-lead session, recipe above.
