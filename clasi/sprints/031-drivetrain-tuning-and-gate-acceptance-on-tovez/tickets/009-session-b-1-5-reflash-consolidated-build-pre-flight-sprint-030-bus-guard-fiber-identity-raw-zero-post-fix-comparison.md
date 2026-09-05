---
id: 009
title: 'Session B (1/5): reflash consolidated build; pre-flight; sprint-030 bus-guard,
  fiber-identity, raw-zero post-fix comparison'
status: open
use-cases: [SUC-008]
depends-on: ['001', '008']
github-issue: ''
issue: sprint-030-hardware-acceptance-needs-one-bench-session.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session B (1/5): reflash consolidated build; pre-flight; sprint-030 bus-guard, fiber-identity, raw-zero post-fix comparison

**Type: (a) hardware/playfield — team-lead executes personally. First
step of Session B (see sprint.md Test Strategy).**

## Description

Flash tovez with ticket 008's consolidated build. Confirm identity
(`HELLO` returns `device NEZHA2 robot tovez ...`) and run the standard
pre-flight: room lights ON (Shelly `192.168.1.122`), camera calibrated,
AprilTag 1 at world (0,0), tag 52's registration confirmed. Then run
sprint 030's remaining three (of four) deferred hardware acceptance
checks — the fourth (stack canary, item 5B) is deliberately NOT here;
see ticket 014.

1. **Item 1 — bus-ownership guard**: script a wire-issued OTOS read to
   land mid-drive; confirm it no longer corrupts the encoder sample;
   watch `i2cf` across the run (it must not climb).
2. **Item 2 — fiber-identity check**: (a) a button-handler tour during
   a live `RUN` job must not corrupt the shared `lineBuf_`; (b) a
   block-side `startMove()` during a live wire motion obligation must
   be refused (`kBusy`), not silently superseding it.
3. **Item 4 — raw-zero rejection, post-fix**: repeat the cold
   power-up run from ticket 001 on THIS (post-fix) firmware; compare
   directly against ticket 001's pre-fix baseline — no odometry
   position jump in the first ~40 cm on the post-fix run, where the
   pre-fix run (if it showed one) did.

## Acceptance Criteria

- [ ] tovez identifies as running the ticket-008 build (`HELLO`/`ID`
      cited) before any check below is attempted.
- [ ] Item 1: `i2cf` does not climb across a mid-drive OTOS-read
      scenario, capture cited.
- [ ] Item 2: both fiber-identity scenarios behave as designed, capture
      cited for each.
- [ ] Item 4: ticket 001's pre-fix baseline and this run's post-fix
      result are compared explicitly in the closing note, not just
      individually reported — the comparison IS the acceptance
      criterion, per `sprint-030-hardware-acceptance-needs-one-bench-session.md`.
- [ ] Any item that cannot be verified is recorded as `UNVERIFIED` with
      what was tried, per `measurement-citations.md` — never a
      fabricated pass.

## Testing

- **Existing tests to run**: N/A — hardware verification of
  already-tested (host-level) sprint 030 code.
- **New tests to write**: none (host coverage already exists from
  sprint 030; this is the hardware confirmation those host tests
  couldn't provide).
- **Verification command**: N/A (hardware ticket).
