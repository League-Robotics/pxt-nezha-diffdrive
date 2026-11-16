# Sprint 045 ticket 003: stored radio address and _reboot on tovez (2026-11-15)

Robot: tovez (uid a8fdb5e4, `/dev/cu.usbmodem2221202`), on its stand, USB, local registry.
Driver: `tests/dev/radiostore_accept.py` (every serial step is one `mbserial` session, one capture file each).
Firmware under test: fixtures `test/radiostore_a.ts` / `test/radiostore_b.ts` built by
`uv run python tools/make_deploy.py --robot tovez --program radiostore_a.ts` (and `_b`), logs `build_a.log`, `build_b.log`.
Both call only `diffDrive.setupRobot()` (never `setupRadio`), so the radio source is decided by setupRobot. B is A plus a
`hello` run command. Both register `pause` (addProgram, body `basic.pause(6000)`), `pressa`/`pressb` (raise the A/B button click events).
Firmware includes the `_reboot` fix committed with this ticket (see Findings 1). Wheels never driven except one 300 mm MOVE_X (step 12).

## Before the first flash (0 = `00-preflash-observed.txt`, typed by hand, not scripted)

tovez was running `id diffdrive calibration-0.20261105.1 1.20261027.1 tovez`, `ver 1.20261027.1`,
STATUS `radio=1 channel=48 group=29`.

## Acceptance steps

All lines below are verbatim from the named capture.

