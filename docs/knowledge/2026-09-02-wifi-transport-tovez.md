---
date: 2026-09-02
tags: [wifi, ai-wb2-12f, planetx, udp, tcp, mdns, dns-sd, transport, v6, tovez, farm, mbdeploy, radio]
related-tickets: []
---

# The WiFi transport: v6 over TCP and UDP on the Planet X Ai-WB2-12F, verified on tovez

## What shipped

`src/comms/wifi_link.{h,cpp}` (host-portable AT state machine) and
`src/comms/wifi_uart.{h,cpp}` (NRF_UARTE1 on RJ11 J1: TX P8, RX P1)
make the ELECFREAKS Planet X WiFi module a third v6 transport, peer to
USB serial and the radio. On one module the robot runs:

- a **TCP server on :7654** -- a client is a plain line stream like
  USB; up to three clients, replies to whichever spoke last, banner on
  connect, no keepalive (`AT+CIPSTO=0`);
- a **UDP plane on :7654** -- one datagram per line, host learned from
  the first datagram, forgotten after 60 s of silence;
- an **mDNS/DNS-SD announcer** -- the module has no mDNS of its own, so
  the robot multicasts its own response packet every 60 s:
  `<name>.local` plus "`<name> robot link`" under `_robotlink._tcp` and
  `_robotlink._udp`, TXT `name=<name> role=robot link=v6 port=7654`.

`Protocol` owns a third `WireHandler` over the shared adapter, mirrors
`emitLine()` output to it, and gates telemetry so frames can never delay
a reply (below). Opt-in from a program via `diffDrive.enableWifiLink()`;
credentials come from the gitignored `config/wifi_secrets.json` at
deploy time (`tools/make_deploy.py`, `_inject_wifi_secrets()`); a build
without them leaves the link disabled.

**The v6 radio link is now OFF by default in the test program.**
`test/test.ts` gates `enableRadioLink()` on `BOOT_RADIO_LINK`, which
`make_deploy.py --radio-link` (or `connection.v6_radio_link: true` in
the robot's radio-robot-lib config) flips to true; otherwise the radio
is never touched, and MakeCode's own `radio` blocks (a student's
joystick, 32-byte packets) work in the same program.

Host side: `tools/wifilink.py` (`TcpLink`, the UDP `WifiLink`, mDNS +
broadcast discovery, CLI), `tools/robotlink.py` `open_link(wifi=...)`
so every tour tool takes `--wifi <name>`, `wire_acceptance.py --wifi`
/ `--wifi-tcp` / `--tcp` and its every-verb section, and
`tools/publish_wiki.py` for the Robot Garage wiki. The agent-facing
guide is `docs/robot-connections.md` (rule pointer:
`.claude/rules/connecting-to-a-robot.md`).

Design source: radio-robot-lib's `docs/design/wifi-link` design note,
the AT-mode / `CIPMUX=1` link proven on tovez under nezha-upy on
2026-08-21. The earlier radio-robot-elite passthrough exploration was
read for its AT findings and deliberately not ported (see the header
of `wifi_link.h` for why).

## Verified on hardware -- tovez, 2026-09-02

Board: tovez (UID `...a8fdb5e413abb276...`), on mbdeploy farm node
magni (192.168.1.147), module on J1, joined "Busboom Mesh" and leased
**192.168.1.213**. Every artifact below is in
`captures/tovez-wifi-20260902/` (`notes.md` indexes them). Two
firmware generations were measured: the first WiFi build off master
3b771b7 (`0.20260902.2`), then the branch merged with sprint 028's
executor inversion (`0.20260902.3`, hex `tovez-wifi-tcp-merged-build8`
and the final build 9).

