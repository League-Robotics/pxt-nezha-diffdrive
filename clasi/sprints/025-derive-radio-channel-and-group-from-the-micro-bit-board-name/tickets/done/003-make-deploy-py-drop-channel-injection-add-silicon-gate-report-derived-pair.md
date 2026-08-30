---
id: '003'
title: 'make_deploy.py: drop channel injection, add silicon gate, report derived pair'
status: done
use-cases: []
depends-on:
- '001'
github-issue: ''
issue: derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# make_deploy.py: drop channel injection, add silicon gate, report derived pair

## Landing Order Constraint (with ticket 002)

**This ticket must land with or before ticket 002 — never after.**
`_inject_radio_channel()` matches the `kChannel` line via `_K_CHANNEL_RE =
r'(static constexpr int kChannel = )\d+(;)'` and **raises** the moment
that regex stops matching. Ticket 002 deletes the `kChannel` constant the
regex matches against; this ticket deletes `_inject_radio_channel()` (and
`_K_CHANNEL_RE`) itself. If ticket 002 lands first without this ticket,
every `make_deploy.py` build breaks in between — the injector still fires,
finds no `kChannel` line, and raises. Both tickets' `depends-on` lists only
name `['001']`, so the dependency graph does not prevent committing them in
the wrong order; this note is what does.

## Description

`tools/make_deploy.py` currently injects a per-robot radio channel into the
scratch copy at deploy time (`_inject_radio_channel()`,
`_read_robot_radio_channel()`, `_K_CHANNEL_RE`, lines ~426-486), read from
radio-robot-lib's `connection.radio_channel` config field. With the board
deriving its own address at boot (ticket 002), the hex is no longer
per-channel: every robot's hex is now byte-identical with respect to radio
addressing, so this injection step is dead code, not merely superseded.

`--robot` keeps its other two jobs unchanged: selecting the flash target
(`flash(a.robot)`) and driving `_inject_profile()`'s `kProfile` bake and
`_inject_boot_banner()`'s banner text — neither of those reads
`connection.radio_channel`, so neither is affected by this ticket.

In place of channel injection, this ticket adds the **silicon gate**: before
building for `--robot <name>`, verify that the board physically attached (if
any) really is `<name>`, using `mbdeploy.devices.read_board_name()` — the
only identity authority (`.claude/rules/` "identity comes from hardware, not
config"; per `docs/radio-addressing.md`, `--robot <name>` is a config string,
and deriving an address from it without checking would move the staleness
from `connection.radio_channel` to `identity.robot_name` rather than remove
it — this is the whole point of the change).

## Acceptance Criteria

- [x] `_inject_radio_channel()`, `_read_robot_radio_channel()`, and
      `_K_CHANNEL_RE` are deleted from `tools/make_deploy.py`.
      `main()`'s call to `_inject_radio_channel(DEPLOY, a.robot)` is removed
      from the build sequence.
- [x] `--robot` still selects the flash target (`flash(a.robot)`),
      `kProfile` (`_inject_profile()`), and the boot banner
      (`_inject_boot_banner()`) — none of these three call sites change.
