---
id: '003'
title: Hardware acceptance of the stored radio address and _reboot
status: done
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

- [x] Steps 1-5 pass with capture files named in the results.
- [x] `reboot.ok` ordering and `reboot.fail` result recorded with captures.
- [x] `tests/dev/DESIGN.md` lists the new script.
- [x] Robot restored to its name-derived address.
- [x] Results written as MEASURED with artifact paths, or UNVERIFIED.

## Testing

- **Existing tests to run**: `uv run pytest tests/host` unaffected.
- **New tests to write**: the `tests/dev/` acceptance script (not pytest).
- **Verification command**: the script's own output in `captures/`.

## Results

Robot tovez, 2026-11-15, captures in `captures/sprint045-stored-radio-20261115/` (index and verbatim lines in its `notes.md`).
Driver `tests/dev/radiostore_accept.py`; fixtures `test/radiostore_a.ts`, `test/radiostore_b.ts`.

- MEASURED step 1 baseline, source `name` ch 48 grp 29: `02-baseline.txt`.
- MEASURED step 3 invalid sets (ch 84, grp 256, 1.5, -1, 77.5) store nothing: `03-invalid_sets.txt`, `04-invalid_then_show.txt`.
- MEASURED step 2 `_radioset 77 29`, STATUS unchanged until reboot, `reboot.ok` before the reset, boot line `ch 77 grp 29 stored`,
  STATUS `channel=77 group=29`: `05-set_then_reboot.txt` (one session).
- MEASURED step 4 flash B then A, address kept: `07-b_boot_and_show.txt`, `09-a_boot_and_show.txt` (flash logs `06`, `08`). Only for a
  flash that does not mass-erase: `mbdeploy` on tovez mass-erases (erase step fails) and wipes the settings; see `notes.md` Findings 2.
- MEASURED step 5 clear then reboot, back to `name`: `13-clear_then_reboot.txt`. Step 7 final state: `14-final_state.txt`.
- MEASURED step 6 `reboot.fail` while a button-started program runs: `10-reboot_fail_while_program_runs.txt`. A `RUN`-started program
  makes `_reboot` wait, then succeed: `11-reboot_queued_behind_run_program.txt`.
- MEASURED `_reboot` during a raw MOVE_X: queued until the move ends, then `reboot.ok` and reset: `12-reboot_during_raw_move.txt`.
  UNVERIFIED: that the wheels stop at the reset itself (the move had ended; STATUS only, no camera).
- Defect found and fixed in this ticket: `reboot.ok` never left the board (queue not drained before `control.reset()`).
