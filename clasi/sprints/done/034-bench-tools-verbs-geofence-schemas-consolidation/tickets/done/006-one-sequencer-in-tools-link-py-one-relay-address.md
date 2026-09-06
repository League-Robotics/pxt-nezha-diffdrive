---
id: '006'
title: One sequencer in tools/link.py; one relay address
status: done
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

- [x] `tools/link.py` exists and owns **one** `Sequencer` and **one**
      line-reassembly buffer. Its scope is the protocol only -- id
      allocation, resend-with-the-same-id, `ack`/`nack`/`err` parsing,
      line buffering, and the sequenced/unsequenced split. **Transports
      stay where they are**: each carrier keeps its own small class for
      how a socket or serial port is opened, tuned and closed.
- [x] `robotlink.Link`, `fieldlink._SequencedLink`, `wire_acceptance`'s
      TCP relay links and `tests/calibration/turn_calibration.Link` all
      use it. The `robotlink` sequencer is the one that survives -- it is
      the tested one (`sync_seq`'s `nack N -> N-1`, `send_until`'s
      format-once-then-resend, `hello()` as a session reset).
- [x] No relay group is hard-coded anywhere.
      `wire_acceptance.RadioLink`'s `!CG {channel} 10` is replaced by
      `robotlink.radio_address(robot)`. **This is a behaviour change,
      not a refactor** -- flag it in the ticket record so a reviewer
      notices (sprint Open Question 2).
- [x] The relay setup sequence (`!ECHO OFF` / `!MODE RAW250` / `!P 7`)
      is settled: either every relay carrier sends it or none does, with
      the reason written on the code. Do not leave the disagreement.
- [x] **`tools/rogo/` is untouched and gains no import from `tools/`.**
      Its whole premise, in its own `DESIGN.md`, is "nothing installed
      but Python" -- stdlib-only, `pipx install` straight from this
      checkout or from git. An import of `tools/link.py` breaks that.
      Its duplicate is deliberate; label it as such in both
      `tools/DESIGN.md` and `tools/rogo/DESIGN.md` (ticket 012 does the
      former; do the `rogo` note here so it lands with the change it
      describes).
- [x] `tests/calibration/test_turn_calibration_gates.py` stays green --
      the calibration programs are the sprint-031 bench workflow and
      must keep working.
- [x] `tests/tools/test_rogo.py` passes unchanged.

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

## Implementation Record

### `tools/link.py`'s public surface

- `RELAY_HOST = 'torture'`, `RELAY_PORT = 8760` -- the relay pool, named
  once. It was spelled three ways, one of them the bare IP
  `192.168.1.12`.
- `relay_setup_lines(channel, group) -> tuple` -- `('!ECHO OFF',
  '!MODE RAW250', '!CG <ch> <grp>', '!P 7')`. `!GO` is deliberately
  excluded (it switches the relay into the data plane and each carrier
  follows it with its own, longer settle).
- `LineBuffer` -- `feed(chunk) -> list[str]`, `line(chunk) -> str|None`,
  `reset()`. Newline reassembly across arbitrary read boundaries, the
  relay's `'< '` receive prefix stripped, blank lines dropped.
- `Sequencer(sequenced_verbs=None)` -- `seq` (the last id handed out),
  `is_sequenced(line)`, `format(line, force=False)`, `reset()`,
  `observe_reply(line)` (`ack N` -> N, `nack N` -> N-1).

Stdlib-only, deliberately, so `tests/host/` and `tests/calibration/`
import it on a machine with no pyserial and no robot.

### Migrated, and what was left alone

| caller | what it now shares | what stayed |
|---|---|---|
| `robotlink.Link` | `Sequencer(_V6_VERBS)`, `LineBuffer`, `relay_setup_lines()` | the pyserial port, `open_link()`'s per-carrier handshake and settles, `send_until`'s retry shape |
| `fieldlink._SequencedLink` | `Sequencer()` (`format(force=True)`), `LineBuffer`, `relay_setup_lines()` | the socket, the lossy-carrier retry loop, `unseq`/`seqd`'s reply patterns |
| `wire_acceptance` `UsbLink`/`RadioLink`/`TcpLink` | `LineBuffer`; `RadioLink` also `relay_setup_lines()` + `radio_address()` | every `ask()`/`read()` timing, and **no `Sequencer`** |
| `turn_calibration.Link`/`RelayLink` | `Sequencer()`, `LineBuffer`, `relay_setup_lines()` | the background reader thread and its timestamped line log, `wait_for`/`since` |

Left alone, with the reason:

- **`wire_acceptance` uses no `Sequencer`.** Its whole job is to probe
  the sequencing contract from OUTSIDE, so it hand-writes the ids its
  cases need -- `#0`, a `#9` gap, the reserved ceiling `#4294967295`, a
  resend of `#2` -- and tracks the robot's counter from what the robot
  actually says (`next_id()`). A `Sequencer` would allocate those ids
  instead and there would be nothing left to test. It shares the line
  reassembly and the relay setup, which is the duplication the review
  actually named ("the same 14 lines").
