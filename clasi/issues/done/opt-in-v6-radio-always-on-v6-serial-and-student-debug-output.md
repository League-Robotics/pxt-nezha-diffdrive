---
status: done
---

# Opt-in v6 radio, always-on v6 serial, and student debug output

## Description

Students cannot drive the robot from a joystick micro:bit using MakeCode's
ordinary `radio.*` blocks. A joystick program compiles, flashes, and then
silently does nothing — the two boards never hear each other.

The curriculum wants the opposite default: plain PXT radio works out of the
box for joysticks, and the v6 protocol on radio is something a student opts
into when they graduate to advanced control. Serial stays v6 always, but
students need a way to get their own output into the MakeCode console —
including `variable: value` lines the console will graph.

## Cause

The extension claims **both** wires the moment its code loads, unconditionally.

`motion.ts:74` runs a top-level `_startProtocol()`, which calls
`Protocol::start()` (`src/comms/protocol.cpp:258`): it sizes the serial rings
and launches the protocol fiber. That fiber loops forever, and every iteration
polls radio RX (`protocol.cpp:328`). `RadioTransport::tryReceiveLine()` calls
`ensureRadioReady()` internally, which does `uBit.radio.enable()` →
`setFrequencyBand(4)` → `setGroup(10)` → `setTransmitPower(7)` and registers a
datagram listener (`radio_transport.cpp:30-47`).

So the radio is up on band 4 / group 10 from boot, carrying raw RadioRelay
fragments with **no PXT radio packet header** (`radio_transport.h` top comment).
MakeCode's `radio` package cannot share the air with that — different framing
and a different band.

`RadioTransport` has exactly two lazy-enable entry points, and both must be
accounted for: `tryReceiveLine()` (`radio_transport.cpp:137`) and `sendLine()`
(`radio_transport.cpp:148`).

A second, smaller problem: the `set radio group` block exposes the wrong knob.
In fleet practice the group is always 10 and the **channel** is what differs per
robot (vevov 4, getez/tovez 3) — but the channel is a compile-time constant with
no student-facing surface at all.

## Proposed fix

Stakeholder decisions taken 2026-08-29:

1. **Serial is always v6.** No enable block. Student serial *input*
   (`serial.readLine`, `serial.onDataReceived`) is not supported — the protocol
   fiber consumes inbound lines — and the v6 boot banner keeps appearing in the
   console. Both accepted.
2. **`send string` / `send value` write to serial always, and to radio as well
   once the v6 radio link is on.**
3. **`set radio group` is removed**, replaced by a `setup radio` block taking
   channel and group, with group defaulting to 10.

### Gate the radio behind an explicit enable — `src/comms/protocol.{h,cpp}`

Add `bool radioEnabled_ = false;` with a `setRadioEnabled(bool)`. Gating the RX
poll alone is **not** sufficient — the first `emitLine()` would silently claim
the radio anyway. All three call sites must be gated:

| site | line | why it matters |
|---|---|---|
| radio RX poll | `protocol.cpp:328` | what brings the radio up at boot today |
| `emitLine()`'s radio write | `protocol.cpp:145` (and the `:148` retry) | any debug line would enable the radio |
| radio telemetry | `protocol.cpp:393` | `wireHandlerRadio_.emitTelemetry()` sinks to `sendLine()` |

Leave `SerialTransport` and the banner untouched.

### Make the channel settable — `src/comms/radio_transport.{h,cpp}`

**Keep the line `static constexpr int kChannel = 4;` byte-for-byte.**
`tools/make_deploy.py:464` matches it with
`re.compile(r'(static constexpr int kChannel = )\d+(;)')` and hard-fails the
build if it stops matching. Add alongside it:

```cpp
uint8_t channel_ = kChannel;   // per-robot deploy default; setChannel() overrides
void setChannel(uint8_t channel);
```

`ensureRadioReady()` reads `channel_` instead of `kChannel`. `setChannel()`
stores the value; if `radioReady_` is already true it re-applies
`uBit.radio.setFrequencyBand(channel_)`.

Mark that re-apply path **UNVERIFIED** in the source and say what would settle
it. `changing-the-radio-group-mid-run-is-unverified.md` records that
`setFrequencyBand()` performs an explicit radio restart — a source reading of
`MicroBitRadio.cpp`, not a measurement — while `setGroup()` does not. The
supported path is calling `setup radio` from `on start`, before the radio comes
up. Do not claim the mid-run path works without a bench capture.

Also correct `radio_transport.h:207-212`, which states channel has "no
student-facing surface for it, and none is planned" — this change is that
surface.

### New blocks — `src/blocks/run.ts`

Each is a block *and* a JavaScript function: in MakeCode one annotated
`export function` gives both surfaces at once.

```ts
//% block="setup radio channel %channel group %group"
export function setupRadio(channel: number, group: number = 10): void

//% block="send string %text"
export function sendString(text: string): void

//% block="send value %name = %value"
export function sendValue(name: string, value: number): void
```

- Delete `setRadioGroup` (`run.ts:103-117`, plus the group comment at
  `run.ts:61` that names it).
