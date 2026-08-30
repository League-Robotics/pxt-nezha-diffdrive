---
id: '004'
title: 'robotlink.py and wire_acceptance.py: derive relay tuning'
status: done
use-cases: []
depends-on:
- '001'
github-issue: ''
issue: derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# robotlink.py and wire_acceptance.py: derive relay tuning

## Description

Two host tools still hand-dial the relay to the legacy `(4, 10)` pair
instead of deriving it from `tools/radio_address.py` (ticket 001). Fix
both; they have different shapes because they know different things about
which robot they're talking to.

**`tools/robotlink.py`** is vevov-specific throughout (its own module
docstring says "zavaz is vevov's relay") — `open_link(radio=True)` is
called from ~10 tools with no robot name passed at all, always implicitly
meaning vevov. `ZAVAZ_CHANNEL = 4` / `ZAVAZ_GROUP = 10` are module-level
literals it sends via `!CG` at line ~323.

**`tools/wire_acceptance.py`**'s `RadioLink` is fleet-generic — its
`--radio CH` flag takes a bare channel integer for "the torture relay
pool" (any robot reachable there, not just vevov), and hardcodes group 10
at line ~158 (`f'!CG {channel} 10'`).

**Important asymmetry to design around**: group is **not** a function of
channel alone. Per `docs/radio-addressing.md`, 125 names share each
channel (`channel` only fixes `n % 25`; `group` depends on `n / 25`, which
varies across those 125 names). So `wire_acceptance.py`'s existing
`--radio CH` contract (channel only, no robot identity) has no way to
derive a *specific* robot's group from `CH` alone — deriving the pair
requires the robot's **name**, not its channel number. Do not attempt to
invert channel-only back to a group; add a name-based path instead and
keep the raw channel path for un-migrated/manual dialing (which is what
group 10 is reserved for — see `docs/radio-addressing.md`'s reserved-values
table).

## Acceptance Criteria

### `tools/robotlink.py`

- [x] `ZAVAZ_CHANNEL` and `ZAVAZ_GROUP` module-level constants are removed.
- [x] `open_link()` gains a `robot=` parameter (default `'vevov'`, so the
      ~10 existing call sites that pass `radio=True` with no robot name —
      `pivot_truth.py`, `tour_closedloop.py`, `tour_square.py`,
      `tour_watch.py`, `tour_run.py`, `tour_practice.py`, `truth_check.py`,
      `turn_sweep.py`, and the `radio=a.radio`-style calls in
      `arc_capture.py`/`otos_levercal.py`/`rotation_check.py`/
      `tour_capture.py` — keep working unchanged and still mean vevov).
- [x] The `!CG` line at ~323 derives `(channel, group)` from `robot` via
      `tools/radio_address.py`'s `name_to_address()` instead of the
      removed constants.
- [x] The module docstring's `# zavaz relay, channel 4` comment and the
      top comment above `ZAVAZ_CHANNEL`/`ZAVAZ_GROUP` (`# zavaz is vevov's
      relay (channel 4). getez lives on channel 3 and belongs to another
      robot -- never retune it here.`) are updated to describe the derived
      value instead of the hardcoded one — keep the getez warning, it's a
      real playfield-safety rule (`.claude/rules/playfield-testing.md`),
      not a stale artifact of the old scheme.
- [x] `tests/tools/test_robotlink.py`'s assertion at ~line 183
      (`f'!CG {robotlink.ZAVAZ_CHANNEL} {robotlink.ZAVAZ_GROUP}\n'`) is
      updated to assert against the derived pair for `'vevov'` instead of
      the removed constants (`37`/`43` per `docs/radio-address-vectors.json`).

### `tools/wire_acceptance.py`

- [x] `RadioLink.__init__` gains an explicit `group=10` parameter (default
      preserves today's behavior exactly for any existing raw-channel
      caller), and the `!CG` line at ~158 uses it instead of the literal
      `10`.
- [x] `main()`'s CLI gains a robot-name-based way to reach `RadioLink` with
      a derived pair — add `--robot NAME` to the existing
      `--usb`/`--gauti`/`--radio` mutually-exclusive group (`g` at ~line
      399); when given, resolve `(channel, group)` via
      `tools/radio_address.py`'s `name_to_address(NAME)` and construct
      `RadioLink(channel, group=group)`. Do not remove or repurpose
      `--radio CH` — it remains the correct tool for a bare channel number
      (manual dialing, un-migrated boards, group 10 by convention).
- [x] `where` (the human-readable string printed alongside `link`, ~line
      416) reflects which path was used, e.g. `f'radio {a.robot}
      (ch{channel}/grp{group})'` for the new path, unchanged
      `f'radio ch{a.radio}'` for the existing one.

## Implementation Plan

### Approach

1. `tools/radio_address.py` (ticket 001) needs to be importable from both
   files. Both already live in `tools/`, so a plain `import radio_address`
   should work the same way other same-directory `tools/*.py` imports do —
   confirm rather than assume, since some scripts in this directory add an
   explicit `sys.path.insert` even for same-directory imports (defensive
   habit in this codebase, not always structurally required).
2. `robotlink.py`: thread `robot` through `open_link()` into the `!CG`
   construction; update the docstring/comments; update the existing test's
   literal assertion.
3. `wire_acceptance.py`: add the `group=10`-defaulted parameter to
   `RadioLink`; add `--robot` to the CLI; wire the derived values through
   to both the `RadioLink` construction and the `where` string.

### Files to Modify

- `tools/robotlink.py`
- `tools/wire_acceptance.py`
- `tests/tools/test_robotlink.py` (update the `!CG` literal assertion)

### Testing Plan

- **Existing tests to run**: `uv run pytest tests/tools/test_robotlink.py -v`
  — the full file, since this ticket touches `open_link()`'s signature and
  the relay handshake it already pins carefully (HELLO-before-anything-else,
  no `sync_seq()` call, etc. — do not regress those other assertions while
  changing the `!CG` line).
- **New tests**: extend `tests/tools/test_robotlink.py` (or add a small
  new test) asserting `open_link(radio=True)` with no `robot=` argument
  still sends `!CG 37 43` (vevov's derived pair) — i.e., prove the default
  didn't silently change behavior for the ~10 existing no-robot-argument
  callers. For `wire_acceptance.py`, add a small test (new file, e.g.
  `tests/tools/test_wire_acceptance_radio_link.py`, if none currently
  covers `RadioLink`/`main()`'s argument parsing — check first) proving
  `--robot vevov` derives `37`/`43` and `--radio 4` still sends group `10`
  unchanged.
- **Verification command**: `uv run pytest tests/tools/test_robotlink.py -v`
  plus whatever new/existing test file covers `wire_acceptance.py`'s
  argument handling.

### Documentation Updates

Inline comment/docstring updates described in the Acceptance Criteria
above (both files' own top-of-file docs and the `robotlink.py` constants'
removed comment). No separate doc files reference these constants by name
(confirm with a repo-wide grep before closing the ticket).
