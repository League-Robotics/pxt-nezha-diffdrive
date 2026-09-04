---
id: '005'
title: execRun buffer relocation and protocol-fiber stack high-water mark
status: open
use-cases: [SUC-005]
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

- [ ] (Part A) `sanitized`/`buf` are declared after `execRun()`'s early
      returns; `result` is a `WireHandler` member if needed to further
      shrink the pre-refusal footprint (state which was done and why).
- [ ] (Part A) Existing wire-grammar host suite
      (`wire_handler.cpp`'s own RUN-verb host tests) passes unchanged —
      this is a pure refactor with no behavior change.
- [ ] (Part A) `git diff` on `src/core/diffdrive.{h,cpp}` is empty
      (this ticket does not touch the kernel).
- [ ] (Part B, team-lead session) The stack high-water mark under the
      tour-plus-radio-`RUN` scenario is measured and recorded with a
      MEASURED citation, or the ticket explicitly states UNVERIFIED and
      what was tried.

## Testing

- **Existing tests to run**: `wire_handler.cpp`'s existing RUN-verb host
  test coverage; `tests/host/` full suite scoped to `wire_handler.cpp`
  during implementation.
- **New tests to write**: none required for Part A beyond confirming
  existing tests still pass — this is a refactor, not new behavior.
  Part B is hardware-only with no host-test substitute.
- **Verification command**: `uv run pytest tests/host/ -k
  "wire_handler or exec_run"` during implementation; full `uv run
  pytest` at `close_sprint`. Part B has no pytest equivalent — pyOCD
  read, team-lead session.