- **`wire_acceptance.GautiLink`** keeps its hand-written reassembly:
  that loop runs on the Pi, inside the `HELPER` source string uploaded
  over ssh, where nothing from this checkout exists. Shipping `link.py`
  alongside it to save fourteen lines would add a second file to keep
  in step over ssh.
- **`wire_acceptance.WifiLink`** delegates to `tools/wifilink.py`'s own
  `TcpLink`/`WifiLink`; that module is not in this ticket's scope.
- **`robotlink.WifiSerial.readline()`** keeps its own byte loop: it must
  return a RAW line with its trailing newline to wear the pyserial
  shape `Link` calls, not a stripped `str`.
- **`tools/rogo/`** is untouched and imports nothing from `tools/`
  (pinned by `test_rogo_imports_nothing_from_tools`); the deliberate-
  duplicate note is now in `tools/rogo/DESIGN.md` and `tools/DESIGN.md`.
- **`_V6_VERBS` stays a literal in `tools/robotlink.py`.**
  `tests/host/test_wire_constants_drift.py::_robotlink_v6_verbs()`
  `ast.literal_eval`s it out of that file by name, and its own failure
  message says "ticket 006 and this drift test both key on that name".
  `Sequencer` therefore takes the verb set as a constructor argument;
  robotlink is also the only caller that needs to CLASSIFY a line at
  all (the other three name the verb kind at the call site). Drift test
  run and green: 36 passed.

### BEHAVIOUR CHANGES -- for a reviewer, not refactors

1. **`wire_acceptance.RadioLink`'s relay address** (sprint.md Open
   Question 2). Was `!CG {channel} 10`, group hard-coded to 10, from
   `--radio CH` (an int channel). Now `--radio ROBOT` (a board name),
   resolved through `robotlink.radio_address(robot)` -- the explicit
   `field_calibration.json` override, else the base-5 name derivation
   the fleet was addressed with. The host also moved from the bare IP
   `192.168.1.12` to `torture`, the name the other two relay carriers
   already used. **The `--radio` CLI argument changed meaning**: an old
   invocation `--radio 4` now fails loudly (`4` is not a valid 5-letter
   micro:bit name) rather than tuning to 4/10.
2. **The same hard-coded group, in the second place it lived.**
   `turn_calibration.robot_radio()` read `c.get('radio_group', 10)`.
   The default is gone -- a missing key now raises `SystemExit` naming
   the config file. Every robot config in
   `radio-robot-lib/config/robots/` sets both keys, so nothing loses a
   working path.
3. **The relay setup sequence is settled: ALL FOUR LINES, on EVERY
   relay carrier**, in `robotlink`'s order. `fieldlink.FieldLink` and
   `wire_acceptance.RadioLink` gain `!ECHO OFF`/`!MODE RAW250`/`!P 7`;
   `turn_calibration.RelayLink` gains `!MODE RAW250`/`!P 7`. The reason
   is written on `link.relay_setup_lines()`: the relay PERSISTS its
   config across resets (`!DEFAULTS` exists precisely to clear it --
   `../microbit-radio-relay/README.md` command summary), so "a fresh
   board defaults to RAW250/power 7" describes a board nobody has
   configured, not the shared hand-driven relays these carriers get; a
   previous session's `!MODE MAKECODE` or `!P 3` is otherwise inherited
   in silence and the robot simply never answers. And `!ECHO` is a
   radio TRANSPONDER ("bounce received messages back"), not terminal
   echo, so leaving it unset is a live radio behaviour, not cosmetics.
4. **`LineBuffer` strips `'< '` unconditionally**, including on the two
   `wire_acceptance` carriers (`UsbLink`, `TcpLink`) that did not strip
   it before. No robot line begins with `'< '`, so nothing is lost, and
   the alternative was a per-carrier flag the carriers disagreed about
   -- the defect being removed. No assertion in the harness matches on
   a `'< '` prefix, so PASS/FAIL/BLOCKED is unaffected.

`wire_acceptance.py`'s three outcomes and their exit codes are
otherwise untouched: `3` for no HELLO banner, `2` for a wedged adapter
or any BLOCKED, `1` for any FAIL, `0` otherwise; and both sprint-033
checks are unchanged in place (`GET rebase #3` -> `ack 3` + `err 12`;
`STOP #4294967295` -> `nack` + `err 3`, then `STOP #1` -> `ack 1`).

### Comment hygiene

Review replacements #2 (`sync_seq`, 23 lines of sprint-024 history) and
#3 (`hello`, 30 lines) applied verbatim from
`docs/code-review/2026-09-02/raw/tools-and-tests.md`. `open_link()`'s
trailing comment used to say "see `Link.hello()`'s own docstring for
why" -- that reasoning no longer lives there, so the comment was made
self-contained rather than left pointing at nothing.

### Verification

`uv run pytest tests/tools tests/calibration -q` -> **541 passed** (of
which `test_link.py` 33 new, `test_robotlink.py` 31,
`test_fieldlink.py` 5, `test_rogo.py` and
`test_turn_calibration_gates.py` unchanged and green).
`uv run pytest tests/host/test_wire_constants_drift.py -q` -> 36
passed. `ruff check` clean on every touched file. No hardware was
touched, so there is no MEASURED claim anywhere in this change; every
link test drives an injected fake socket or fake serial port.