- `setupRadio` sets channel and group on the transport **and** enables the v6
  radio link — one block, no ordering trap between configure and enable. Its doc
  comment must say: call from `on start`, before anything else touches the
  radio; once it runs, MakeCode's own `radio.*` blocks stop working in that
  program; and changing the channel can take a robot off the fleet relay.
- `sendString(text)` → `emitLine("DBG:" + text)`, matching the existing
  convention at `test/test.ts:341`.
- `sendValue(name, value)` → emits `name + ":" + value` and **must not** carry
  the `DBG:` prefix, or the console will not graph it. That is exactly what
  PXT's `serial.writeValue` produces (`pxt_modules/core/serial.ts:113`).

Both debug blocks route through the existing `diffDrive.emitLine`
(`shims.cpp:1257`) → `Protocol::emitLine` (`protocol.cpp:116`) path, which
already writes serial then radio — no new transport plumbing. Note `emitLine()`
clips to `RadioTransport::kMaxPayloadBytes` even when only serial is in play, so
a long `send string` truncates; worth a line in the help text.

New shims in `src/shims.cpp` + simulator fallbacks in `src/blocks/sim.ts`,
following the existing `_setRadioGroup` pair. Per `sim.ts:195`, declare
shim-fallback params as `number`, never `int32` — `int32` params fail the
JS→Blocks decompiler with TS9256.

**Do not put `min=`/`max=` on these blocks.** Measured 2026-08-29: parameter
min/max on a newly added block hung the editor's toolbox build for 4+ minutes
with zero console errors and "Problems 0", and `pxt build` passes regardless.

### Re-enable radio in the deploy program — `test/test.ts`

Load-bearing, not a follow-up. Every `tools/*.py` script drives the robot over
the zavaz relay, and untethered runs report results back by radio. With the
radio gated off, all of that goes silent with no error — the failure looks
exactly like a dead robot.

`test/test.ts` must call `diffDrive.setupRadio(...)` in its startup path on the
robot's own channel, cross-checked against `make_deploy.py`'s injected
`kChannel` so a `--robot tovez` build still lands on channel 3.

### Toolbox layout — `docs/blocks-toolbox.csv`

The CSV is the source of truth (commit `2d8394c`). Remove the `setRadioGroup`
row and add three: `setupRadio` into Setup/Setup (the slot it vacates), and
`sendString`/`sendValue` into a new **Debug** group under Extra — they are
student console output, not driving. Then `just blocks-plan` to check and
`just blocks-apply` to write the annotations; `//% group=`, `//% subcategory=`
and `//% weight=` are all generated, so do not hand-edit weights. New rows can
use fractional `new_order` (e.g. `4.1`) to slot in without renumbering.

Update the longhand baseline in `tests/host/test_block_toolbox_order.py`; it
fails on any intentional reorg, which is its job.

## Verification

1. `uv run pytest` — full suite (791 passing at `2d8394c`). Expect to update the
   toolbox baseline, and `tests/tools/test_make_deploy_robot_channel.py` if the
   channel declaration moves at all.
2. `just blocks-plan`, `just blocks-apply`, then `just blocks` and read the
   flyout back from the editor DOM: all three render, `setup radio` under Setup,
   `send string`/`send value` under Extra ▸ Debug, and `set radio group` gone.
   Then drag each into `on start` and switch to the JavaScript view to confirm
   the blocks → JS → blocks round-trip, where this repo's TS9256 decompiler
   traps bite.
3. **Default path, the point of the change:** a consumer project with
   `radio: "*"` using `radio.sendNumber` / `radio.onReceivedNumber` that does
   NOT call `setup radio`. Confirm two micro:bits talk. This cannot work today.
4. **Opt-in path:** `setup radio channel 4 group 10` in `on start`, then confirm
   the robot answers `PING` → `pong` over the relay. `PING`/`STATUS`/`HELLO` do
   not take a `#<id>`; the sequenced verbs do.
5. **Console graph:** `send value "x" 42` renders on the MakeCode graph;
   `send string "hello"` appears as `DBG:hello` and does not.
6. Hardware checks are UNVERIFIED until run. Anything written into source as
   MEASURED must name its capture file, board, and date.

## Related

- `radio-group-setup-block.md` — shipped the `set radio group` block this issue
  removes; superseded by `setup radio`.
- `changing-the-radio-group-mid-run-is-unverified.md` — the mid-run re-apply
  question, which now extends to `setFrequencyBand()` as well as `setGroup()`.
- Channel is fleet-critical: CLAUDE.md records channel 4 for vevov and "never
  retune getez's channel 3". This issue hands students that knob.

---

## Triage 2026-09-02 — DONE

Landed: `setupRadio`, `sendString`, `sendValue` in `src/blocks/run.ts`;
`RadioTransport::setChannel()`; `Protocol::setupRadio()` with the radio
link opt-in (`protocol.h` "The v6 radio link is OPT-IN"); `set radio
group` removed. The five boards reflashed 2026-08-30 answer on their
derived channels (`captures/fleet-reflash-20260830.md`). Verification
steps 3 and 5 (plain PXT `radio.*` between two micro:bits, and the
MakeCode console graph) remain UNVERIFIED on hardware.
