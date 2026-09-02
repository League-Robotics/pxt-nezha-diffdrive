---
status: pending
---

# UART wedge baseline did not reproduce on a pre-fix rebuild

## Description

Sprint 027 ticket 002 (hardware acceptance for the single-serial-producer
fix) was required to reproduce the concurrent-writer UARTE wedge on
pre-fix firmware before judging the fix. It could not. On tigez over
local USB, a pre-fix build made from commit `1217f19` (the commit
immediately before the fix, `drainEmitQueue` confirmed absent from the
compiled `protocol.cpp`) survived 20 trials of the documented trigger
verbs (`RUN:z` x15, `RUN:ping` x5) across three reset paths (serial
reopen, boot-banner race, SWD hardware reset via pyOCD). `HELLO`
answered after every trial. Full record:
`captures/tigez-uart-wedge-20260902/notes.md`, step 1.

The original issue,
`clasi/sprints/027-one-serial-producer-fix-the-uart-wedge-and-retest-the-radio-wedge/issues/done/concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`,
measured the wedge on the same board earlier the same day at "100% of
the time" on a local docker build, with direct pyOCD register reads of
the wedged UARTE (`rxBuffHead=rxBuffTail=0` after 17 bytes sent,
`is_tx_in_progress_=0`, `ERRORSRC=0`, bare halt/go recovering it). Those
register reads are not in doubt. What is in doubt is why a rebuild of
the same source, on the same toolchain image id (`d1a78700858a`, built
2026-08-31, tagged both `ghcr.io/league-microbit/yotta-compiler:latest`
and `pext/yotta:latest`), no longer lands in the race window.

The fix itself is not in question: the fixed build passed a 12-command
soak and the telemetry-subscribed cleartext `RUN:` check on the same
board the same session (steps 2 and 3 of the same notes file), and the
structural argument (exactly one caller each for `uBit.serial.send` and
`RadioTransport::sendLine`) stands on its own.

## What would settle it (all UNVERIFIED)

- **Hex identity of the original measurement.** The morning session's
  wedging hex was not preserved. If any copy exists (a leftover
  `.tmp/deploy-head/built/binary.hex` on another checkout, a worktree,
  a mbdeploy cache), flash it and send `RUN:z`. A wedge there and none
  on the `1217f19` rebuild would localise the difference to the build,
  not the board.
- **Host-side send pattern.** The original reproduction may have sent
  the `RUN:` line with a different preceding traffic pattern (a `HELLO`
  in the same write, a relay banner, a different inter-line delay) that
  placed the line's arrival inside the race window. Replay the exact
  original transcript if one exists; otherwise sweep the delay between
  `HELLO` and `RUN:z` over 0-200 ms in 5 ms steps.
- **Working-tree state at measurement time.** The original session had
  the ad-hoc fix in its working tree at some point. Confirm from that
  session's hooks/build log which source state the wedging hex was
  compiled from; `1217f19` is the assumption, not a record.
- **Board state.** `.claude` memory records I2C/peripheral wedges that
  come and go with board state and are cured by reflash. A wedge whose
  probability depends on board state would look exactly like this.
  Retest after the board has sat idle for hours, before any reflash.

## Why it matters

Without a reproduced baseline, the sprint 027 fix is verified by a
"no failure observed" result plus a structural argument, not by a
before/after pair on identical hardware. That is still good evidence,
but any future "the serial link died" report cannot be triaged against a
known-good reproduction recipe until this is resolved.
