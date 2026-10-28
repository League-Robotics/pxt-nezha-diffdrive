---
status: pending
---

# zuvat: `i2cf` grows 2 to 4 per position move and 7 to 9 per 1.5 s of `WHEELS_V`

Seen 2026-10-27 during sprint 043 ticket 002 on zuvat (042 build, farm
node loki over the serial bridge): STATUS `i2cf` climbed from 0 to 117
over the bring-up session, about 2 to 4 per `MOVE_X` position move and 7
to 9 per 1.5 s of `WHEELS_V`, with `wedge=0` throughout and both wheels
always moving. Captures: `captures/zuvat-position-2026-10-27/` (per-case
logs, `notes.md`). Not diagnosed. Related to the older
`i2c-fault-count-climbs-on-idle-bus.md` in `clasi/issues/high/`? That one
was idle; this one scales with motion, so it may be the brick refusing or
delaying frames while a move is live (the sniffed `C0` "refused in servo
mode mid-move" ack is a candidate), or the position-move latch's encoder
reads colliding with the brick's own 400 ms ping.

## To settle it

Count `i2cf` per frame type on the sim bus (host) and, on zuvat, per
`position_mode 0` vs `1` over the same leg; sniff the brick with the ESP32
harness if the counts differ.
