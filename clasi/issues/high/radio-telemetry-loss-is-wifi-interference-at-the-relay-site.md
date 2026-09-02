---
status: pending
---

# ~25-30% radio datagram loss is WiFi interference at the torture relay desk

Priority: High — every radio-driven capture (bench and field) loses a
quarter to a third of its telemetry frames, and command round-trips
fail ~half the time (measured 2/4 PING on a healthy link), forcing
retries everywhere.

## What was measured (all 2026-08-30 evening, tigez on meili bench, artifacts in `captures/tigez-cal-20260830/`)

| experiment | artifact | result |
|---|---|---|
| USB tap vs radio, same tour | `bench3.json` | tap 943/943 (0.0%), radio 28.2% lost; field run same night 29.3% (`fieldtour4.json`) |
| TLM POSE vs FULL | `losslen.json` | 30.1% vs 28.8% — length-independent |
| two relays (guvov+getez) listening together | `tworx.json` | both miss the SAME frames (strict subset; joint 0.71 vs 0.52 if independent) |
| robot TX counters (scratch diag build, `radio-txcount-diagnostic.patch`) | `txcount.json` | 854/854 sends DEVICE_OK, 0 guard trips — robot transmits 100%, already at max power |
| relay `!DEBUG ON` RSSI | `dbglisten.json` | arriving frames −58 dBm median, none garbled; 21.7% of datagrams produce no RX event at all |
| channel 81 (2481 MHz) scratch build | `ch81.json` | loss 25.6% → 17.2% — better above the WiFi band, not cured |
| per-frame loss vs torture WiFi bytes | `wificorr.json` | monotonic: 16.8% in quietest WiFi quartile → 26.7% in busiest |

torture (192.168.1.12) has **no wired network**: `wlp2s0` (2.432 GHz,
17 dBm) carries every relay's TCP stream; `enp1s0` is UP with no IPv4.
The Busboom Mesh AP reads **−11 dBm** from torture — it is on/next to
the relay desk. Receiving a frame causes a WiFi forward burst that
blinds the relays for the next frame — hence the measured
anti-correlation (P(lost|prev lost) 22.9% vs P(lost|prev rx) 30.4%).

## Remedies (first two are stakeholder hardware calls)

1. Put torture on Ethernet (cable + DHCP on enp1s0) — removes the
   17 dBm co-located transmitter entirely.
2. Move the relay micro:bits a few metres from the mesh node (USB
   extension).
3. Shift the fleet channel plan above the WiFi band (channels 78-83):
   measured ~8 points. Touches the 3-repo addressing scheme
   (`radio-address-derived-from-board-name`).
4. Nothing to gain in robot firmware: TX is 100% at max power.

Full narrative: `reports/tigez-bench-square-tour-20260830.md` addendum.

## UPDATE 2026-08-31 ~00:30: torture wired; the real jammer is Busboom_Garage, IN-CHANNEL

The stakeholder wired torture (enp1s0 now 192.168.1.12, metric 100;
wlp2s0 idle at .200 — 1 kB TX during a full test window). MEASURED
tigez, `captures/tigez-cal-20260830/wired1.json` + `floodtest.json`:

- ch 55 loss with the wire: **22.1%** (was 25.6-30%). ~6 points from
  remedy 1, and the frame-to-frame anti-correlation collapsed
  (21.2%/22.3% vs 22.9%/30.4% before) — the self-inflicted
  forward-burst loop is gone, confirming that mechanism.
- **The dominant jammer is a SECOND house network:** the farm Pis
  associate to `Busboom_Garage`, **freq 2457 MHz (WiFi ch 10, span
  2447-2467)** — which sits directly on top of micro:bit ch 55
  (2455) and ch 47 (2447). The whole fleet channel map
  (25+2·(N%25) -> 2425-2473 MHz) lives inside the two house networks'
  bands (Mesh 2422-2442, Garage 2447-2467).
- **Flood proof** (`floodtest.json`): one continuous TLM stream,
  35 s quiet then 35 s pulling bulk data over meili's Garage-network
  WiFi: loss **24.4% -> 58.0%**. The tap and camera streams the rig
  itself runs during tours are Garage-network traffic — the
  instrumentation jams the link it measures.
- The farm Pis are 2.4 GHz-only, so their traffic cannot leave the
  band. The durable fix is remedy 3: move fleet channels into
  **2476-2483 (micro:bit 76-83)**, clear of both networks. Groups
  already disambiguate shared channels (tigez/tovez precedent), so
  8 channels suffice. Coordinated 3-repo change
  (`radio-addressing-three-repo-split`).
- **Clean-spectrum proof** (`ch81wired.json`, scratch ch-81 build,
  torture wired): quiet **9.1%**, garage flooded **9.3%** — the
  channel move makes the link IMMUNE to garage traffic and cuts the
  quiet-air loss from 22% to 9%. Chart:
  `reports/tigez-bench-square-20260830/radio-loss-by-condition.png`.
  The residual ~9% floor is the desk-adjacent Busboom Mesh AP
  (-11 dBm blocking) and/or BLE advertising at 2480 (remedy 2 — move
  the relays — is the lever for that).