| check | result | artifact |
|---|---|---|
| Discovery by mDNS | `dns-sd -B` lists **"tovez robot link"** under `_robotlink._udp` and `_robotlink._tcp`; `dns-sd -L` resolves to `tovez.local.:7654` with the TXT record; `tovez.local` -> 192.168.1.213 | `mdns-*.log`, `tcp-smoke.log` |
| TCP: raw socket by name and by IP, and `nc` | banner on connect, then `pong`, `ver` replies | `tcp-smoke.log` |
| Every-verb section over TCP, fresh boot (first build) | **39/40** -- all 18 verbs, wheels turning on all six motion verbs | `all-verbs-wifi-tcp-run3.log` |
| Every-verb section over UDP, fresh boot (first build) | **39/40**, identical | `all-verbs-wifi-run2.log` |
| Same section over farm USB, same boot | **40/41**, identical outcomes | `all-verbs-usb-run2.log` |
| Every-verb over TCP, merged build, second idle TCP client connected | **40/40** | `all-verbs-wifi-tcp-merged-run6-second-client.log` |
| Full classic suite over UDP, merged build | 64/70; the 6 failures are the every-verb motion cases refused by the ESTOP latch the preceding bad-cases section sets -- test order, not transport (the classic motion case in the same run turned the wheels) | `wire-acceptance-wifi-udp-merged-run4.log` |
| Cleartext `RUN:gap` carve-out | silent on the first build over USB AND WiFi (pre-sprint-028 behaviour); answers `GAP:0` on the merged build | `usb-rungap-check.log`, `tcp-smoke.log` |
| Radio-era tool over the net: `tour_capture.py --wifi tovez --tour wheels` | full wheels tour captured: 373 pose rows, 374 telemetry frames, 5.3% frame loss (the radio measured 17-33% per-line loss) | `tour-capture-wifi.log`, `tour-wheels-wifi_*.csv` |
| Radio negative control (radio switch off) | through the torture relay tuned to tovez's 55/108: **0/6 PINGs answered** while the same board answers over WiFi | `radio-negative-control.log` |
| PING round trip, idle, UDP | 50/50 answered; min 0.1, **median 40.1**, p90 59.5, max 157.8 ms | `post-reflash-measurements.log` |
| PING round trip while `TLM POSE` streams | 30/30; median 53.3, p90 77.7 ms | same |
| Telemetry cadence over WiFi | 179 frames / 10 s = **17.9 Hz**; gap median 56 ms, p90 79 ms -- the >= 50 ms floor holds | same |
| Ack latency around motion, merged build, TCP vs farm USB | `TLM POSE`, `WHEELS_V`, `STOP`, `MOVE_X`, `STOP`, `PING` all acked in 110-155 ms on both carriers | `ack-latency-during-motion.log` |
| Ten-minute idle TCP hold, then PING | `pong` after 600 s of silence -- no idle timeout | `tcp-idle-hold.log` |
| **Final build 9** (reply-preempts-telemetry), fresh boot: every-verb over TCP, then over UDP | **40/40 and 40/40** | `final-all-verbs-tcp.log`, `final-all-verbs-udp.log` |
| Final build: `tour_capture.py --wifi tovez --tour wheels` | 314 pose rows, 315 frames, 9.2% frame loss (frames are now dropped rather than queued) | `final-tour-capture.log`, `final-tour-wheels-wifi_*` |
| Final build: TCP every-verb again on the SAME boot after the tour | **29/36** -- acks arriving 1-3 s late again; see the open item | `final-all-verbs-tcp-2.log` |
| Final build, fresh boot: 12 x (`WHEELS_V` 1.2 s, `STOP`) with `TLM POSE` on | TCP 24/24 acks, median 72, p90 102, max 128 ms; UDP 24/24, median 79, max 135 ms; none over 800 ms | `final-ack-latency-motion-loop.log` |
| Final build: PING with telemetry off / on, TCP | median 40 / 38 ms; UDP with telemetry on median 50 ms | `final-tcp-latency-vs-telemetry.log` |

A USB round trip is 5-6 ms. The ~40 ms WiFi figure is the module's own
per-`CIPSEND` exchange (prompt, payload, `SEND OK`).

### The one real transport finding: TCP acks are slow when the host delays its acks

