---
id: '002'
title: 'Host: open_link() resyncs via HELLO, and sync_seq() fixes its ack/nack asymmetry'
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: radio-link-wedges-on-a-sequence-gap-and-reconnect-cannot-heal-it.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host: open_link() resyncs via HELLO, and sync_seq() fixes its ack/nack asymmetry

## Description

A robot whose radio (or serial) wire handler has stalled on a sequence
gap streams `nack <N> 0 none` at the reliability cadence and, today,
nothing in `tools/` can clear it short of a robot reboot. Two bugs in
`tools/robotlink.py`, both inside the `Link`/`open_link()` machinery,
combine to cause this:

1. **`sync_seq()` (lines 123-142) is off by one on a `nack` line.** It
   matches `^(?:ack|nack)\s+(\d+)` and sets `self._seq = int(m.group(1))`
   for *either* verb. That's correct for `ack N` ("N was accepted," so
   the next id to allocate is N+1 — `_format()`'s `self._seq += 1`
   handles that). It's wrong for `nack N`, which means "send me N next":
   the next id to allocate must be N itself, so `_seq` must land on
   `N - 1`. Reading `nack 5` today sets `_seq = 5`, and the next
   `_format()` call allocates `#6` — a fresh gap on the same wound. This
   is why a reconnect into an already-stalled robot re-wedges itself.

2. **`open_link()` (lines 208-244) never sends `HELLO`.**
   `WireHandler::handleHello()` (`src/comms/wire_handler.cpp:640-652`) is
   the protocol's own designated escape hatch: it resets `expectedNext_`
   to 1 and clears `gapOutstanding_` on whichever handler received it,
   without touching motion-completion state (`lastDone()`/
   `lastDoneReason()` are untouched). `open_link()` calls `sync_seq()` on
   both carriers today and never sends `HELLO` on either — the one thing
   that can clear a stalled gap without a reboot is never used.

**Fix both, and get their composition right — this is the part that
needs care, not just stacking the two fixes literally:**

- Fix `sync_seq()`'s branch: capture which verb matched (not just the
  digits), and set `_seq = N` for an `ack`, `_seq = N - 1` for a `nack`.
  This fix stands on its own merits regardless of anything else — it is
  wrong today independent of sprint 024's other ticket.
- Make `open_link()` send `HELLO` and consume its banner reply before
  anything else, on both the USB branch and the zavaz-radio branch (after
  the relay's own `!ECHO OFF`/`!MODE RAW250`/`!CG`/`!P`/`!GO` control-plane
  setup on the radio side — those are relay commands, not robot wire
  commands, and must still run first).
- **Do not simply call the (now bug-fixed) `sync_seq()` right after
  `HELLO` and assume that's the whole fix.** Ticket 001 (this sprint)
  removes the firmware's free-running reliability emission. Once that
  lands, there is normally **nothing** for `sync_seq()`'s passive
  read-a-line loop to find immediately after `open_link()` sends `HELLO`
  — no keepalive streams anymore. A naive "`HELLO` then `sync_seq()`"
  composition would silently degrade into a dead wait for `sync_seq()`'s
  full default timeout (1.5 s) on every single connect, finding nothing,
  before falling through. It happens to leave `_seq` at its harmless
  constructor default of `0` (which is exactly correct after a `HELLO`
  reset — a fresh `Link` already initializes `self._seq = 0`, matching a
  robot at `expectedNext_ = 1`) — but relying on a timeout to arrive at
  the right answer by accident is not a fix worth shipping. Send `HELLO`,
  consume its banner (confirm it looks like `device NEZHA2 ...`), and
  then establish the resync state directly — whether that's a plain
  `self._seq = 0` assignment with a comment explaining why (`HELLO`'s own
  contract guarantees `expectedNext_ = 1`), or a `sync_seq()` variant that
  does not block for its full default timeout when nothing arrives, is
  the implementer's call. What matters is that `open_link()` must not
  hang on a read that no longer has anything to answer it.

