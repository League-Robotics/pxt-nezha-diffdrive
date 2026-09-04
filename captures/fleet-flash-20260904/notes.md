# Fleet reflash for the playfield rotation comparison, 2026-09-04

Built from master 7802ed9 (version 1.20260903.2) with
`tools/make_deploy.py --robot <name> --radio-link`, one hex per robot
(`build-<name>.log`, sha256 at the end of each), flashed over the farm
with `mbdeploy deploy --remote <name>` -- all three on the first try
(`flash-<name>-1.log`). Script: the scratchpad `fleet_flash.sh`, log
`run.log`.

| robot | node | bake (travel_calib / trackwidth / slip / overrun) | WiFi baked | radio link | verified over the wire |
|---|---|---|---|---|---|
| tigez | meili 192.168.1.150 | 0.78623 / 114.4 / 0.9617 / 5.5 mm | no (no module) | on, 55/114 | `id diffdrive tigez 1.20260903.2 tigez`, slip 0.962, overrun 5.5 |
| vevov | magni 192.168.1.147 | 0.70066 / 128 / 0.987 / 2.2 mm | no | on, 37/43 | `id diffdrive vevov 1.20260903.2 vevov`, slip 0.987, overrun 2.2 |
| gopiv | hodr 192.168.1.148 | none (firmware defaults: slip 0.952, overrun 0) | yes, Busboom Mesh | on, 47/60 | `id diffdrive gopiv 1.20260903.2 gopiv`, overrun 0 |

The v6 radio link is ON in these builds (`BOOT_RADIO_LINK = true`) so
every board stays reachable through the relay pool on the playfield
regardless of Pi or module; the calibration tool's `--radio` carrier
uses it. gopiv's WiFi state: see `gopiv-wifi-listen.log`.

Farm serial ports are dynamic; the verify step in `run.log` resolved
tigez by mDNS, then died on vevov's `_mbserial._tcp` lookup (the name
was not resolvable at that moment), so vevov and gopiv were verified by
hand with `mbdeploy connect --remote`.

## gopiv's WiFi module is silent (same symptom as tovez on 2026-09-03)

40 s on hodr's serial port after the flash (`gopiv-wifi-listen.log`):
`DBG:wifi state=1 ... restarts=4..5 sent=0 rx=0 cmd=AT+CWMODE=1 reply=`
-- the firmware drives the UART and cycles configure -> backoff, and not
one byte comes back from the module. So gopiv never joins or announces
(`wifilink.py --tcp --robot gopiv` finds nothing). Module unplugged /
unseated on J1, or unpowered (the RJ11 rail comes from the brick, and a
brick with its battery switch off looks identical from the UART).
UNVERIFIED which; needs a look at J1 and the module's LEDs. Until then
gopiv is reached over the farm USB on the bench and the radio relay on
the playfield (link ON in this build).
