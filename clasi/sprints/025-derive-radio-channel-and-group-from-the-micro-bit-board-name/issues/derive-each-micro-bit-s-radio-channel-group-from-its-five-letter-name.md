---
status: in-progress
sprint: '025'
tickets:
- 025-001
- 025-002
- 025-003
- 025-004
- 025-005
- 025-006
---

# Derive each micro:bit's radio channel and group from its five-letter name

Priority: **Medium** — no robot is broken today, but radio addressing is
hand-maintained in four places that can silently disagree, and every new board
needs a human to allocate it a free channel. Three repos are agreed on the
scheme (see Related); this issue is pxt-nezha-diffdrive's share.

## Description

Every micro:bit's five-letter name is a plain base-5 encoding of
`NRF_FICR->DEVICEID[1]`, burned into silicon. That makes it a unique per-board
number a board can read about *itself*, so a board can derive its own radio
address at boot and any tool that knows the name can compute the same address
with no registry lookup.

**Measured 2026-08-29**, from `radio-robot-lib/config/robots/devices.json`
(all 7 fleet boards — gopiv, getez, zetuv, tovez, zeguz, vevov, zavaz):
`microbit_serial_number() mod 3125 == base5(name)` exactly, 7/7. The
derivation is published by the Micro:bit Foundation at
<https://support.microbit.org/support/solutions/articles/19000067679-how-to-find-the-name-of-your-micro-bit>
(codebook plus a Python implementation).

### The scheme

```
position 0,2,4  consonant   z v g p t   = 0 1 2 3 4
position 1,3    vowel       u o i e a   = 0 1 2 3 4

N        =  Σ val(name[p]) · 5^(4−p)     # 0 .. 3124, plain base-5, MSD first
channel  =  25 + 2 · (N mod 25)          # {25, 27, … 73} — 25 channels, 2 MHz apart
group    =  1 + (N div 25)
if group >= 10: group += 1               # skip 10; see Cause
                                         # → 1..9, 11..126
```

Reverse: `N = 25·(group − (group > 10 ? 1 : 0) − 1) + (channel − 25)/2`.

Because the split is digit-aligned, it is readable by hand: **the last two
letters give the channel, the first three give the group.**

Properties, machine-checked across all 3125 names:

- 3125 names → 3125 distinct `(channel, group)` pairs. No name collides with
  another on both axes.
- Exactly 125 names per channel, 25 names per group — even on both axes.
- Channels 25–73 = 2425–2473 MHz. Starts above Wi-Fi channel 1 (2401–2423 MHz);
  2 MHz spacing is what BLE itself uses at 1 Mbit. Max 73, inside
  `setFrequencyBand`'s 0–83. Max group 126, inside `setGroup`'s 0–255.
- Never emits channel 3, 4 or 7, and never group 0 or group 10.

### Fleet under this scheme

| name | role | serial | N | channel | group |
|---|---|---|---|---|---|
| zeguz | robot | 4227700425 | 425 | 25 | 19 |
| zetuv | robot | 1468666101 | 476 | 27 | 21 |
| vevov | robot | 1198504156 | 1031 | 37 | 43 |
| gopiv | bench rig | 2175407711 | 1461 | 47 | 60 |
| getez | relay | 1784514240 | 1740 | 55 | 71 |
| zavaz | relay | 4076631795 | 545 | 65 | 23 |
| tovez | robot | 2314287040 | 2665 | 55 | 108 |

A relay has no address of its own — **it adopts the robot's**. The getez and
zavaz rows are informational only, so getez sharing channel 55 with tovez costs
nothing: getez tunes to 55/108 when it serves tovez and its own 55/71 never
goes on air.

**Channel sharing between two ROBOTS is real, though.** `channel` is the CODAL
frequency band; `group` is only an address filter. Two robots on one channel
cannot parse each other's traffic but do contend for the same air. Across the
six configured robots there is exactly one such pair — **togov and vevov both
derive channel 37** (2437 MHz). That is tolerable at this fleet's duty cycle,
but it is a real cost, not a non-issue, and it scales as 1 − (24/25)^(n−1)
per added robot.

## Cause

