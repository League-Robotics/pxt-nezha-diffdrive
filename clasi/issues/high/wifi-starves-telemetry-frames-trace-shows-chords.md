---
status: pending
---

# WiFi starves telemetry frames: the console's path trace draws chords across turns

## Description

Observed 2026-10-17 on `tigez` (`1.20261006.1`, no OTOS, pose = encoder
odometry) over WiFi from the robot console. Drove forward, pressed the
pad's 90° right turn (`MOVE_X 0 -1571 0 ...`), drove forward again. The
trace shows a straight diagonal of about 2 cm x / 6 cm y at the corner:
not a drift, but a straight line between the last frame received before
the turn and the first frame received after the second forward move was
already 6 cm along.

Measured at the host's WebSocket (every frame the host decodes for
`wifi-tigez`, `tlm=pose` subscribed, `kTelemetryEmitPeriod` 50 ms):

| condition | frames received | median gap (robot `now`) | max gap | seq skipped |
| --- | --- | --- | --- | --- |
| idle, 15 s | 0 | — | — | all |
| one unsequenced reply every 150 ms, 6 s | 10 | 504 ms | 1788 ms | 88 of 98 |

The second row is the traffic a held pad button produces (`WHEELS_V`
every 150 ms, each acked). At 150 mm/s a 500 ms gap is 7.5 cm between
trace points and 1.8 s is 27 cm. USB and radio were not measured.

## Cause (wifi_link.cpp)

- `telemetryAllowed()` refuses a frame unless `txCount_ == 0 &&
  sendPhase_ == kIdle`, so a frame is only ever queued when the ESP-AT
  send engine has nothing in flight. Every ack or reply during a drive
  occupies it.
- `sendLine()` calls `purgeTelemetry()` on every non-telemetry line, so
  a frame that was queued is discarded by the next ack.
- The idle case (zero frames with nothing else on the link) is not
  explained by the two rules above and needs a look: a telemetry frame
  is addressed to `replyLink_`, which is the TCP client after a
  `STATUS` reply, so something else keeps the gate shut between the
  host's 2 s status polls.

## Proposed resolution

Give telemetry one reserved send slot of its own: allow a frame
whenever that slot is free rather than only when the whole engine is
idle, and replace purge-on-reply with "a newer frame replaces the
queued one". Count telemetry frames refused and purged separately in
`dropCount_` and show them on `STATUS`. Then re-measure the table above.

---

## Triage 2026-10-27 — HIGH

Recent (2026-10-17) and real, but it is the robot console's trace quality over WiFi, not the current zuvat work, which runs over a serial bridge. Same fix area as `wifi-transport-truncates-multi-line-replies`; do the two as one ticket.
