---
id: '004'
title: 'HARDWARE: measure credential flash region survival across reflash and power
  cycle'
status: done
use-cases:
- SUC-003
depends-on:
- '003'
github-issue: ''
issue: wifi-credentials-live-in-flash-not-in-the-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# HARDWARE: measure credential flash region survival across reflash and power cycle

## Description

**This is the sprint's main risk, and it is a hardware question, not a
header-reading one** (sprint architecture Risks / Design Rationale #1 /
Open Question 1). Whether the candidate flash page ticket 002 chose
actually survives `mbdeploy deploy` (which erases pages) and a power
cycle depends on exactly which pages that erase touches and what
PXT/MakeCode itself already keeps in flash — this can only be answered
by flashing a real board, writing a record, reflashing, and reading it
back.

**Per `.claude/rules/hardware-tickets-run-them-yourself.md`-equivalent
project convention (see the team-lead's memory: "Hardware tickets: run
them yourself"): this ticket's on-robot steps are run by the team-lead
directly, as one scripted session, not dispatched through repeated
programmer cycles.** The programmer-facing part of this ticket (if any
scripting/tooling is needed to make the check repeatable) should be
prepared so the team-lead can execute it in one pass.

**Board**: gopiv, reachable via Pi `null` per the team-lead's own
session notes — `mbdeploy deploy --remote gopiv` /
`mbdeploy connect --remote gopiv`. Its Nezha brick was unpowered as of
2026-09-09, so motion commands are unavailable — irrelevant here, since
this check only needs WiFi and the wire, not motion.

**Procedure**:
1. Build and flash firmware containing ticket 002's `WifiCredentialStore`
   and ticket 003's `WIFICRED` verb onto gopiv (`mbdeploy deploy --remote gopiv`).
2. Connect (`mbdeploy connect --remote gopiv` or the WiFi/USB carrier
   per `.claude/rules/connecting-to-a-robot.md`) and issue
   `WIFICRED SET 0 <test-ssid> <test-password>` with an OBVIOUSLY FAKE
   credential (never a real network's password — this artifact will be
   captured and must not contain anything sensitive).
3. Read back via bare `WIFICRED` — confirm slot 0 shows occupied,
   correct SSID, `haspw=1`.
4. **Power-cycle test**: power-cycle the board (unplug/replug power,
   NOT just a serial reconnect — see `.claude/rules/playfield-testing.md`'s
   distinction between a real power event and a session artifact).
   Reconnect, read back via `WIFICRED`. Record pass/fail.
5. **Reflash test**: `mbdeploy deploy --remote gopiv` again (same or a
   trivially rebuilt hex — the point is the erase, not a code change).
   Reconnect, read back via `WIFICRED`. Record pass/fail.
6. Capture the full session transcript (commands + replies) to
   `captures/wifi-credential-flash-survival-<date>/notes.md`
   (`captures/` is gitignored — `git add -f` if the artifact needs to be
   committed, per project convention) — this is the artifact this
   ticket's `MEASURED` claims cite.
7. **If either check fails**: do NOT silently narrow scope. Report to
   the stakeholder immediately. The sprint architecture's Open Question
   1 already names the fallback: pick a different candidate page (loop
   back to ticket 002 with a new address) or, if no address survives
   reflash, document R3 as power-cycle-only and get that narrowing
   explicitly signed off — R3 as written in the linked issue requires
   BOTH.

## Acceptance Criteria

- [~] DEFERRED, not measurable from here (artifact path cited, per
      `.claude/rules/measurement-citations.md`): the credential record
      written in step 2 is read back correctly after a power cycle.
- [x] MEASURED — **FAIL, and that is the finding**: read back after an
      `mbdeploy deploy` reflash — the sprint's headline risk, settled
      here, not assumed.
- [x] If either measurement is a FAIL, this is reported to the
      stakeholder as a finding (not silently patched around), and
      either a new candidate page is chosen (reopening ticket 002) or
      R3's scope is explicitly narrowed with stakeholder sign-off
      before any downstream ticket (005, 006) proceeds on the
      assumption that R3 is fully met.
- [x] The test credential used is obviously fake, never a real
      network's password, in every captured artifact.
- [x] No passphrase — fake or otherwise — appears in cleartext in any
      artifact this ticket produces beyond what's operationally
      necessary to prove the round-trip (the captured transcript may
      show the fake SSID and a `haspw=1` flag; it should not need to
      show the fake password's actual text either, since `WIFICRED`'s
      own enumeration never returns it — if some intermediate debug
      step DOES surface it, that's itself a finding to report, not to
      quietly work around).

## Implementation Plan

**Approach**: This ticket is primarily an on-hardware measurement
session, not a code-writing ticket. Any code involved is either
already complete (tickets 002/003) or a small helper script to make
the session's commands scriptable/repeatable (optional, at the
team-lead's discretion).

**Files to create**: `captures/wifi-credential-flash-survival-<date>/notes.md`
(the measurement artifact).

**Testing plan**: The hardware session IS the test — no host test can
substitute for it (this is exactly why the sprint's Test Strategy calls
this out as un-satisfiable by host tests).

**Documentation updates**: Record the outcome (page address confirmed,
or the narrowed/relocated decision) in this ticket's own closing notes
so ticket 007's docs pass has the final, confirmed answer to write
down.


## Results — team-lead, 2026-09-09/10

Artifacts: `captures/wifi-credential-store-20260909/` (`notes.md` indexes
them). Board gopiv, fake credential `TestNet038` / a fake passphrase.

**Reflash: FAIL — a deploy MASS-ERASES, so credentials do not survive it.**
A store written before `mbdeploy deploy --remote gopiv` enumerated empty
afterwards. The programmed range (105 sectors, 0x68000 bytes) never
reaches the store page at `0x0007D000`, so this is pyOCD's chip
mass-erase, not overwrite. Reported to the stakeholder in the interim
release summary; **R3 is narrowed accordingly to "survives a power
cycle", not "survives a reflash"**, and the stakeholder's answer was to
keep going. The operational rule — *provision AFTER flashing* — is in
the capture notes, the release notes, the merge commit, and the
instructions handed to the consuming project. Ticket 002's page address
is NOT reopened: no page survives a mass erase, so no other candidate
would have done better.

**Power cycle: DEFERRED, not measurable from this session.** It needs a
reboot that is not a reflash, and there was no way to produce one
remotely: the wire vocabulary has no reset/reboot verb, gopiv's Nezha
brick is switched off so power cannot be cycled through it, and the
`null` Pi's serial daemon holds the port open continuously so the
open-the-port-resets-the-target behaviour never fires. The first person
to power-cycle a provisioned board settles it; the expected reading
(`credsrc=2` and a join on the stored SSID) is written down in the
capture notes and in the consuming project's instructions, flagged as
unconfirmed. **A `REBOOT` wire verb would close this hole** — filed as
its own issue.

**Two defects found by this run, both fixed** (they are why the first
two attempts failed): the vendored `MicroBitFlash.h` documents
`flash_write()` as returning non-zero on success while the code returns
`MICROBIT_OK` (0), and this target's newlib-nano printf has no `%zu`.
Details in the capture notes.
