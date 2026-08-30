---
id: '025'
title: Derive radio channel and group from the micro:bit board name
status: executing
branch: sprint/025-derive-radio-channel-and-group-from-the-micro-bit-board-name
use-cases: []
issues:
- derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 025: Derive radio channel and group from the micro:bit board name

## Goals

Make every board compute its own radio address from its five-letter
micro:bit name, and remove the four hand-maintained sources of the same two
numbers.

## Problem

Radio addressing is allocated by hand in four places that can silently
disagree: `kChannel` in `src/comms/radio_transport.h` (deploy-time
text-substituted by `make_deploy.py` from radio-robot-lib's
`connection.radio_channel`), the baked `group_ = 10`, `robotlink.py`'s
`ZAVAZ_CHANNEL`/`ZAVAZ_GROUP` literals, and `wire_acceptance.py`'s hardcoded
group 10. Every new board needs a human to find a free channel.

That scheme has already failed. In `radio-robot-lib/config/robots/`, **gopiv
and zeguz both sit on `radio_channel: 5`**, and zetuv sits on 7 — MakeCode's
unconfigured default. `zetuv.json`'s own provenance note records the author
reasoning "3/4/5/6 were already taken and a collision makes both robots
unusable", and the collision happened anyway two robots later.

## Solution

The name is a base-5 encoding of `NRF_FICR->DEVICEID[1]`, so it is already a
unique per-board number. Derive the address from it; injectivity becomes a
property of the map rather than of whoever edited the file last.

Normative spec: `docs/radio-addressing.md`. Machine-readable contract:
`docs/radio-address-vectors.json`.

```
n       = base5(name)                        # 0..3124, name[0] MOST significant
channel = 25 + 2 * (n % 25)                  # 25..73 inclusive
group   = 1 + (n / 25); if >= 10 then +1     # 1..9, 11..126
```

## Success Criteria

1. A board flashed from this sprint brings its radio up on its derived pair
   with no per-robot hex and no config file consulted.
2. `tools/radio_address.py` and the firmware's C++ derivation both reproduce
   `$.properties.full_space_sha256` over all 3125 names.
3. `make_deploy.py` hard-fails when silicon disagrees with `--robot`.
4. vevov answers `PING` over zavaz tuned to 37/43, **and is silent on the old
   `!CG 4 10`** — the negative control is mandatory.

## Scope

### In Scope

- `tools/radio_address.py` reference implementation + tests.
- Firmware self-addressing in `src/comms/radio_transport.{h,cpp}`.
- `make_deploy.py`: drop channel injection, add the silicon gate, report the
  derived pair.
- `robotlink.py` and `wire_acceptance.py`: derive relay tuning.
- Hardware verification on vevov over zavaz.

### Out of Scope

- radio-robot-lib deleting `connection.radio_channel` — that repo's work,
  gated on their own sign-off, and unblocked once ticket 003 lands.
- microbit-radio-relay's `!N <name>` — that repo's work. **Not a dependency:**
  a self-addressing board is reachable today via plain `!CG`, so there is no
  flag day and no synchronized release.
- Retuning getez off channel 3 (`.claude/rules/playfield-testing.md` forbids
  it, and the torture:8760 relay pool depends on it). vevov/zavaz only.
- The `set radio group` block (sprint 021 ticket 005).

## Test Strategy

Host tests only, plus one hardware link check. No commanded motion, so no
geofence or playfield exposure.

The **full-space digest is the primary test**, not the sampled vectors: both
the Python and the C++ derivation must reproduce
`a1069d8503f83873ab79b97c063ff95f300b34a35a03d83848888cc361bbde31` over all
3125 names. A test that only checks the published rows can pass with a
reversed encoder — `zuzuz`, `tatat`, `zotoz`, `pipip` and `zavaz` are all
digit-palindromes and cannot detect digit-order errors. Use `zuzuv` or
`zotuz` for spot checks.

## Architecture

Authority moves from configuration to silicon. `ensureRadioReady()` derives
`channel_` and `group_` from `microbit_friendly_name()` at radio bring-up
instead of reading a `constexpr` that `make_deploy` patched. Host tools
recompute the same pure function to know where to tune a relay.

### Architecture Overview

One pure function, three implementations, one shared contract:

| implementation | consumer |
|---|---|
| `RadioTransport::deriveAddress()` (C++, no allocation) | the board, at boot |
| `tools/radio_address.py` | `make_deploy`, `robotlink`, `wire_acceptance` |
| `docs/radio-address-vectors.json` | this repo + two sibling repos |

`setGroup()`/`setChannel()` keep their store-then-apply override contract; a
`*_overridden_` flag distinguishes "never told" (use derived) from
"explicitly set" (use the override).

### Design Rationale

**Superseding sprint 022.** That sprint decided radio-robot-lib's
`connection.radio_channel` is canonical for the channel. This reverses it:
silicon is a better authority than a config field. Recorded here rather than
deleted silently.

**The silicon gate is not optional.** Deriving from `--robot <name>` reads a
config string, which would move the staleness rather than remove it.
radio-robot-lib found the case: `togov` is a well-formed name deriving
cleanly to 37/109, but no probe in either repo has ever seen that board.
`read_board_name(uid)` (`mbdeploy/src/mbdeploy/devices.py:275`, pyOCD over
SWD, attach-only) is the only identity authority. `connection.serial_last_6`
is **not** an acceptable substitute — it means last-6-hex for three robots,
last-6-decimal for gopiv, and for zeguz a substring of the DAPLink USB UID,
a different chip entirely.

**Reserved values buy a no-flag-day rollout.** Never emitting channel 3/4/7
or group 0/10 keeps the legacy fleet convention, MakeCode's unconfigured
default, and the relay's `!C` button space all clear, so migrated and
un-migrated boards coexist.

### Cross-repo coordination

Spec verified independently by radio-robot-lib (own encoder, from prose,
reproducing the digest byte-for-byte) and adopted by microbit-radio-relay for
`!N <name>`. Their review produced three fixes already folded into the spec:
the channel-25 inclusive ruling, the published encode direction, and the
endianness trap with its negative digest.

**Live collision to resolve before ticket 002:** an uncommitted change in the
main checkout adds `setChannel()` to `radio_transport.h`. Complementary, not
opposed — a mutable `channel_` is what derivation writes into — but the two
edits must not land blind.