Four independent hand-maintained sources of the same two numbers:

- `src/comms/radio_transport.h` — `static constexpr int kChannel = 4`, text-substituted
  at deploy time by `tools/make_deploy.py`'s `_inject_radio_channel()` from
  radio-robot-lib's `connection.radio_channel`.
- `src/comms/radio_transport.h` — `uint8_t group_ = 10`, baked fleet-wide.
- `tools/robotlink.py` — `ZAVAZ_CHANNEL = 4`, `ZAVAZ_GROUP = 10` as literals.
- `tools/wire_acceptance.py` — `f'!CG {channel} 10'`, group hardcoded.

Three reserved-value exclusions in the scheme above each have a cause:

- **Channel 3, 4 and group 10** are the current fleet convention. Excluding
  them lets un-migrated boards and derived-address boards coexist during
  rollout instead of stomping each other.
- **Channel 7 / group 0** is MakeCode's unconfigured default — the rendezvous
  point for every board whose program forgot to set the radio up.
- **Group 10** is also the microbit-radio-relay `!C <ch>` button space, which
  accepts channels 0–35 and *forces* group 10. Without the skip, six names
  (`zotuz` 25, `zotuv` 27, `zotug` 29, `zotup` 31, `zotut` 33, `zotoz` 35)
  land exactly on a hand-dialed `!C`. Verified by exhaustive enumeration,
  2026-08-29. Skipping group 10 also makes `?`-on-the-relay-display mean
  unambiguously "named/custom address".

### The hand-assigned scheme has already failed

Confirmed 2026-08-30 by reading `radio-robot-lib/config/robots/*.json`
directly (reported by radio-robot-lib-61, verified here):

- **gopiv and zeguz are both on `radio_channel: 5`.** A live collision, in
  the file, today.
- **zetuv is on `radio_channel: 7`** — MakeCode's unconfigured default band,
  the rendezvous point for every board whose program forgot to set the radio up.
- `zetuv.json`'s own `_provenance` note records the author reasoning
  "radio_channel 3 -> 7 (3/4/5/6 were already taken and a collision makes both
  robots unusable)". The failure mode was written down in the file and then
  happened anyway two robots later, because nothing enforces uniqueness.

This is the argument for derivation over allocation: a derived address cannot
collide, because injectivity is a property of the map rather than of whoever
edited the file last.

## Proposed fix

Authority is the **firmware**: each board derives its own address from
`microbit_friendly_name()` at radio bring-up. Host tools recompute the same
function to know where to point the relay.

1. **`docs/radio-addressing.md`** (new) — normative spec: codebook, forward and
   reverse maps, reserved-value rationale, the "relay adopts the robot's
   address" rule, and the measured evidence with its artifact path. This repo
   owns the spec; the other two repos link to it.
2. **`docs/radio-address-vectors.json`** (new) — the shared test-vector file.
   All three repos assert against this same file so the mapping cannot drift.
3. **`tools/radio_address.py`** (new) — pure functions, no I/O:
   `name_to_index`, `index_to_name`, `name_to_address`, `address_to_name`.
   Raises on a letter outside the codebook.
   `tests/tools/test_radio_address.py` pins it against a checked-in fixture of
   the seven fleet name/serial pairs (not a live read of the sibling checkout —
   same posture as `test_make_deploy_robot_channel.py`'s `monkeypatch` of
   `RADIO_ROBOT_LIB`), plus the exhaustive properties listed above.
4. **`src/comms/radio_transport.{h,cpp}`** — delete `static constexpr int kChannel`;
   add `static void deriveAddress(const char* name, uint8_t* channel, uint8_t* group)`
   (codebook decode, ~10 lines, no allocation). `ensureRadioReady()` calls it
   with `microbit_friendly_name()` before `setFrequencyBand()`/`setGroup()`,
   preserving the existing `enable` → band → group → power call order that the
   header comment explains. `group_ = 10` stops being a default; a
   `groupOverridden_` flag keeps `setGroup()`'s store-then-reapply contract
   while an un-told board uses its derived group. An unrecognised letter falls
   back to the legacy (4, 10) pair rather than an arbitrary band.
   `tests/host/radio_address_shim.cpp` + `tests/host/test_radio_address_derivation.py`
   pin the C++ against the same vectors file, following the existing
   `radio_transport_rx_capacity_shim.cpp` pattern.
