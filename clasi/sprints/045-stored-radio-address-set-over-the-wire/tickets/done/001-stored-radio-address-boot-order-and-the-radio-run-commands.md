---
id: '001'
title: Stored radio address, boot order and the _radio run commands
status: done
use-cases:
- SUC-001
- SUC-002
depends-on: []
github-issue: ''
issue: stored-radio-address-set-over-the-wire.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Stored radio address, boot order and the _radio run commands

## Description

Mirror the stored Wi-Fi address for the radio, in `src/blocks/program.ts`
(`wifiAddressKey`, `storedWifiAddress()`, `saveWifiAddress()`,
`reportWifiAddress()` are the pattern).

- Settings keys `#radio.ch` and `#radio.grp` (numbers). Stored channel
  0-83, group 0-255, both whole numbers.
- `setupRobot()` boot order: if the program already called `setupRadio()`
  (`radioAddressInUse()` set) source is `program`; else a stored pair gives
  `setupRadio(stored)` with source `stored`; else the name-derived pair
  with source `name`. No stored pair and no derivable name leaves the radio
  off as today.
- Boot line becomes `boot radio <name> ch N grp M <source>`.
- Run commands registered in `setupRobot()` with `runSignature`:
  `_radioshow()`, `_radioset(channel:number=0, group:number=0)`,
  `_radioclear()`.
- `radiostore.values` report from show, set and clear: `ch`, `grp` (the
  address the next boot will use from the store, else the default), `stored`
  (0/1), `source` (the source of the address in use this boot), `default_ch`,
  `default_grp` (name-derived). A set answers with the stored values.
  Invalid values answer `radiostore.fail` with a `why` and write nothing;
  both values validated before either is written.
- A stored address takes effect at the next boot. No live retune.
- Keep `program.ts` cohesive: if the additions are large, put the store and
  its pure validation in a sibling file under `src/blocks/` and register it
  in `pxt.json`.

## Acceptance Criteria

- [x] `_radioset 70 12` stores and answers `radiostore.values` with the
      stored pair; non-integer, negative, channel > 83 or group > 255 answer
      `radiostore.fail` and store nothing.
- [x] Boot order and source word as above; STATUS is unchanged and still
      reports the address in use.
- [x] `_radioclear` removes both keys and answers with `stored` 0 and the
      name-derived default.
- [x] `setupRobot()` JSDoc command list includes the three new commands.
- [x] Docs: `src/blocks/DESIGN.md` (from the sprint design overlay),
      `src/DESIGN.md` radio section note, `docs/robot-connections.md` where
      `_net*` or stored credentials are described, and the README if it
      lists run commands.
- [x] No narrative or history comments in the source.

## Testing

- **Existing tests to run**: `uv run pytest tests/host`, specifically
  `test_typescript_typecheck.py` and `test_block_toolbox_order.py`; check
  `tests/host/README.md` for how simulator parity is guarded and run the
  parity tests that cover `src/blocks`.
- **New tests to write**: a text-level source-pin test in the style of
  `test_boot_banner_source_pin.py` pinning the keys, the bounds, the
  boot-order shape and the three command registrations, and a
  `tests/host/` test of the validation table (valid and invalid pairs)
  against a Python restatement or a direct evaluation of the pure
  validation function if the host test setup can run it.
- **Verification command**: `uv run pytest tests/host`