One every-verb run over TCP on the merged build (`...-run5-single.log`)
failed 13 cases with `STOP` acks arriving 1-3 s late, while the
identical run minutes later passed 40/40 (`...-run6-second-client.log`)
and a targeted probe measured 110-155 ms acks around motion. The
mechanism: for a TCP client the module's `SEND OK` waits for the
client's TCP acknowledgement, and a host that delays acks (macOS,
~200 ms) turns every queued line into hundreds of milliseconds; with
telemetry subscribed, the 8-slot send queue fills with frames and a
reply waits behind seconds of stale telemetry. Two changes close it
(build 9): frames are queued only into an IDLE send engine (nothing
queued, nothing in flight), and a reply purges any frames still
waiting -- a stale frame is worthless, a late ack stalls the host.
`tests/host/test_wifi_link.py` pins both.

## Things that cost time, so you don't pay them again

- **PXT exports any plain `enum Name {` it finds in a C++ file into
  `enums.d.ts`, then fails the build with "please add 'enums.d.ts' to
  files".** Its regex is `^\s*enum\s+(|class\s+|struct\s+)(\w+)\s*({|$)`,
  so an explicit underlying type (`enum State : uint8_t {`) is not
  matched. Every enum in `wifi_link.h` carries one for that reason.
- **Remote flashes to tovez fail about one time in three** ("Timeout
  reading from probe" mid-programming after the mass-erase path), and a
  failed flash leaves the board with NO firmware. The immediate retry
  has succeeded every time. Treat a probe timeout as "retry once";
  check `INFO` on the `_mbflash` service afterwards.
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
- **`nc` exits when its stdin closes**, so `printf ... | nc host 7654`
  prints nothing; keep stdin open (the tool, or an interactive `nc`).
- **The `+IPD` header's characters also flow into the status-line
  accumulator**; a `0,CONNECT` following a payload with no newline
  between them was glued onto the header text and never parsed.
  A completed header now clears that buffer.
- **The robot's DBG line comes out on USB only on a state change** (and
  every 10 s while not ready); it also goes to the WiFi client on the
  new-peer / new-client edge, which is why a fresh connection shows one.
- The module keeps its AP join across an nRF reset, so after a
  reflash the `AT+CWJAP?` poll lands immediately and the link is back
  within seconds; the 6-170 s join is only paid from a cold module.
- `wire_acceptance.py`'s classic sections end with ESTOP, which latches;
  the every-verb section's motion cases then read as refusals. Use
  `--only-all-verbs --no-estop` on a fresh boot for a clean full pass.

## Open items

0. **Late TCP acks after earlier sessions on the same boot -- NOT
   resolved.** Two of six every-verb runs over TCP on the merged builds
   (`...-run5-single.log`, `final-all-verbs-tcp-2.log`) had acks arrive
   1-3 s late, always in a run that followed a previous WiFi session on
   the same boot (a tour capture, or an earlier acceptance pass); every
   fresh-boot run passed 40/40 and every targeted latency loop measured
   under 135 ms, including with telemetry streaming. The
   reply-preempts-telemetry change (build 9) did not remove it. The
   host's delayed TCP acks were the first hypothesis, but the fresh-boot
   loops do not show it. Next thing to try: capture the module's own
   `DBG:wifi` counters (drop=, sent=) and the `+IPD` link ids across a
   session boundary -- a stale `0,CLOSED` (client gone, module still
   holding link 0) would make sends to that link block on TCP
   retransmits. Until then: UDP (`--wifi`) for telemetry-heavy captures
   and long sessions; TCP for interactive use and `nc`.
1. The 60 s peer-silence forget and the backoff/restart path were
   exercised only under the host tests, not on the bench.
2. No authentication on :7654 -- anyone on the LAN can drive the
   robot. Same open decision the earlier exploration flagged.
3. Replies go to the newest/last-speaking client only; a second
   observer client sees nothing. Fine for one agent at a time; a
   fan-out would be new design.
4. `tour_capture` over WiFi saw 5.3% telemetry-frame loss (queue-full
   drops under the 50 ms floor). The radio's 17-33% per-line loss was
   the reason the tour tools grew retries; those retries stay in place.

Robot assignment note: tovez was assigned for this work by the
stakeholder on 2026-09-02. There is no standing rule about which agent
owns which robot; the assignment is per session and per machine.
