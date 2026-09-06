---
id: 008
title: Build consolidated tovez firmware (sprint 030 + this sprint's wire/motion fixes)
status: done
use-cases:
- SUC-003
- SUC-004
depends-on:
- '003'
- '005'
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

- [x] Firmware builds cleanly with tickets 003 and 005's fixes plus
      sprint 030's already-merged code (no new merge conflicts, no
      `DIFFDRIVE_FAULT_SPIN`).
- [x] The resulting `built/binary.hex` (or equivalent artifact) is
      identified by its exact commit/build identity for citation in
      Session B's capture.
- [x] All host tests pass against this build's source
      (`uv run pytest tests/host/`).
- [x] No motor-mapping or radio-addressing constants for tovez are
      touched (already baked; see `tovez's motor mapping` note in this
      sprint's context) — this is a pure feature/fix build.

## Testing

- **Existing tests to run**: full `tests/host/` suite (this is a
  build/integration point, not a scoped ticket — run broadly before
  handing to Session B).
- **New tests to write**: none beyond what tickets 003/005 already
  added.
- **Verification command**: `uv run pytest tests/host/`

## Build record (this ticket)

**Build command** (run from the worktree root, no `--flash`):

```
uv run python tools/make_deploy.py --robot tovez
```

**Source commit built**: `ade852bf518dd4c077a49c276124c7e6ba76f763`
(branch `sprint/031-drivetrain-tuning-and-gate-acceptance-on-tovez`,
tree clean apart from this ticket's own status edit and the
`.clasi/.clasi.db` process file) — `git log` on this branch confirms
sprint 030's bus-guard/fiber-identity/motion-owner/raw-zero/staged-stop
commits (`50abf9a`, `bf597e1`, `6f6a9b0`, `c7fca90`,
`da589b0`/`fcc325c`) plus this sprint's ticket 002 (`96ffd6d`,
parallax single ownership), ticket 003 (`d8fab66`, done-reason latched
via `lastSegmentEndedByDeadline_`/`engineMoveEndedByDeadline()`), and
ticket 005 (`decf8a3`, `wrongWay()` gated on minimum yaw progress) are
all present on this HEAD, with no ticket-013/014
`DIFFDRIVE_FAULT_SPIN` build switch anywhere in the build path (that
symbol is `#ifdef`-guarded in `src/comms/protocol.cpp` and
`src/platform/nezha_port.cpp`; nothing in `tools/make_deploy.py` ever
defines it).

**Artifact**: `.tmp/deploy-head/built/binary.hex` (gitignored scratch
copy; not committed — reproduce with the command above against this
same commit). 1,721,681 bytes; `_count_universal_hex_blocks()` found 0
`:0400000A` markers, confirming a plain V2 (`csv-mbcodal`) hex, not a
stray universal build. SHA-256:
`a2c5d18a0b52c148f32e00162772188aef5468ce7a5a74e714cdc42f62f76e52`.

**Test-program inclusion, checked directly** (the "testFiles not in
hex" trap): the scratch copy's `pxt.json` has `test/test.ts` in
`files` and an empty `testFiles` list; the build log's
"Building CXX object" lines list every expected translation unit
(`make_deploy.py`'s own `_check_translation_units()` gate also passed,
or the build script would have exited non-zero).

**Motor bake, checked directly** in the scratch copy's
`src/shims.cpp`: `NezhaMotorPort left{2, -1}` /
`NezhaMotorPort right{1, +1}` — matches tovez's
`radio-robot-lib/config/robots/tovez.json`
`geometry.firmware_bake.motors` (`left_port:2, fwd_sign_left:-1,
right_port:1, fwd_sign_right:1`) exactly, and matches this ticket's
"tovez is wired left = port 2 (−1), right = port 1 (+1)" note. Nothing
in this ticket's own diff touches that config file or
`_inject_motors()`; the bake was already present in radio-robot-lib
before this ticket started. Radio: channel 55 / group 108, also read
unmodified from the same config.

**Version / ID string the board will report** after a successful
flash: `kVersion` was injected from `pyproject.toml`'s
`1.20260904.5` (verified in the scratch copy's
`src/comms/protocol.cpp`); `kProfile` is `"tovez"`. So `ID` should
answer `id diffdrive tovez 1.20260904.5 tovez` — distinct from the
board's current `1.20260903.1`, so a flash's success is checkable by
diffing that string. This ticket did **not** run
`dotconfig version bump` and did not hand-edit `pxt.json` — the
`1.20260904.5` pyproject.toml version predates this ticket
(`bab232e`, sprint 030) and this build only reads it, per the
version-scheme trap note above.

**Host tests**: `uv run pytest tests/host/` — 880 passed, 0 failed, run
in the foreground against this same commit before the firmware build.

**What is NOT verified here (no hardware)**: whether the board
actually boots and answers on this hex, whether the boot banner
(`tovez 04.05`) displays correctly on the LED matrix, and whether any
of sprint 030's or this sprint's runtime behavior (bus guard, wire
done-reason latch, wrong-way gating) holds on real hardware — all of
that is Session B's job (tickets 009-012), not this one. This ticket
only establishes that the source compiles, the artifact is the right
shape, and the previously-diagnosed fixes are present in the built
tree.

**For the team-lead before flashing**: the hex lives in this
worktree's `.tmp/deploy-head/` (gitignored scratch, not committed) —
either flash directly from there, or rerun the exact command above
against commit `ade852b` to reproduce it byte-for-byte. Do not add
`--flash` from an agent session per this ticket's scope; ticket 009
owns the flash step.
