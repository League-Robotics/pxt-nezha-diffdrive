---
id: 008
title: Build consolidated tovez firmware (sprint 030 + this sprint's wire/motion fixes)
status: open
use-cases: [SUC-003, SUC-004]
depends-on: ['003', '005']
github-issue: ''
issue:
- wire-done-reason-is-resolved-lazily.md
- segment-moves-end-early-just-after-boot.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build consolidated tovez firmware (sprint 030 + this sprint's wire/motion fixes)

**Type: (b) desk work — programmer/team-lead build step. No hardware
(build only; flashing happens in ticket 009).**

## Description

Sprint 030's fixes (bus-ownership guard, fiber-identity check,
self-resolving motion obligation, raw-zero rejection, stack-canary
scaffold) are already merged on this branch but have never been
flashed to tovez, which still runs pre-030 firmware `1.20260903.1`.
This ticket builds ONE consolidated binary containing sprint 030's
already-merged code plus this sprint's own code fixes (tickets 003 and
005) — no gain retuning is baked here; that happens live via `SET` in
Session B and gets its own build in ticket 015.

Follow `tools/make_deploy.py`'s standard build path (per
`connecting-to-a-robot.md` / `docs/robot-connections.md`); confirm the
version-scheme trap doesn't apply (no `close_sprint`/`dotconfig version
bump` mid-sprint — see `git-commits.md`). Do NOT enable
`DIFFDRIVE_FAULT_SPIN` in this build — that is ticket 013/014's
separate, bracketed cycle.

## Acceptance Criteria

- [ ] Firmware builds cleanly with tickets 003 and 005's fixes plus
      sprint 030's already-merged code (no new merge conflicts, no
      `DIFFDRIVE_FAULT_SPIN`).
- [ ] The resulting `built/binary.hex` (or equivalent artifact) is
      identified by its exact commit/build identity for citation in
      Session B's capture.
- [ ] All host tests pass against this build's source
      (`uv run pytest tests/host/`).
- [ ] No motor-mapping or radio-addressing constants for tovez are
      touched (already baked; see `tovez's motor mapping` note in this
      sprint's context) — this is a pure feature/fix build.

## Testing

- **Existing tests to run**: full `tests/host/` suite (this is a
  build/integration point, not a scoped ticket — run broadly before
  handing to Session B).
- **New tests to write**: none beyond what tickets 003/005 already
  added.
- **Verification command**: `uv run pytest tests/host/`