- [x] The module docstring's description of `--robot`'s channel-injection
      behavior (lines ~34-46, "`--robot` selects more than the flash
      target... this script reads the target robot's own
      `connection.radio_channel`...") is rewritten to describe the new
      state: the hex is radio-address-agnostic, the board derives its own
      channel/group at boot from its name, and `--robot` only verifies
      (via the silicon gate) and selects the flash target/profile/banner.
      Do not leave stale prose describing deleted behavior.
- [x] A new deploy-summary line prints the derived `(channel, group)` pair
      for `a.robot`, computed via `tools/radio_address.py`'s
      `name_to_address()` (ticket 001) — e.g. `make_deploy: vevov derives
      radio channel=37 group=43`. Printed unconditionally (build and
      `--flash` both), so the operator always knows what to tune a relay
      to, matching the existing `print(f'make_deploy: geometry bake
      {_name} = {_value:g}')`-style summary lines already in `main()`.
- [x] **The silicon gate** (new function, e.g. `_verify_robot_silicon(uid,
      robot)` or inline in `main()`/`flash()`):
  - [x] Imports `read_board_name` from `mbdeploy.devices`. **Import
        mechanics**: `mbdeploy` is installed via `pipx` into its own
        isolated venv (confirmed 2026-08-30: `/Users/eric/.local/bin/
        mbdeploy`'s shebang points at a pipx venv, and `import mbdeploy`
        fails in this repo's own `uv run python`) — it is **not**
        importable off this repo's own dependency tree as-is. Follow the
        existing sibling-checkout convention this file already uses for
        `RADIO_ROBOT_LIB`/`ELITE` (module-level path constants) and the
        `sys.path.insert(0, ...)` pattern several `tools/*.py` scripts
        already use (e.g. `tools/otos_levercal.py:34`): add a
        `MBDEPLOY_ROOT = '/Volumes/Proj/proj/RobotProjects/mbdeploy'`
        constant, `sys.path.insert(0, os.path.join(MBDEPLOY_ROOT, 'src'))`
        before the import, and treat an `ImportError` there (sibling
        checkout missing/moved) the same as `read_board_name()` returning
        `None` for the purposes of the fail/warn logic below — do not let
        an import failure crash with a raw traceback.
  - [x] Determine the attached board's UID the same way `flash()`'s
        existing `mbdeploy` subprocess call does (check how `flash()`
        resolves a target board, and reuse that resolution rather than
        inventing a second one).
  - [x] Calls `read_board_name(uid)` and compares to `a.robot`.
  - [x] **Mismatch → hard failure**: `sys.exit` naming both the requested
        `--robot` value and the name actually read from silicon.
  - [x] **`read_board_name()` returns `None`** (pyOCD unavailable, probe
        busy, or the import-failure case above): with `--flash`, a board is
        physically attached, so this is a **hard failure** (`sys.exit`,
        explaining why the check could not run). Without `--flash`, there
        is nothing attached to check, so **warn and continue** — print a
        message, do not exit.
  - [x] Runs with `connect_mode="attach"` semantics (no halt, no reset, no
        serial port) — confirm the call matches
        `mbdeploy/src/mbdeploy/devices.py:275`'s actual signature and
        default rather than assuming keyword names; read that function
        before wiring the call.
- [x] `tests/tools/test_make_deploy_robot_channel.py` is retired (deleted).
      Its fixture-based coverage of `_inject_radio_channel()` /
      `_read_robot_radio_channel()` / `_K_CHANNEL_RE` has nothing left to
      test once those are deleted.

## Implementation Plan

### Approach

1. Delete `_inject_radio_channel()`, `_read_robot_radio_channel()`,
   `_K_CHANNEL_RE`, and the `main()` call site, per the acceptance criteria.
2. Rewrite the module docstring's `--robot` description (see acceptance
   criteria) — this is not optional cleanup, the current prose actively
   describes behavior this ticket removes.
3. Add the deploy-summary print, using `tools/radio_address.py` (ticket
   001) — import it the same way this file already imports sibling tools
   (check whether `tools/radio_address.py` needs a `sys.path` entry or is
   already reachable; it lives in the same `tools/` directory as
   `make_deploy.py` itself, so a plain `import radio_address` after
   confirming `tools/` is already on `sys.path` — which it is, since
   `make_deploy.py` itself runs from there — should suffice; do not
   over-engineer this part).
4. Add the silicon gate. Read `flash()`'s existing board-resolution logic
   first (how does it find `uid` for the `mbdeploy` subprocess call today)
   before writing new resolution logic — reuse, don't duplicate.
5. Delete `tests/tools/test_make_deploy_robot_channel.py`.
6. Write new tests for the silicon gate and the deploy-summary line,
   following that retired file's own convention of monkeypatching sibling
   paths/functions rather than depending on the real sibling checkouts or
   real hardware being present (see Testing Plan).

### Files to Modify

- `tools/make_deploy.py` — delete channel-injection code, rewrite
  docstring, add deploy-summary line, add silicon gate.

### Files to Create

- New test file (e.g. `tests/tools/test_make_deploy_silicon_gate.py`)
  covering the silicon gate's four branches: match (proceed), mismatch
  (`sys.exit` naming both), `None` + `--flash` (hard failure), `None` + no
  `--flash` (warn and continue). Monkeypatch `read_board_name` (or the
  module-level import point) rather than requiring real pyOCD/hardware —
  same posture the retired `test_make_deploy_robot_channel.py` used for
  `RADIO_ROBOT_LIB`.
- Coverage for the deploy-summary line (e.g. capture stdout and assert the
  derived channel/group appear) can live in the same new file or a second
  small one — programmer's judgment.

### Files to Delete

- `tests/tools/test_make_deploy_robot_channel.py`.

### Testing Plan

- **Existing tests to run** (scoped): `uv run pytest tests/tools/ -k
  make_deploy` to confirm no other `make_deploy.py` test (e.g. the build
  triage suite, `tests/tools/test_make_deploy_triage.py`) regresses from
  the docstring/structure changes.
- **New tests**: as described above.
- **Verification command**: `uv run pytest tests/tools/ -k make_deploy -v`

### Documentation Updates

The module docstring rewrite (acceptance criteria above) IS this ticket's
documentation update — `tools/make_deploy.py`'s own top-of-file doc is the
only place `--robot`'s channel behavior is documented in prose. No other
doc files reference `_inject_radio_channel()` by name (confirm with a
repo-wide grep before closing the ticket; if any do, update them too).
