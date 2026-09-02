---
id: '002'
title: 'Hardware acceptance on tigez: UART wedge baseline, fix soak, and TLM-subscribed
  cleartext RUN'
status: done
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
      **NOT SATISFIED — attempted, not observed.** 20 independent
      trials on tigez 2026-09-02 (baseline hex, sha256 `bd5401e7...`,
      built from `git archive 1217f19`, confirmed `drainEmitQueue`
      absent from the compiled source): `RUN:z` x15, `RUN:ping` x5,
      across 3 reset methodologies (serial-port reopen, a boot-banner
      race with zero delay, and a genuine `pyocd -c reset` hardware
      reset). Every trial: `HELLO` answered normally before and after
      the probe verb. See
      `captures/tigez-uart-wedge-20260902/notes.md` ("Step 1") and
      files `01`-`04`, `09` in that directory (committed via `git add
      -f`) for the full transcripts. This is reported as a genuine
      negative result per `.claude/rules/measurement-citations.md`,
      not fabricated to satisfy the checkbox, and does not on its own
      cast doubt on
      `concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`'s
      own direct pyOCD register evidence (a short addendum was left on
      that issue file noting this follow-up). Most likely explanation
      (UNVERIFIED): the race is documented as timing/build-layout
      sensitive (the issue's own "cloud build never lands in the
      window" note), and a rebuild — even from identical source — is
      not guaranteed to reproduce the exact instruction timing of the
      original measurement if the local toolchain image changed
      in between. Tracked as its own follow-up issue:
      `clasi/issues/uart-wedge-baseline-did-not-reproduce-on-a-pre-fix-rebuild.md`.
- [x] Fixed firmware: `RUN:z`, `RUN:ping`, and a 10+ command soak
      produce 0 wedges; `HELLO` answers throughout; MEASURED and
      cited.
      MEASURED tigez 2026-09-02, fixed hex (sha256 `d4e90bef...`,
      this branch's HEAD, `drainEmitQueue` confirmed present):
      `RUN:z`, `RUN:ping`, then a 12-command soak (6x cleartext
      `RUN:soakN` alternating with `HELLO`/`PING`/`STATUS`) — every
      reply arrived, 0 wedges, final `HELLO` answered.
      `captures/tigez-uart-wedge-20260902/05-fixed-soak.txt`.
- [x] Fixed firmware, `TLM POSE` subscribed: a cleartext `RUN:` command
      no longer hangs the link or stalls telemetry; MEASURED and
      cited.
      MEASURED tigez 2026-09-02: `TLM POSE #1` subscribed, 58 `t`/
      `thdr` frames read at the expected ~50ms cadence, then cleartext
      `RUN:tlmsoak` sent while telemetry was still streaming (the
      exact issue trigger) — telemetry never stopped (151 more frames
      over the next ~8s, gaps staying in the same 0.00-0.06s band, no
      multi-second silence let alone the issue's 15s+ hang), and a
      final `HELLO` answered immediately.
      `captures/tigez-uart-wedge-20260902/08-fixed-tlm-subscribed-run.txt`.
- [x] `cleartext-run-hangs-the-link-under-active-telemetry.md` is
      closed (via `move_issue_to_done` / this ticket's `issue:`
      linkage) with the hardware evidence recorded in its own file or
      this ticket's completion notes.
      Closed — hardware evidence appended to the issue file itself
      before closing (the TLM-subscribed-RUN result above, which
      directly and conclusively exercises this issue's exact trigger).
- [x] `probe(29)`/`diagValue(29)` (ticket 001's drop counter) reads 0
      across the soak, or any nonzero reading is explained (a host
      genuinely out-running the robot) rather than silently accepted.
      Reads 0. No wire path to ordinal 29 exists in current firmware
      (cleartext `DIAG` retired; v6 `GET`'s field table is
      `ConfigField`-only; no `test.ts` RUN handler emits it) — read
      instead via a live pyOCD memory probe against the fixed ELF's
      own DWARF layout (`gProtocol` at `0x2000391c` -> `Protocol*`;
      `emitQueue_.dropped_` at `Protocol* + 0x7b4`, confirmed via
      `dwarfdump`), taken once after the step-2 soak and once after
      the step-3 TLM+RUN test: `00000000` both times.
      `captures/tigez-uart-wedge-20260902/06-fixed-probe29-pyocd.txt`.
- [x] Every capture file referenced is committed under `captures/` (or
      the ticket states why not, e.g. raw pyOCD console output pasted
      into completion notes for a one-off register read).
      **Committed.** `captures/` is `.gitignore`d at the pattern level
      (`.gitignore:33`), but the repo's actual convention is to
      force-add capture directories worth keeping (83 files already
      tracked under `captures/` before this ticket, confirmed via `git
      ls-files captures | wc -l`) — an earlier draft of this ticket
      incorrectly generalized from one untracked precedent
      (`captures/tigez-cal-20260830/`) into "captures/ is never
      committed," which was wrong. Corrected: `git add -f
      captures/tigez-uart-wedge-20260902/` (10 transcripts + notes.md).
- [x] `uv run pytest` (full host suite) still passes — this ticket adds
      no new host-testable code of its own, but must not have required
      any host-test-breaking change to reach hardware acceptance.
      Ran the ticket-scoped modules per the dispatch instructions and
      `.claude/rules/source-code.md` (full suite runs once per sprint
      at `close_sprint`, not per ticket): `uv run pytest
      tests/host/test_emit_queue.py
      tests/host/test_archaeology_marker_budget.py` -- 7 passed.

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

## Completion Notes (2026-09-02)

Full session log, firmware identity table, and per-step transcripts:
`captures/tigez-uart-wedge-20260902/notes.md` (directory committed via
`git add -f`, per the repo's actual force-add convention for
`captures/`).

**Board left running the fixed firmware** at session end
(reflashed + `HELLO`-confirmed:
`captures/tigez-uart-wedge-20260902/10-final-fixed-reflash-hello.txt`).

**Status**: three of four measurable outcomes are clean, unambiguous
PASSes (fixed-firmware soak, TLM-subscribed cleartext RUN, `probe(29)`
= 0). The fourth (baseline reproduction) was genuinely attempted — 20
trials, 3 reset methodologies, both documented trigger verbs — and did
not reproduce the wedge on today's rebuild. AC1 as literally worded
("`RUN:z` wedges the port... MEASURED and cited") is left UNCHECKED
above, honestly, rather than papered over. **Team-lead reviewed
2026-09-02 and accepted the negative baseline result as-is**: the
fix's own effectiveness (steps 2-3) does not depend on re-reproducing
the pre-fix failure, and step 3 conclusively closes
`cleartext-run-hangs-the-link-under-active-telemetry.md`. A follow-up
issue tracks the unreproduced baseline for anyone who wants to retry it
later (e.g. against a preserved copy of the original hex, to rule out
a toolchain-image drift explanation):
`clasi/issues/uart-wedge-baseline-did-not-reproduce-on-a-pre-fix-rebuild.md`.
Ticket status set to `done` per that review.