5. **`tools/make_deploy.py`** — delete `_inject_radio_channel()` and
   `_read_robot_radio_channel()`; the hex is no longer per-channel. `--robot`
   keeps selecting the flash target, `kProfile` and the boot banner. Add a
   deploy-summary line printing the derived `(channel, group)` so the operator
   knows what to tune the relay to. Retire
   `tests/tools/test_make_deploy_robot_channel.py`.

   **Deploy-time silicon gate (required — see below).** `--robot <name>` is a
   config string, and deriving an address from it would move the staleness
   from `connection.radio_channel` to `identity.robot_name` rather than remove
   it. Before deriving, read the board's real name over SWD and compare:

   ```python
   from mbdeploy.devices import read_board_name   # verified present 2026-08-30,
                                                  # mbdeploy/src/mbdeploy/devices.py:275
   silicon = read_board_name(uid)                 # FICR.DEVICEID[1] via pyOCD,
                                                  # connect_mode="attach" — no halt,
                                                  # no reset, no serial port, works on
                                                  # an unflashed or bricked board
   ```

   - `silicon != --robot` → `sys.exit` naming both, the same loud posture
     `_read_robot_radio_channel()`'s docstring says it exists to protect.
   - `read_board_name()` returns `None` when pyOCD is unavailable or the probe
     is busy. With `--flash` a board is physically attached, so an unreadable
     one is a hard failure; without `--flash` there is nothing to read, so warn
     and continue.

   The address is then genuinely silicon-derived on both ends, and the config
   name is verified as a side effect rather than trusted.
6. **`tools/robotlink.py`** — drop `ZAVAZ_CHANNEL`/`ZAVAZ_GROUP`; `open_link()`
   takes `robot=` and derives the pair for the `!CG` it already sends (~line 323).
   Prefer the relay's new `!N <name>` once microbit-radio-relay ships it.
7. **`tools/wire_acceptance.py`** — derived pair instead of hardcoded group 10.

This deliberately reverses sprint 022's decision that radio-robot-lib's
`connection.radio_channel` is canonical. Record that as a superseding
decision in the sprint doc, not a silent deletion.

### Open decisions for the sprint

- **getez.** `.claude/rules/playfield-testing.md` says never retune getez's
  channel 3, and the torture:8760 relay pool has tovez reachable there.
  Moving tovez to (55, 108) requires retuning getez and updating the pool
  config. Do vevov/zavaz first; get explicit stakeholder sign-off before
  touching getez.
- **The `set radio group` block** (`clasi/issues/radio-group-setup-block.md`,
  sprint 021 ticket 005). A student changing the group desyncs the relay.
  Under this scheme the derived group is the default and the block is an
  override requiring a matching `!CG`/`!N` — document that, or defer the block.

## Verification

Link-level only; no commanded motion, so no geofence or playfield exposure.

1. `uv run pytest tests/tools/test_radio_address.py tests/host/test_radio_address_derivation.py`
   — both pass against the same vectors file.
2. Full suite once, inside `close_sprint`.
3. Hardware, vevov (derived **channel 37 / group 43**), captured to
   `captures/radio-addressing-<date>.md`:
   - `make_deploy.py --robot vevov --flash`; confirm the deploy summary prints 37/43.
   - Tune zavaz `!CG 37 43`, then `PING` → `pong <n>`, and `ID` naming `vevov`.
     `HELLO` only at session start — it is a session reset, not a liveness probe.
   - **Negative control:** retune zavaz to the old `!CG 4 10` and confirm the
     board is silent. Without this the test proves nothing — a robot that
     answers on both is a robot that never changed channel.
   - Identity from `HELLO`/`ID`, never from `mbdeploy probe`'s cached ROLE column.
4. Every `MEASURED` claim written during this names its capture file, per
   `.claude/rules/measurement-citations.md`.

## Related

