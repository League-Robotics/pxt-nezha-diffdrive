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

## WiFi on the playfield, 2026-09-04: not usable this session

- **tigez and vevov were built WITHOUT WiFi credentials.** `build-tigez.log`
  and `build-vevov.log` both say `no .../config/wifi_secrets.json -- WiFi
  link stays DISABLED in this build` (the secrets file lives in the
  wifi-transport worktree, not the main checkout the fleet build ran
  from; gopiv's hex was the one built with it: `WiFi link ENABLED,
  ssid='Busboom Mesh'`). Their modules are fitted but the firmware never
  drives them (`DBG:wifi state=0 ... restarts=0 sent=0` over the relay
  from tigez, 11:2x). Fix: copy `config/wifi_secrets.json` into the main
  checkout and reflash -- impossible today (no Pi Zeros on the field).
- **gopiv's WiFi TCP link died under motor load** during the first sweep
  (`gopiv-baked.log`: BrokenPipe mid-sweep, then
  `wifilink: gopiv not found by mDNS ... or by broadcast HELLO`), and
  `dns-sd -B _robotlink._tcp` found no announcement afterwards. The
  module answered on the bench with the wheels idle. UNVERIFIED whether
  it is a brown-out of the module on the brick's RJ11 rail when the
  motors draw, or the module rebooting; needs the USB console during a
  pivot to settle it.
- All three sweeps therefore ran over the torture relay pool
  (`turn_calibration.py --radio`). Relay lesson: a killed host session
  leaves the robot's `TLM FULL` stream running; at ~15 frames/s over the
  radio the robot then stops hearing commands (HELLO/TLM OFF/STOP
  unanswered across ~30 tries on tigez) and only a power cycle clears it.
  Some pool relays (guvov) need `!GO` before passing lines through.

**Update, 2026-09-04 afternoon:** tigez reflashed on meili with the secrets
copied in -- WiFi link up, 40/40 acceptance, 20/20 bench pivots over TCP:
`captures/tigez-wifi-reflash-20260904/notes.md`. vevov still carries the
WiFi-disabled build.
vevov and gopiv reflashed the same afternoon (1.20260904.3): vevov 40/40
+ 20/20 soak (`captures/vevov-wifi-reflash-20260904/`); gopiv's module was
silent until its brick was switched on, then 40/40 + 20/20
(`captures/gopiv-wifi-reflash-20260904/`). All three boards now run WiFi
+ radio builds.
