---
id: '003'
title: 'Build checkpoint: flash vevov and tovez, verify ID/HELLO name agreement on
  each'
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ['001', '002']
github-issue: ''
issue:
- id-verb-reports-a-baked-constant-not-the-machine-name.md
- make-deploy-accepts-a-silently-incomplete-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: flash vevov and tovez, verify ID/HELLO name agreement on each

## Description

This sprint's own build-checkpoint-and-flash-verification ticket,
following the established per-sprint convention (sprints 014-019, 022
each ended with one). It is the acceptance test for both of this
sprint's issues, and it is the reason ticket 001 (build-gate hardening)
must be genuinely complete and passing before this ticket runs: this
ticket's own trust in "the hex that reached each board is really this
sprint's code" now depends on `make_deploy.py`'s hardened gate meaning
what it says.

Run a real `make_deploy.py` build (through the now-hardened gate from
ticket 001, carrying ticket 002's `execId` change), flash it to **both**
vevov and tovez, and confirm on each board that `ID`'s new fourth field
agrees with that same board's `HELLO` reply. This is the acceptance test
Eric specified directly in the issue: "Flash two different boards. `ID`
must return each board's own name, and that name must agree with the
same board's `HELLO` reply. Agreement between `ID` and `HELLO` is the
acceptance test."

**Hardware notes** (from `.claude/rules/playfield-testing.md` and this
sprint's own briefing):
- vevov: channel 4, reachable via the zavaz relay.
- tovez: channel 3, but the getez relay is **not connected** — USB only.
- Both boards are on the bench, charged.
- `mbdeploy probe` is the only authority on ports and intermittently
  reports a present board as `CONN=no` — don't take one `CONN=no` read
  as proof a board is absent; re-probe.
- Opening/reopening a USB serial port resets the target program (pose
  and any other in-memory state re-zeros) — plan each board's
  verification as one serial/radio session, don't assume state survives
  a port close between `ID` and `HELLO`.

This ticket needs no camera and no motion — it is a wire-protocol
identity check, not a driving test. Do not drive either robot as part
of this ticket.

## Acceptance Criteria

- [ ] A full `make_deploy.py` build for vevov (`--robot vevov`) passes
      the hardened gate from ticket 001 (hex size floor, all-ten-files
      translation-unit check) with no failures.
- [ ] A full `make_deploy.py` build for tovez (`--robot tovez`)
      similarly passes the hardened gate.
- [ ] vevov, flashed with its build, replies to `ID` with its own name
      as the fourth field, and that name matches vevov's `HELLO` reply
      name.
- [ ] tovez, flashed with its build, replies to `ID` with its own name
      as the fourth field, and that name matches tovez's `HELLO` reply
      name.
- [ ] vevov's and tovez's `ID` name fields **differ from each other**
      (proving this isn't two boards coincidentally both showing a
      stale shared constant — the original defect this sprint fixes).
- [ ] Both boards' `ID` replies still show fields 0-2
      (`drivetrain`/`profile`/`version`) in the pre-existing 3-field
      shape, undisturbed by the append.
- [ ] Build evidence recorded in this ticket (or its completion note):
      hex byte sizes for both builds, and the full set of ten
      `Building CXX object` lines confirmed present for both, matching
      the documentation convention of prior build-checkpoint tickets
      (e.g. sprint 016 ticket 007).

## Implementation Plan

**Approach**: Sequential, one board at a time (matching sprint 022
ticket 003's proven pattern): build for vevov, flash, verify over its
relay; build for tovez, flash, verify over USB. Use `tools/robotlink.py`
(or equivalent existing wire-session tooling) to send `ID` and read
`HELLO`'s banner or an explicit `HELLO` request within one serial/radio
session per board, per the reopen-resets-state note above.

**Files to modify**: None — this ticket is verification, not code. If
verification surfaces a defect in tickets 001 or 002's work (e.g. a
buffer truncation, a build that doesn't actually carry the code change),
fix it here or reopen the relevant ticket, per normal practice.

**Files to create**: None, beyond this ticket's own recorded build
evidence.

## Testing

- **Existing tests to run**: The full suite gate happens once at
  `close_sprint`, not per-ticket (per `.claude/rules/source-code.md`) —
  this ticket's own verification is the hardware check described above,
  not a pytest run.
- **New tests to write**: None — this ticket is a hardware acceptance
  check, not a host-testable change. (Tickets 001 and 002 already carry
  the host-level regression tests for their respective code changes.)
- **Verification command**: `uv run python tools/make_deploy.py --robot
  vevov --flash` and `uv run python tools/make_deploy.py --robot tovez
  --flash`, followed by manual `ID`/`HELLO` comparison on each board
  over its own transport.
