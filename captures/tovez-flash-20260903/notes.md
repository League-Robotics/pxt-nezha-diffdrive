# tovez reflashed from master 75cd7dc; WiFi module silent on the UART, 2026-09-03

Built from master `75cd7dc` (wifi-transport merged, version 1.20260903.1)
with `config/wifi_secrets.json` present: `make_deploy: WiFi link ENABLED,
ssid='Busboom Mesh'`, hex sha256
`8b1880c2f53278bfaa6b442f5cf882486d3dd0d72288234a55b45b56a0f19a79`
(`build.log`). Flashed over the farm, tovez on node **meili**
(192.168.1.150), `mbdeploy deploy --remote tovez` -- ran twice because
the wrapper's success grep did not match; both completed
(`flash-tovez-1.log`, `flash-tovez-2.log`). Afterwards over farm serial:
`id diffdrive tovez 1.20260903.1 tovez`, `device NEZHA2 robot tovez 2314287040`.

## The WiFi module does not answer

Before the flash (still on 0.20260902.3, which the wifi-transport
session had verified over TCP the day before on node magni) tovez was
already absent from mDNS: a 70 s `rogo --discover tovez` and
`dns-sd -B _robotlink._tcp` saw nothing, and 14 s of farm serial
showed no `DBG:wifi` line at all.

After the flash, the farm serial port (meili:43659) shows the link
state machine cycling with every AT reply EMPTY, 85 s of observation:

```
DBG:wifi state=1 ip=- peer=-:0 tcp=0/0 to=4 restarts=1 sent=0 rx=0 drop=0 mdns=0/0 cmd=ATE0 reply=
DBG:wifi state=1 ... restarts=1 ... cmd=AT+CIPSERVER=0 reply=
DBG:wifi state=1 ... restarts=1 ... cmd=AT+CWMODE=1 reply=
DBG:wifi state=6 ... restarts=2 ... cmd=AT+CWMODE=1 reply=
DBG:wifi state=1 ... restarts=2 ... cmd=AT+CWMODE=1 reply=
DBG:wifi state=6 ... restarts=3 ... cmd=AT+CWMODE=1 reply=
DBG:wifi state=1 ... restarts=3 ... cmd=ATE0 reply=
DBG:wifi state=1 ... restarts=3 ... cmd=AT+CIPSERVER=0 reply=
```

`rx=0` throughout: not one byte has come back from the module since
boot. The firmware is driving the UART (the commands advance, the
restart/backoff path runs), so this is the module side -- unplugged or
unseated on J1, unpowered, or the RJ11 cable disturbed when the robot
was moved from magni to meili. A cold module that simply has not joined
yet answers `AT` with `OK` and reports a join state; this one answers
nothing. `rogo` cannot reach tovez until the module is physically
checked. UNVERIFIED which of those it is; a look at the J1 cable and the
module's LEDs would settle it.
