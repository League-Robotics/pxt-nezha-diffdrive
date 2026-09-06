---
id: '006'
title: One sequencer in tools/link.py; one relay address
status: in-progress
use-cases:
- SUC-001
- SUC-004
depends-on:
- '003'
- '005'
github-issue: ''
issue: tools-consolidation-inprocess-aprilcam-wrap-link-layer.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# One sequencer in tools/link.py; one relay address

## Description

The sequenced-wire protocol is implemented **four times**, and the relay
address is chosen in **three different places, one of them wrong**.

Implementations, verified against the tree 2026-09-06:

| where | what it is |
|---|---|
| `tools/robotlink.py` `Link` | serial + relay handshake, sequence ids, `send_until`, `sync_seq`, `hello` |
| `tools/fieldlink.py` `_SequencedLink` (+ `FieldLink`, `TcpFieldLink`) | its own `seqd`, one-letter `s` receiver, semicolon-joined statements |
| `tools/wire_acceptance.py` `UsbLink` / `GautiLink` / `RadioLink` / `TcpLink` / `WifiLink` | a fifth `read` that is the same 14 lines as `fieldlink`'s |
| `tests/calibration/turn_calibration.py` `Link` / `RelayLink` | a fourth `seqd` |

Relay addresses: `fieldlink.FieldLink` uses host `torture` and takes
`(channel, group)`; `wire_acceptance.RadioLink` uses host
`192.168.1.12` and sends `!CG {channel} 10` -- **group hard-coded to
10**, which cannot be right, since the fleet table in
`.claude/rules/playfield-testing.md` has groups 43, 60, 108 and 114.
`robotlink.radio_address(robot)` derives the pair from the board name and
is the correct one (it replaced the stale `ZAVAZ_CHANNEL`/`ZAVAZ_GROUP`
before this sprint).

`FieldLink` also skips the `!ECHO OFF` / `!MODE RAW250` / `!P 7` setup
that `robotlink` sends. Whichever is right, one of them is wrong.

## Acceptance Criteria

- [ ] `tools/link.py` exists and owns **one** `Sequencer` and **one**
      line-reassembly buffer. Its scope is the protocol only -- id
      allocation, resend-with-the-same-id, `ack`/`nack`/`err` parsing,
      line buffering, and the sequenced/unsequenced split. **Transports
      stay where they are**: each carrier keeps its own small class for
      how a socket or serial port is opened, tuned and closed.
- [ ] `robotlink.Link`, `fieldlink._SequencedLink`, `wire_acceptance`'s
      TCP relay links and `tests/calibration/turn_calibration.Link` all
      use it. The `robotlink` sequencer is the one that survives -- it is
      the tested one (`sync_seq`'s `nack N -> N-1`, `send_until`'s
      format-once-then-resend, `hello()` as a session reset).
- [ ] No relay group is hard-coded anywhere.
      `wire_acceptance.RadioLink`'s `!CG {channel} 10` is replaced by
      `robotlink.radio_address(robot)`. **This is a behaviour change,
      not a refactor** -- flag it in the ticket record so a reviewer
      notices (sprint Open Question 2).
- [ ] The relay setup sequence (`!ECHO OFF` / `!MODE RAW250` / `!P 7`)
      is settled: either every relay carrier sends it or none does, with
      the reason written on the code. Do not leave the disagreement.
- [ ] **`tools/rogo/` is untouched and gains no import from `tools/`.**
      Its whole premise, in its own `DESIGN.md`, is "nothing installed
      but Python" -- stdlib-only, `pipx install` straight from this
      checkout or from git. An import of `tools/link.py` breaks that.
      Its duplicate is deliberate; label it as such in both
      `tools/DESIGN.md` and `tools/rogo/DESIGN.md` (ticket 012 does the
      former; do the `rogo` note here so it lands with the change it
      describes).
- [ ] `tests/calibration/test_turn_calibration_gates.py` stays green --
      the calibration programs are the sprint-031 bench workflow and
      must keep working.
- [ ] `tests/tools/test_rogo.py` passes unchanged.

## Implementation Plan

### Approach

1. Write `tools/link.py` first, with tests, before touching any caller.
   Take `robotlink`'s implementation as the starting point.
2. Migrate callers one at a time, running that caller's tests after each.
3. `wire_acceptance.py` is the riskiest caller: it is the acceptance
   harness itself, it has five link classes, and it distinguishes
   PASS/FAIL/BLOCKED with distinct exit codes. Preserve that behaviour
   exactly. Its `UsbLink`/`GautiLink` are serial, not relay -- migrate
   only what genuinely shares the protocol, and say in the ticket record
   what you left alone and why.
4. `tests/calibration/turn_calibration.py` already does
   `sys.path.insert(..., 'tools')` and imports `field`; adding
   `link` follows the same established path.

**Do not build an abstraction wider than the four callers need.** The
review's own remedy names `SerialLink`, `RelayLink(host, port, channel,
group)` and one `Sequencer`; that is the ceiling, not a floor.

### Files

- `tools/link.py` (new).
- `tools/robotlink.py`, `tools/fieldlink.py`, `tools/wire_acceptance.py`,
  `tests/calibration/turn_calibration.py`.
- `tools/rogo/DESIGN.md` -- the deliberate-duplicate note.
- `tests/tools/test_link.py` (new), `tests/tools/test_robotlink.py`,
  `tests/tools/test_fieldlink.py`.

Also: while in `robotlink.py`, apply the review's comment-hygiene
replacements #2 and #3 (the `sync_seq` and `hello` docstrings, 23 and 30
lines of sprint-024 history). The review supplies both replacement texts
verbatim.

### Re-anchoring

Line numbers in the issue are from 2026-09-02 and predate
`fieldlink.TcpFieldLink` and `tools/wifilink.py`. Grep for
`class _SequencedLink`, `def seqd`, `!CG`, `def read`.

### Depends on

Tickets 003 (deletions) and 005 (the verb set the sequencer keys on).

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_robotlink.py
  tests/tools/test_fieldlink.py tests/tools/test_rogo.py
  tests/calibration/test_turn_calibration_gates.py -q` (foreground,
  scoped).
- **New tests to write**: `tests/tools/test_link.py` for the shared
  sequencer -- first id is 1; a resend reuses its id; a fresh id on a
  resend is a defect and is asserted against; `nack N` sets the next id
  to `N-1`; `hello()` resets to 0; partial lines reassemble across reads;
  an unsequenced verb goes out bare. Use an injected fake socket, not a
  real one. Plus a test that no relay group literal `10` survives in
  `wire_acceptance.py`.
- **Verification command**: `uv run pytest tests/tools
  tests/calibration -q`
