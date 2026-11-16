---
id: '003'
title: Hardware acceptance of the stored radio address and _reboot
status: open
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '001'
- '002'
github-issue: ''
issue:
- stored-radio-address-set-over-the-wire.md
- high/the-wire-has-no-reboot-verb.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware acceptance of the stored radio address and _reboot

## Description

Prove the feature on one real robot over USB (see
`.claude/rules/connecting-to-a-robot.md` and `playfield-testing.md`; read
the other `.claude/rules/` files). Script in `tests/dev/` using the shared
helper `tests/dev/devlink.py`, listed in `tests/dev/DESIGN.md`; logs in
`captures/<session>/`. Every result in the ticket, the sprint, and the
closed issues cites its capture file (`measurement-citations.md`). The
robot stays still throughout; no moves are needed. This ticket also covers
`the-wire-has-no-reboot-verb.md`, so add that issue with
`add_issue_ref`.

Sequence:
1. Baseline: boot line and `_radioshow` on the name-derived address.
2. `_radioset <ch> <grp>` (a harmless unused channel, 47-83), read back,
   `_reboot`: confirm `reboot.ok` arrived before the reset, the boot line
   shows the stored address with source `stored`, and STATUS reports it.
3. Invalid sets (channel 84, group 256, 1.5) answer `radiostore.fail` and
   change nothing.
4. Flash a different program, then this program again: stored address kept.
5. `_radioclear`, `_reboot`: boot line returns to the name-derived address,
   source `name`.
6. `_reboot` while a program runs answers `reboot.fail`. Record, without
   claiming it, what a raw in-flight motion does on `_reboot` only if it
   can be done safely and camera-checked; otherwise leave it UNVERIFIED.
7. Leave the robot on its name-derived address.

Close `the-wire-has-no-reboot-verb.md` with the residue noted (run command,
not a wire verb; mid-move behaviour as measured or UNVERIFIED).

## Acceptance Criteria

- [ ] Steps 1-5 pass with capture files named in the results.
- [ ] `reboot.ok` ordering and `reboot.fail` result recorded with captures.
- [ ] `tests/dev/DESIGN.md` lists the new script.
- [ ] Robot restored to its name-derived address.
- [ ] Results written as MEASURED with artifact paths, or UNVERIFIED.

## Testing

- **Existing tests to run**: `uv run pytest tests/host` unaffected.
- **New tests to write**: the `tests/dev/` acceptance script (not pytest).
- **Verification command**: the script's own output in `captures/`.
