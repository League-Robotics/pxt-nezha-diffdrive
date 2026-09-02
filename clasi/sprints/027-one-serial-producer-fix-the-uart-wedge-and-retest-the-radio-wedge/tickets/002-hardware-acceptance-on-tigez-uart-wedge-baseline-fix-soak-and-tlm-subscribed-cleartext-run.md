---
id: '002'
title: 'Hardware acceptance on tigez: UART wedge baseline, fix soak, and TLM-subscribed
  cleartext RUN'
status: open
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: cleartext-run-hangs-the-link-under-active-telemetry.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware acceptance on tigez: UART wedge baseline, fix soak, and TLM-subscribed cleartext RUN

## Description

Ticket 001 restructures `Protocol::emitLine()`/`Protocol::run()` so the
protocol fiber is the sole producer into both transports, closing the
concurrent-writer UARTE wedge. That fix must be hardware-confirmed on
the same board and toolchain that reproduced the wedge, per
`.claude/rules/measurement-citations.md` — the wedge is a timing race
(local docker toolchain build only; the MakeCode cloud build shifts
timing and never lands in the window, per the issue's own "why local
builds and not cloud builds" note) and no host test can substitute for
a real board.

This ticket runs the full acceptance sequence on **tigez** (farm node
meili, USB serial, pyOCD on the SWD port — never DAPLink MSD, and build
with `--robot tigez` per `tools/make_deploy.py`):

1. **Baseline, on CURRENT (unfixed) firmware.** Reproduce the wedge
   before judging the fix: send `RUN:z`, confirm the port stops
   answering in both directions (dead to `HELLO`, no reply to
   anything), and confirm a bare pyOCD `halt`/`go` recovers it — the
   exact signature `concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`
   already measured. This step exists so the fix is judged against a
   reproduced failure, not an assumed one.
2. **Fixed firmware — soak.** Build with ticket 001's change. Send
   `RUN:z`, `RUN:ping`, then a 10+ command soak (mirroring the issue's
   own "verified on hardware" soak: 10 alternating commands, 0
   reboots, port alive at the end). 0 wedges, `HELLO` answers
   throughout.
3. **Fixed firmware — TLM-subscribed cleartext RUN.** Subscribe `TLM
   POSE`, then send a cleartext `RUN:<name>` line while telemetry is
   active — the exact trigger
   `cleartext-run-hangs-the-link-under-active-telemetry.md` recorded
   (six independent reproductions, 15+ s of total silence, telemetry
   itself stopping). Confirm the link no longer hangs and telemetry
   keeps flowing. This closes that issue as the same defect ticket 001
   fixes — no separate code change is expected here, only the hardware
   confirmation the issue's own "What to do" section calls for.

Every claim in this ticket's completion notes must be a `MEASURED`
comment naming its capture file under `captures/`, board, and date. An
untested combination is written as `UNVERIFIED`, not asserted.

## Acceptance Criteria

- [ ] Baseline reproduction on current firmware: `RUN:z` wedges the
      port in both directions on tigez, confirmed with pyOCD
      halt/go recovering it, MEASURED and cited before the fix build
      is flashed.
- [ ] Fixed firmware: `RUN:z`, `RUN:ping`, and a 10+ command soak
      produce 0 wedges; `HELLO` answers throughout; MEASURED and
      cited.
- [ ] Fixed firmware, `TLM POSE` subscribed: a cleartext `RUN:` command
      no longer hangs the link or stalls telemetry; MEASURED and
      cited.
- [ ] `cleartext-run-hangs-the-link-under-active-telemetry.md` is
      closed (via `move_issue_to_done` / this ticket's `issue:`
      linkage) with the hardware evidence recorded in its own file or
      this ticket's completion notes.
- [ ] `probe(29)`/`diagValue(29)` (ticket 001's drop counter) reads 0
      across the soak, or any nonzero reading is explained (a host
      genuinely out-running the robot) rather than silently accepted.
- [ ] Every capture file referenced is committed under `captures/` (or
      the ticket states why not, e.g. raw pyOCD console output pasted
      into completion notes for a one-off register read).
- [ ] `uv run pytest` (full host suite) still passes — this ticket adds
      no new host-testable code of its own, but must not have required
      any host-test-breaking change to reach hardware acceptance.

## Implementation Plan

**Approach**: This is a hardware-verification ticket, not a code
ticket. Build ticket 001's firmware locally (docker toolchain, not the
cloud compiler — the race does not reproduce there), flash tigez on
meili via pyOCD, and run the three-step sequence above in order,
capturing console/serial output for each step before moving to the
next. Keep the pre-fix baseline build and the post-fix build clearly
labeled in captures so a reader can tell which result belongs to which
firmware.

**Files to create**: capture files under `captures/` for the baseline
reproduction, the soak test, and the TLM-subscribed RUN check (naming
convention matching existing capture directories, e.g.
`captures/tigez-uart-wedge-20260902/`).

**Files to modify**: `clasi/issues/cleartext-run-hangs-the-link-under-active-telemetry.md`
(closed via the ticket's issue linkage — no manual edit needed beyond
what `move_issue_to_done`/ticket completion produces, unless the
hardware evidence needs to be appended to the issue file directly
before closing).

**Files NOT to modify**: no firmware source changes are expected in
this ticket — if the soak or TLM check surfaces a NEW defect, throw a
ticket exception rather than silently patching code outside this
ticket's acceptance criteria.

## Testing

- **Existing tests to run**: `uv run pytest` (full host suite),
  confirming ticket 001 left it green before spending bench time on
  hardware.
- **New tests to write**: none (hardware acceptance, not host-testable
  by construction — the wedge is a timing race the host cannot
  reproduce).
- **Verification command**: the three hardware steps above, each with
  a MEASURED capture; `uv run pytest` as the regression floor.