- **microbit-radio-relay** — adding `!N <name>` to the relay firmware
  (`source/relay/RadioRelay.cpp`), the same function in `mbrelay.naming`, and
  the server-side `^!(C|CG|RC)` watcher extended to `!N`. The group-10 skip
  above exists at that repo's request.
- **`!C` becomes dead for migrated boards, and that is intended.** `!C` spans
  channels 0–35 and forces group 10; derived addresses are channels 25–73 and
  never group 10, so `!C` cannot address a migrated board at all — only `!CG`
  or the new `!N` can. Sweep the docs, capture notes and rule files that still
  say "`!C 4`" as part of the rollout.
- **radio-robot-lib** — radio-robot-lib-61 independently re-derived this scheme
  and reproduced the fleet table exactly, then confirmed (2026-08-30): nothing
  in that repo consumes `connection.radio_channel` except as config — `rogo`
  takes `--connect HOST:PORT` and never tunes a relay from it — so this repo's
  `make_deploy.py` is its sole reader. Their recommendation is to DELETE the
  field plus its `robot_config.schema.json` entry and the
  `tests/host/rogo/fixtures/gopiv.json` fixture, pending Eric's sign-off
  (he had separately asked for togov to be set to channel 6). Deleting costs
  that repo zero code changes. They also agree the mapping belongs here, not
  in the config home: it is arithmetic over micro:bit silicon, not a per-robot
  fact.
- **togov is unprobed, and it is the fleet's only derived channel collision.**
  It appears in no device registry in either repo — not radio-robot-lib's
  `config/robots/devices.json`, not radio-robot-elite's `config/devices.json`,
  not that repo's `rogo-revival` worktree (checked by radio-robot-lib-61,
  2026-08-30). Yet "togov" is a well-formed micro:bit name deriving cleanly to
  37/109, and vevov derives 37/43 — the same physical band. `config/MANIFEST.md`
  records togov.json as imported wholesale from radio-robot-elite on
  2026-08-22 carrying measured-looking calibration, so it is probably a real
  board somebody calibrated that no probe has ever seen. **Action: on first
  probe of togov, record its `device_id` and confirm 37/109.** The fleet's only
  channel contention sitting on its only unverified board is not a coincidence
  worth leaving unresolved, and it cannot be settled from config — only by
  probing.

  *Falsifiable prediction to confirm, never to bake:* if togov's
  `serial_last_6` ("ade9b4") uses the hex-of-`device_id` encoding, then
  `device_id = 2108549556` (`0x7DADE9B4`) is the unique 32-bit value that both
  ends in `0xADE9B4` and encodes "togov" — verified here: exactly 1 of the 256
  candidate high bytes lands on N=2681. Since 256 candidates spread over 3125
  residues give P(any consistent value exists) ≈ 7.9%, its existence is modest
  evidence (~12×) that the label is right. If `read_board_name()` returns
  anything else, the `sys.exit` fires and we have learned the label was wrong —
  which is what the gate is for.

- **Never use `connection.serial_last_6` as an identity source.** It means
  three different things across six files (verified 2026-08-30 against
  `devices.json`):

  | robot | `serial_last_6` | what it actually is |
  |---|---|---|
  | tovez, vevov, zetuv | f137c0, 6fb8dc, 8a10f5 | last 6 **hex** of `device_id` |
  | gopiv | 407711 | last 6 **decimal** of `device_id` (hex would be `aa165f`) |
  | zeguz | 0cfd6c | substring of the **DAPLink USB UID** — a different chip |
  | togov | ade9b4 | unknown; never probed |

  zeguz is the trap: that is the on-board interface chip's USB serial, not the
  nRF target's `DEVICEID[1]`, so it carries no identity information at all
  while looking exactly like the fields that do (mbdeploy's README is explicit
  that the name is not encoded in the UID). Same defect class as
  `radio_channel` — a hand-maintained mirror that drifted. `read_board_name()`
  is the only identity source; see `.claude/rules/` on identity coming from
  hardware, not config.
- `clasi/issues/radio-group-setup-block.md` — sprint 021 ticket 005, interacts
  with the derived group default.
- `.claude/rules/playfield-testing.md` — getez channel-3 constraint.
