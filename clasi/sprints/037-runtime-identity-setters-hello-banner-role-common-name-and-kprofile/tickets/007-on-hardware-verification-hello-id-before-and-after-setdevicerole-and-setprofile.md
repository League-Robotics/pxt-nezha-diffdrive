---
id: '007'
title: 'On-hardware verification: HELLO/ID before and after setDeviceRole() and setProfile()'
status: open
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '004'
- '005'
- '006'
github-issue: ''
issue:
- high/hello-banner-role-and-common-name-are-hardcoded.md
- high/kprofile-needs-a-runtime-setter.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# On-hardware verification: HELLO/ID before and after setDeviceRole() and setProfile()

## Description

One scripted on-robot session, run by the team-lead directly (per this
project's hardware-ticket convention — not a programmer dispatch
cycle), confirming both new setters actually change the wire output on
real silicon, not just in source-pin tests. Everything upstream of this
ticket (001-006) is host-side; this is the only ticket in the sprint
that touches a real board, and it is what upgrades this sprint's
Success Criteria's on-hardware line from UNVERIFIED to MEASURED.

Follow `.claude/rules/connecting-to-a-robot.md` for how to reach the
assigned board (WiFi TCP via `rogo <name>` is the default carrier;
`tools/wifilink.py --tcp` or `nc <name>.local 7654` also work). The
board for this session is whatever the stakeholder has assigned — do
not assume a specific one from prior sessions (see
`.claude/rules/robot-assignment-is-per-session.md` — no standing
ownership table).

### Session script

1. Build and deploy a firmware image containing tickets 001-003's
   changes (via `tools/make_deploy.py`, per this repo's normal deploy
   path) to the assigned board.
2. Connect and record the BASELINE `HELLO` banner and `ID` reply,
   verbatim, before calling either setter — this is the regression
   check made concrete on real hardware, not just in source-pin tests.
3. Send a test program (or drive the setters directly if the wire
   protocol exposes a way to invoke them without a full TS program —
   check whether `RUN:` or a debug verb reaches them; if not, a small
   `on start` test program calling both setters is the straightforward
   path) that calls `diffDrive.setDeviceRole("TESTROLE", "testbot")`
   and `diffDrive.setProfile("testprofile")`.
4. Record `HELLO` and `ID` AFTER both calls. Confirm:
   - The banner now reads `device TESTROLE testbot <name> <serial>`
     (role and commonName changed, name/serial unchanged from step 2).
   - The `id` reply's `profile` field now reads `testprofile`.
5. **If practical**, also test the "before fiber start" ordering claim
   from tickets 001/002's design (call a setter as literally the first
   statement of `on start`, before anything else, and confirm the
   FIRST banner/`id` reply already reflects it — this is the specific
   race condition the constructor-seeding design exists to avoid). If
   this is not practical to isolate on the available hardware/tooling
   in one session, say so explicitly and record it as still UNVERIFIED
   rather than skipping the record entirely.
6. **If practical**, send an over-length value to one field and confirm
   it is clipped, not garbage/crashed, and that `DBG:role`/
   `DBG:profile` reports the truncation.
7. Record everything in a capture file under `captures/` (this repo's
   convention — see `.claude/rules/measurement-citations.md`: every
   `MEASURED` claim must name its artifact, board, and date).

### What NOT to do

Do not write "MEASURED" anywhere — in this ticket, in `sprint.md`, or
in source comments — without the capture artifact backing it existing
first. If time or hardware access runs out before completing the full
script above, record exactly which steps ran and which did not, and
mark the remainder UNVERIFIED with a one-line note on what would settle
it (per `.claude/rules/measurement-citations.md`'s own guidance: "If
you did not run it, write UNVERIFIED and say what would settle it.").

## Acceptance Criteria

- [ ] A capture file exists under `captures/` recording: the exact
      BASELINE `HELLO`/`ID` output, the exact commands/program sent,
      and the exact AFTER output for both setters, with board name and
      date.
- [ ] The baseline output is confirmed byte-identical to what
      `sendBanner()`/`execId()` produced before this sprint (cross-
      reference against `tests/host/test_wire_grammar.py`'s pinned
      values).
- [ ] The AFTER output shows the new `role`/`commonName` in the banner
      and the new `profile` in the `id` reply, with `name`/`serial`/
      `drivetrain`/`version` unchanged.
- [ ] `sprint.md`'s Success Criteria line about on-hardware confirmation
      is updated to point at this capture file, worded as MEASURED (if
      the full script completed) or UNVERIFIED-with-remainder (if it
      did not), per `.claude/rules/measurement-citations.md`.
- [ ] Steps 5 and 6 (ordering race, truncation-on-hardware) are
      attempted; if not completed, they are explicitly recorded as
      UNVERIFIED rather than silently omitted.

## Testing

- **Existing tests to run**: none (this ticket is on-hardware
  verification, not a host test change).
- **New tests to write**: none — this ticket produces a capture
  artifact, not a test file.
- **Verification command**: N/A. This ticket's own output IS the
  verification.
