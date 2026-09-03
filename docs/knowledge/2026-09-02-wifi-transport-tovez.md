---
date: 2026-09-02
tags: [wifi, ai-wb2-12f, planetx, udp, mdns, dns-sd, transport, v6, tovez, farm, mbdeploy]
related-tickets: []
---

# The WiFi transport: v6 over UDP on the Planet X Ai-WB2-12F, verified on tovez

## What shipped

`src/comms/wifi_link.{h,cpp}` (host-portable AT state machine) and
`src/comms/wifi_uart.{h,cpp}` (NRF_UARTE1 on RJ11 J1: TX P8, RX P1)
make the ELECFREAKS Planet X WiFi module a third v6 transport, peer to
USB serial and the radio. `Protocol` owns a third `WireHandler` over
the shared adapter, mirrors `emitLine()` output to it, and gates its
telemetry through the link's own throttle. Opt-in from a program via
`diffDrive.enableWifiLink()`; credentials come from the gitignored
`config/wifi_secrets.json` at deploy time (`tools/make_deploy.py`,
`_inject_wifi_secrets()`), and a build without them leaves the link
disabled. Host side: `tools/wifilink.py` (UDP link, keepalive, mDNS +
broadcast discovery) and `tools/wire_acceptance.py --wifi <name|ip>`,
whose new every-verb section covers the whole v6 table.

Design source: radio-robot-lib's `docs/design/wifi-link` design note,
the AT-mode / `CIPMUX=1` link proven on tovez under nezha-upy on
2026-08-21. The earlier radio-robot-elite passthrough exploration was
read for its AT findings and deliberately not ported (see the header
of `wifi_link.h` for why).

## Verified on hardware -- tovez, 2026-09-02

Board: tovez (UID `...a8fdb5e413abb276...`), on mbdeploy farm node
magni (192.168.1.147), module on J1, joined "Busboom Mesh" and leased
**192.168.1.213**. Firmware `0.20260902.2` (`id diffdrive tovez
0.20260902.2 tovez`), hex + sha256 in `captures/tovez-wifi-20260902/`.
Every artifact below is in that directory.

| check | result | artifact |
|---|---|---|
| Discovery by mDNS | `dns-sd -B _robotlink._udp` lists **"tovez robot link"**; `dns-sd -L` resolves it to `tovez.local.:7654` with TXT `name=tovez role=robot link=v6-udp port=7654`; `tovez.local` -> 192.168.1.213 | `mdns-browse.log`, `mdns-lookup.log`, `mdns-addr.log` |
| Bring-up after a reflash | link ready and re-announced before the host finished flashing; `DBG:wifi state=5 ip=192.168.1.213 peer=192.168.1.40:7655 restarts=0 ... mdns=1/1` | `post-reflash-measurements.log`, `usb-serial.log` |
| Full acceptance over WiFi | **61/69 PASS**, wheels turned on `WHEELS_X` (the classic sections' motion check) | `wire-acceptance-wifi-run1.log` |
| Every-verb section, fresh boot, WiFi | **39/40 PASS** -- HELLO PING ID VER STATUS HELP GET SET TLM (POSE/FULL/AUTO/BUFFER/NOW/OFF) WHEELS_V WHEELS_X MOVE_X MOVE_V GO_TO_R GO_TO_W STOP `STOP now` RUN, wheels turning on all six motion verbs | `all-verbs-wifi-run2.log` |
| Same section, same boot, USB (farm serial daemon) | **40/41 PASS**, identical outcomes to WiFi | `all-verbs-usb-run2.log` |
| PING round trip, idle | 50/50 answered; min 0.1, **median 40.1**, p90 59.5, max 157.8 ms | `post-reflash-measurements.log` |
| PING round trip while `TLM POSE` streams | 30/30 answered; median 53.3, p90 77.7, max 91.8 ms | same |
| Telemetry cadence over WiFi | 179 frames in 10 s = **17.9 Hz**; inter-frame gap median 56 ms, p90 79 ms -- the >= 50 ms floor holds and nothing wedged | same |

The one failure on both transports is the cleartext `RUN:gap`
carve-out answering nothing. It is silent over USB on the same boot
(`usb-rungap-check.log`), so it is not the transport; whether it is
the `gap` handler, the RUN job gate, or expected is unresolved here.
The 8 failures in the first WiFi run were: 6 motion "0 frames" cases
caused by a column-set bug in the new test section (fixed -- the POSE
header is now read per subscription), `TLM NOW` after `TLM OFF`
producing no frame (correct per `wire_adapter.cpp`: NOW is a one-shot
in the CURRENT subscription's shape, so OFF+NOW emits nothing; the
check was rewritten), and `RUN:gap`.

The ~40 ms round trip is the module's own per-`CIPSEND` exchange
(prompt, payload, `SEND OK`), consistent with the 33-36 ms measured for
the passthrough design and the 49.5 ms passthrough packetization median
before it. A USB round trip is 5-6 ms.

## Things that cost time, so you don't pay them again

- **PXT exports any plain `enum Name {` it finds in a C++ file into
  `enums.d.ts`, then fails the build with "please add 'enums.d.ts' to
  files".** Its regex is `^\s*enum\s+(|class\s+|struct\s+)(\w+)\s*({|$)`,
  so an explicit underlying type (`enum State : uint8_t {`) is not
  matched. Every enum in `wifi_link.h` carries one for that reason.
- **The first `mbdeploy deploy --remote` to tovez erased the board and
  then timed out on the probe** ("Timeout reading from probe" during
  Programming) -- the board was left with NO firmware. The immediate
  retry succeeded (after another sector-erase failure + mass erase).
  Two of three later flashes also needed the mass-erase path. Treat a
  probe timeout as "retry once", not as a broken board, but check
  `INFO` on the `_mbflash` service afterwards.
- **`magni.local` resolves to 10.10.10.10 (its eth0), which the bench
  cannot reach.** Use 192.168.1.147 (its wlan0) for the serial daemon;
  `mbdeploy --remote` itself resolved fine. Serial and flash ports are
  dynamic: `ssh eric@magni.local sudo ss -tlnp | grep python3`, then
  `INFO` identifies the flash port (the serial port just pipes).
- **A worktree needs `node_modules` (symlink), `pxt_modules` (copy) and
  a `.claude/worktrees/aprilcam` symlink** before `uv run` works there
  (pyproject's editable `../aprilcam` resolves relative to the worktree).
- **The USB serial service is exclusive**: a logger holding it blocks
  `--tcp` acceptance runs and is killed by any flash.
- **The robot's DBG line comes out on USB only on a state change** (and
  every 10 s while not ready), so a robot that joined before you
  connected shows nothing until the first WiFi datagram arrives -- the
  new-peer edge emits one.
- The module keeps its AP join across an nRF reset, so after a
  reflash the `AT+CWJAP?` poll lands immediately and the link is back
  within seconds; the 6-170 s join is only paid from a cold module.

## Open items

1. `RUN:gap` (cleartext carve-out) silent on USB and WiFi -- verify on
   master and decide whether it is a defect.
2. The 60 s peer-silence forget and the backoff/restart path were
   exercised only under the host tests, not on the bench.
3. No authentication on UDP :7654 -- anyone on the LAN can drive the
   robot. Same open decision the earlier exploration flagged.

Robot assignment note: tovez was assigned for this work by the
stakeholder on 2026-09-02. There is no standing rule about which agent
owns which robot; the assignment is per session and per machine.
