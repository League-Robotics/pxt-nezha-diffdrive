---
title: "The 250-byte radio packet size is the consuming project's choice, and the v6 radio enable must refuse when it is absent"
status: pending
created: 2026-09-06
---

# The 250-byte radio packet size is the consuming project's choice, and the v6 radio enable must refuse when it is absent

## Description

Students build robot programs in consumer packages such as
`league-projects/scratch/nezha-robot-template`, which depend on this
extension AND on MakeCode's own `radio` package, because joystick
controllers speak plain PXT radio. The v6 radio link is already opt-in
(`RadioTransport::enable()`, `src/comms/radio_transport.h`; issue
`opt-in-v6-radio-always-on-v6-serial-and-student-debug-output`, done), so
a program that never calls `setup radio` leaves `uBit.radio` to MakeCode.

One thing still leaks out of the extension into every consumer regardless
of that gate: `pxt.json`'s `yotta.config.microbit_radio_max_packet_size:
250`. PXT flattens every package's `yotta.config` into one `codal.json`
`definitions` block (`node_modules/pxt-core/built/pxt.js:105220-105238`),
so the define reaches CODAL's `MicroBitRadio` and PXT's own `radio.cpp` in
the student's build. Effects, all source readings, none measured:

- every received frame is a 262-byte `new FrameBuffer()` inside the radio
  ISR instead of 44 (`codal-microbit-v2/inc/MicroBitRadio.h:95-105`,
  `source/MicroBitRadio.cpp:216`), up to four queued plus the live one;
- PXT's `readRawPacket()` returns 254-byte Buffers instead of 36
  (`pxt-common-packages/libs/radio/radio.cpp:192-197`). Its TypeScript
  reads RSSI at `length - 4` (`radio.ts:191`) so it still functions;
- a robot with nRF `MAXLEN` 250 receiving from a joystick at 32 is
  UNVERIFIED cross-device.

The 250 exists only so one v6 line (240 B + 3 B fragment header + 1 B
delimiter = 244 B) fits a single fragment; `RadioTransport::onDatagram()`
accepts single-fragment messages only. Students on plain radio pay the
RAM and ISR-allocation cost and get nothing for it.

## What PXT allows

There is no "if the project also depends on `radio`" conditional in
`pxt.json`. The merge rules that DO exist (`pxt.js:105220-105248`,
`105318`):

| mechanism | behaviour |
|---|---|
| `yotta.config` | first package to set a key wins; a later package setting a DIFFERENT value throws `conflict on yotta setting ... between extensions` unless the first declared `yotta.configIsJustDefaults: true`, or the top-level project sets `yotta.ignoreConflicts` |
| `yotta.optionalConfig` | lowest priority, applied only where no `config` set the key; last one wins among optionals; an explicit `null` deletes the key |
| a consumer setting the same value as a dependency | silently fine (the template's own 250 today) |

So the choice is the consumer's if the extension either drops the key or
demotes it, and the consumer can always set 250 in its own `pxt.json`
with no conflict.

## Proposed fix

1. **Drop `microbit_radio_max_packet_size` from this repo's `pxt.json`.**
   Default becomes CODAL's 32, i.e. what MakeCode's `radio` package
   expects. A consumer that wants the v6 radio link sets
   `"yotta": {"config": {"microbit_radio_max_packet_size": 250}}` itself.
   (Demoting to `optionalConfig` keeps 250 as the default and only lets a
   consumer opt DOWN; that is the wrong default for the curriculum.)

2. **Inject 250 into every deploy scratch copy.** `tools/make_deploy.py`'s
   `_sync_scratch()` (line ~357) already rewrites the scratch `pxt.json`
   in memory; add the `yotta.config` key there so fleet builds (`test.ts`,
   `testrig.ts`, the fault-spin build) are byte-for-byte what they are
   today. Pin it in `tests/tools/` next to the kChannel injection tests.

3. **Make the enable refuse when the build cannot carry a v6 line.**
   `MICROBIT_RADIO_MAX_PACKET_SIZE` is a compile-time macro and the same
   value the whole hex was built with, so a check in
   `radio_transport.cpp` is exact:

   ```cpp
   // [bytes] one whole v6 line in ONE fragment: header + line + '\n'
   static constexpr int kMinPacketSize =
       kFrameHeaderBytes + static_cast<int>(kMaxPayloadBytes) + 1;   // 244
   bool RadioTransport::enable() {
     if (MICROBIT_RADIO_MAX_PACKET_SIZE < kMinPacketSize) return false;
     enabled_ = true;
     return true;
   }
   ```

   NOT a `static_assert`: that would fail the student's build, which is
   the case this issue exists to make work. The refusal must be visible:
   `setupRadio` / `enableRadioLink` return `boolean`, and on refusal
   `Protocol` emits one serial line, e.g.
   `DBG:radio link refused: packet size 32 < 244, set
   microbit_radio_max_packet_size 250 in pxt.json`. `test/test.ts` treats
   a `false` from `enableRadioLink()` as a boot failure, so a deploy that
   forgot step 2 cannot go silent on the relay and look like a dead
   robot.

4. **Template:** `nezha-robot-template/pxt.json` currently sets 250 while
   its `test/boot.ts` uses MakeCode radio (group 11) and puts the wire
   protocol on WiFi. Remove the key there. Not this repo; noted so the
   two land together.

Optional, UNVERIFIED: detect MakeCode's radio package at runtime with a
weak reference (`namespace radio { int radioEnable()
__attribute__((weak)); }`, non-null iff `radio.cpp` is linked) and warn
on `setup radio`. Risk: PXT's per-file dependency scan already reacts to
the token `radio` in this repo's sources (`src/shims.cpp:996`,
`src/blocks/sim.ts:540`) and may demand the `radio` package. The
packet-size check above is deterministic and sufficient; do this only if
a build test shows the scan tolerates it.

## Verification

1. Host: `tests/tools/` pins that every scratch `pxt.json` carries 250 and
   the repo `pxt.json` does not; a unit test on the refusal predicate
   (host-portable, same pattern as `radioRxLineFits()`).
2. Build A (student path): a consumer project with `radio: "*"`, no
   `yotta.config`, `radio.sendNumber` / `onReceivedNumber`, never calls
   `setup radio`. `built/codal.json` shows no
   `MICROBIT_RADIO_MAX_PACKET_SIZE` define. Two micro:bits talk; robot
   drives from a joystick with motors under load. This is the one real
   measurement this issue needs; name the capture.
3. Build B (student path, wrong config): same project, `setup radio`
   called. Console shows the refusal line; MakeCode radio keeps working.
4. Build C (fleet path): `make_deploy.py --robot <name> --radio-link`.
   `built/codal.json` shows 250; `PING` -> `pong` over the relay as today.

## Related

- `opt-in-v6-radio-always-on-v6-serial-and-student-debug-output.md` (done)
- `radio-heap-corruption-hardfault` memory: the 2026-08-30 fault was
  radio RX allocating during a live motor step; resolved by the VFP guard
  and retested over THIS transport, never over PXT's radio path under
  motor load. Build A above covers that.