| # | Step | Result | Capture |
|---|------|--------|---------|
| 1 | Baseline: name-derived address, source `name` | PASS | `02-baseline.txt`: `{"ev":"radiostore.values","ch":48,"grp":29,"stored":0,"source":"name","default_ch":48,"default_grp":29}`, STATUS `channel=48 group=29` |
| 3 | Invalid sets store nothing (ch 84, grp 256, grp 1.5, ch -1, ch 77.5) | PASS | `03-invalid_sets.txt`: five `radiostore.fail` (`channel must be a whole number from 0 to 83` / `group must be a whole number from 0 to 255`); `04-invalid_then_show.txt`: `"stored":0`. (A fresh boot sits between 03 and 04 because closing a session resets tovez on this Mac, which makes it a stronger check.) |
| 2a | `_radioset 77 29` replies, boot/STATUS unchanged before reboot | PASS | `05-set_then_reboot.txt`: `{"ev":"radiostore.values","ch":77,"grp":29,"stored":1,"source":"name",...}` then STATUS `channel=48 group=29` |
| 2b | `_reboot`: `reboot.ok` seen before the reset, board returns by itself | PASS | `05-set_then_reboot.txt`: `ack 4 0 none`, `{"ev":"reboot.ok","why":"asked"}`, `device NEZHA2 robot tovez 2314287040`, then `boot radio tovez ch 77 grp 29 stored`, `RADIOSTORE:boot program=a ...` (same session, no port close/open between set and reboot) |
| 2c | STATUS and `_radioshow` after reboot | PASS | `05-set_then_reboot.txt`: `"ch":77,"grp":29,"stored":1,"source":"stored"`, STATUS `channel=77 group=29` |
| 4a | Flash program B: still stored 77 | PASS | `07-b_boot_and_show.txt` (port opened with `--reset`): `boot radio tovez ch 77 grp 29 stored`, `RADIOSTORE:boot program=b`, `RADIOSTORE:hello` (B-only command ran), STATUS `channel=77 group=29`. Flash log `06-flash_b.txt`. |
| 4b | Flash program A again: still stored 77 | PASS | `09-a_boot_and_show.txt`: `boot radio tovez ch 77 grp 29 stored`, `RADIOSTORE:boot program=a`, STATUS `channel=77 group=29`. Flash log `08-flash_a.txt`. |
| 6a | `_reboot` while a program runs answers `reboot.fail` | PASS | `10-reboot_fail_while_program_runs.txt`: `menu pause`, `run pause` (button path, program on its own fiber), `{"ev":"reboot.fail","why":"a program is running -- press a button or send STOP first"}`, no `reboot.ok`, board did not reset |
| 6b | `_reboot` sent after `RUN pause` over the wire (extra finding) | measured | `11-reboot_queued_behind_run_program.txt`: both acked, no `reboot.fail`; `reboot.ok` then reset after the 6 s program ended (the run queues behind the running RUN program) |
| 6c | `_reboot` during a raw `MOVE_X` | MEASURED partial, see below | `12-reboot_during_raw_move.txt` |
| 5 | `_radioclear`, `_reboot`: back to name-derived, source `name` | PASS | `13-clear_then_reboot.txt`: `"stored":0,"source":"stored"` right after clear (this boot's source), `reboot.ok`, `boot radio tovez ch 48 grp 29 name`, `"stored":0,"source":"name"`, STATUS `channel=48 group=29` |
| 7 | Robot left on name-derived address | PASS | `14-final_state.txt`: `{"ev":"radiostore.values","ch":48,"grp":29,"stored":0,"source":"name",...}`, STATUS `channel=48 group=29` |

Step 6c (`12-reboot_during_raw_move.txt`): `MOVE_X 300 0 120 15000 #1` acked, STATUS `active=1`; `RUN _reboot #2` acked immediately but
STATUS stayed `active=1` for the next three polls (about 6 s) and `reboot.ok` followed, then the reset (`device NEZHA2 ...`, fresh boot lines,
STATUS `active=0 cyc=0`). So the reboot does NOT interrupt a raw move: the RUN is queued until the drivetrain is free, then runs. The claim
"the wheels stop at the reboot" is UNVERIFIED: the move ended on its own before the reboot ran, and wheel state was read from STATUS only
(no camera, robot on a stand). What would settle it: a move longer than the queue wait, with an `ESTOP`-free cancel, camera-checked.

## Findings

1. Defect in ticket 002's `reboot()`: `reboot.ok` never reached the wire. The run dispatch runs inline on the protocol fiber, and the
   emit queue is drained only by that fiber, so `basic.pause(120)` never drained it before `control.reset()`. Observed before the fix:
   ack then reset, no `reboot.ok` (earlier runs, `.tmp/discard*`, untracked and not a citable artifact). Fix: `for (6) _tickDrive()` before the reset (commit "Ticket 045-003: drain the
   reply queue before _reboot resets"). After the fix `reboot.ok` appears in `05`, `11`, `12`, `13`.
2. Flashing tovez erases settings. `mbdeploy deploy tovez` fails the erase step with firmware running (pyocd `0x67` flash erase failure at
   address 0 or a probe timeout); its recovery is a CTRL-AP mass erase, which wipes the settings store (the stored radio address, and by the same
   token stored calibration and WiFi address). Stored values were lost on every mbdeploy flash that mass-erased (seen on three occasions
   this session, earlier runs under `.tmp/discard*`, untracked; the mass-erase text is in the flash logs of those runs only). The address does survive a flash that does not mass-erase. This is what
   `06-flash_b.txt` / `08-flash_a.txt` show: `pyocd flash --connect halt --erase sector` with a hex trimmed to 0x1000..0x80000 (sector 0 and
   the UICR record removed; the MBR is byte-identical between builds) succeeds with `Erased 40960 bytes (10 sectors) ... identical 409600 bytes`
   and the address is kept. The probe is flaky (timeouts while programming); twice a run needed the board recovered with mbdeploy.
   The template release can only claim "survives a reflash" for a flash that does not mass-erase.
3. Opening or closing a serial session resets tovez on this Mac (boot lines appear at the top of the next capture). Every
   set-then-reboot proof therefore runs in ONE session. Boot lines after a flash are seen by opening with `--reset`.
4. `reboot.fail` is only reachable for a program on its own fiber (a button-started menu program, or one that pauses between moves). A
   program started by `RUN` runs on the protocol fiber, so a following `_reboot` waits for it and then succeeds (6b).
5. `tools/make_deploy.py`: `RADIO_ROBOT_LIB` and `ELITE` pointed at `/Volumes/Proj/proj/RobotProjects/...`; fixed to
   `robot-projects`. `radio-robot-elite` is not checked out anywhere under `/Volumes/Proj/proj/`, so `--flash` (which runs mbdeploy with
   `cwd=ELITE`) still cannot run; the script's flashes use mbtools directly.

## Final state of tovez

Stored radio address cleared (name-derived ch 48 grp 29, source `name`), running program A (`test/radiostore_a.ts`) built from branch
`sprint/045-stored-radio-address-set-over-the-wire` with the `_reboot` fix. `14-final_state.txt`.
