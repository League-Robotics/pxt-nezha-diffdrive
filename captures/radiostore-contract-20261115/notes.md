# Radio store replies changed to the console contract, re-run on tovez (2026-11-15)

Why: v1.20261115.1 answered `radiostore.values` with `ch`, `grp`, `stored`,
`source`, `default_ch`, `default_grp`. robot-console's
`docs/design/radio-store-contract.md` (its sprint 030) and its parser
`packages/host/src/radio/robotRadioStore.ts` expect `ch`/`grp` only when
stored, `use_ch`, `use_grp`, `src`, and `why` of `args` or `range`. The
console read the released firmware as "no stored radio setting".

Change: `src/blocks/radiostore.ts`, `src/blocks/program.ts`. Same driver,
`tests/dev/radiostore_accept.py all`, same fixtures, tovez on its stand.

| Step | Result | Capture |
|---|---|---|
| Baseline | PASS | `04-baseline.txt`: `{"ev":"radiostore.values","stored":0,"use_ch":48,"use_grp":29,"src":"name"}` |
| Invalid sets (84 29, 77 256, -1 29: `range`; 77 1.5, 77.5 29, one argument: `args`) | PASS | `05-invalid_sets.txt`; `06-invalid_then_show.txt` `"stored":0` |
| Set 77 29, in use unchanged, reboot | PASS | `07-set_then_reboot.txt`: `"ch":77,"grp":29,"stored":1,"use_ch":48,"use_grp":29,"src":"name"`, `reboot.ok`, `boot radio tovez ch 77 grp 29 stored`, `"use_ch":77,"use_grp":29,"src":"stored"` |
| Flash B, then A (sector erase), address kept | PASS | `08-flash_b.txt`, `09-b_boot_and_show.txt`, `10-flash_a.txt`, `11-a_boot_and_show.txt` |
| `reboot.fail` while a button-started program runs | PASS | `12-reboot_fail_while_program_runs.txt` |
| Clear, reboot, name-derived again | PASS | `15-clear_then_reboot.txt`: `"stored":0,"use_ch":77,"use_grp":29,"src":"stored"`, then `boot radio tovez ch 48 grp 29 name` |

Every `radiostore.*` line in these captures was fed to the console's
`parseRadioStoreReply`; none came back `unsupported` (throwaway vitest file,
not kept).

`00-*-blocked-by-console-lock.txt`: two first attempts failed because the
robot console held tovez's serial lock; its session was closed and the run
repeated.

## Through the robot console, on tigez

Driver: `tests/dev/console_radio.mjs` against the running console's websocket;
flashes by the console's own flash (`request_flash`, template release hex).

| Step | Result | Evidence |
|---|---|---|
| Save 72/179 with console at 3283761, firmware v1.20261115.2 | FAIL: `old-firmware` | not kept (file overwritten). Cause: the robot acks a RUN before the handler's reply and the console stopped reading at the ack. Fixed in robot-console 7c1b0e1. |
| Save again, console restarted on 7c1b0e1, Wi-Fi session also open | FAIL: `not-writable` | not kept. Cause: the save picked the Wi-Fi session. Fixed in robot-console c6f7918 (not yet running in the console used here). |
| Save again with the Wi-Fi session closed | reserved, written, committed, rebooted; warning "did not reconnect" | `console/01-save-72-179.jsonl`; `console/02-verify.jsonl` `ok` |
| After that reboot the robot was still on 52/179 | template `main.ts` called `setupRadioForName()` after `setupRobot()` | STATUS read through the console, not captured to a file. Fixed in template release v0.20261116.3. |
| Console flash of v0.20261116.3 over the stored 72/179 | robot boots on 72/179, console verify `ok` | `console/04-verify-after-flash.jsonl`; STATUS `channel=72 group=179` read through the console, not captured to a file. `console/03-watch-during-flash.jsonl` is empty: no mismatch was broadcast. |

Not tested: a console flash that mass-erases (tigez's did not), and the Save
flow end to end on c6f7918.