See `sprint.md`'s Architecture → Design Rationale, third decision
("`open_link()` sends `HELLO` and then treats the connection as reset,
rather than calling the old `sync_seq()` and trusting whatever it
reads"), for the full reasoning behind this composition.

## Acceptance Criteria

- [x] `sync_seq()`'s regex match distinguishes `ack` from `nack`: an
      `ack N` line sets `_seq = N`; a `nack N` line sets `_seq = N - 1`.
      Both cases are covered by a direct unit test, independent of
      `open_link()`.
- [x] `open_link()` sends `HELLO` and consumes its banner reply before any
      sequenced command is sent, on both the USB branch and the radio
      (zavaz) branch — after the radio branch's existing relay
      control-plane setup (`!ECHO OFF`/`!MODE RAW250`/`!CG`/`!P`/`!GO`),
      which must still run first.
- [x] After `open_link()` returns, `link._seq == 0`, matching the robot's
      guaranteed post-`HELLO` state — without `open_link()` blocking for
      `sync_seq()`'s full default timeout waiting on a keepalive line that
      no longer exists once ticket 001 lands.
- [x] `tests/tools/test_robotlink.py` (new file — none exists today) pins
      `sync_seq()`'s two branches against a fake serial-like object: feed
      it `ack 7 0 none` and separately `nack 5 0 none`, assert `_seq`
      lands on `7` and `4` respectively.
- [x] `tests/tools/test_robotlink.py` pins that `open_link()` writes
      `HELLO` before the first sequenced (`#`-suffixed) verb, on both the
      USB and radio code paths (fake port; assert on write order/content).
- [x] `tests/tools/test_robotlink.py` proves the sprint's own pinned
      success criterion: a fake link whose next relevant reply is `nack 5
      0 none` yields `#5` as the next allocated command id, not `#6`.
- [x] `robotlink.py`'s own top-of-file measured-comment (the "72
      keepalive acks only" example, lines ~82-89) is corrected or
      annotated as describing pre-sprint-024 behavior, so it doesn't read
      as a current-behavior claim.

## Implementation Notes

**`sync_seq()`** (`tools/robotlink.py`): the regex now captures the verb
(`^(ack|nack)\s+(\d+)`) and branches: `_seq = n` for `ack`, `_seq = n - 1`
for `nack`. Docstring rewritten to explain the ack/nack asymmetry and to
record explicitly that `open_link()` no longer calls this method (see
below) — the fix stands on its own for any future caller reading a live
ack/nack line outside the connect path.

**`open_link()` / the HELLO composition**: added a new `Link.hello()`
method rather than wiring the bug-fixed `sync_seq()` directly into
`open_link()` — this is the trap the ticket calls out. `hello()` sends
`HELLO` (unsequenced — `_format()` already leaves it untouched since
`HELLO` is not in `_V6_VERBS`), best-effort reads for a `device `-prefixed
banner line within a short bound (`timeout=1.0`, deliberately less than
`sync_seq()`'s `1.5` default — pinned by
`test_hello_timeout_default_is_shorter_than_sync_seq_default`), and then
unconditionally sets `self._seq = 0` — not conditioned on whether a
banner was actually seen, since `handleHello()`
(`src/comms/wire_handler.cpp:640-652`) resets the robot's
`expectedNext_` to 1 the instant it receives the line, independent of
whether the host manages to read the reply back. `open_link()` calls
`link.hello()` on both the USB and radio branches, on the radio branch
strictly after the existing `!ECHO OFF`/`!MODE RAW250`/`!CG`/`!P`/`!GO`
relay control-plane setup. `open_link()` itself never calls
`sync_seq()` at all now — pinned directly (not just by elapsed time) in
`test_open_link_never_calls_sync_seq_and_does_not_block_on_it`, which
monkeypatches `Link.sync_seq` to record any call and asserts zero calls,
plus a wall-clock assertion (`elapsed < 1.5`) as a second, honest check
that no other blocking path was introduced.

**Top-of-file measured-comment**: annotated in place (kept the original
board/date/figures — 2026-08-25, vevov, "72 keepalive acks", "72 `t`
frames + 4 `thdr` frames" — per `.claude/rules/measurement-citations.md`)
as `PRE-SPRINT-024`, explaining that the "72 keepalive acks" came from
the free-running beacon ticket 001 deleted, not from any reply to the
line actually sent.

**Tests** (`tests/tools/test_robotlink.py`, new): a `FakePort` double
(write()/readline()/reset_input_buffer()/close(), extending
`test_tour_capture.py`'s existing `link.p`-level double with a `writes`
log) backs every test — no real serial/radio anywhere. Covers: both
`sync_seq()` branches individually plus the relay `'< '`-prefix strip;
the sprint-pinned `nack 5` → `#5` (not `#6`) case; `open_link()`'s write
order on both carriers (HELLO after radio's relay setup, before the
first `#`-suffixed verb; USB the same, without the relay preamble);
HELLO's own unsequenced arity on both carriers; `_seq == 0` after
`open_link()` both with and without a banner actually arriving; and the
no-`sync_seq()`-call/no-block pin described above. 15 tests total in the
new file (`uv run pytest tests/tools/test_robotlink.py --collect-only -q`).

**Verification run this session**: `uv run pytest tests/tools/` — 224
passed (the full `tests/tools/` directory: pre-existing files plus the
15 new ones); `uvx ruff check tools tests` — all checks passed. No
hardware attached this session (`mbdeploy probe` showed `CONN: no` on
all boards) — this ticket's fixes and tests are host-side only and
require none; the bench/playfield reconnect-recovery scenario in
SUC-002's Main Flow remains UNVERIFIED against real hardware and would
be settled by: stalling a radio handler's sequence (send an out-of-order
`#N`), reconnecting `open_link(radio=True)`, and confirming the next
`#1` command is accepted rather than nacked.

## Implementation Plan

**Approach**: In `sync_seq()`, capture the verb (`ack` vs `nack`) in the
same regex match (e.g. `re.match(r'^(ack|nack)\s+(\d+)', t)`) and branch
on it when setting `self._seq`. In `open_link()`, move the `HELLO` send +
banner consumption to run immediately after the port/relay is ready for
robot-directed traffic (right where `sync_seq()` is called today), and
replace the direct reliance on `sync_seq()`'s passive read with the
HELLO-based resync described above. Reuse `Link.lines()` (already
handles the relay's `< ` prefix stripping) to read the banner.

**Files to modify**: `tools/robotlink.py` (`sync_seq()`, `open_link()`,
and the file's own top-of-file docstring/measured-comment).

**Files to create**: `tests/tools/test_robotlink.py` — a fake
serial-object test double (check `tests/tools/test_run_verbs.py` and
other `tests/tools/` files for this project's existing fake-port/
monkeypatch conventions before inventing a new one) covering the
acceptance criteria above.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` (scoped to the
  module this ticket touches).
- **New tests to write**: `tests/tools/test_robotlink.py`, per Acceptance
  Criteria above — `sync_seq()`'s ack/nack branches, `open_link()`'s
  HELLO-before-anything-else ordering on both carriers, and the
  `nack 5` → `#5` (not `#6`) pinned case.
- **Verification command**: `uv run pytest tests/tools/`; `uvx ruff check
  tools tests`.
