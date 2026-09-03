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

## Discriminator: is the brick powered? (2 mm kick over farm serial)

The wifi-transport session pointed out the module is powered from the
Nezha brick's rail through the RJ11 jack, so an unpowered brick and an
unplugged J1 cable look identical from the UART. `connL`/`connR` are
unwritten until the kernel steps ([[kernel-reads-are-published-snapshots]]),
so the board got a 2 mm `MOVE_X` kick first. Transcript (meili:43659):

```
> HELLO
< device NEZHA2 robot tovez 2314287040
> STATUS
< status ready=0 active=0 connL=0 connR=0 otos=1 wedge=0 flags=0 i2cf=0 cyc=0 tlm=off next=1 done=0 reason=none
> MOVE_X 2 0 60 1000 #1
< ack 1 0 none
> STATUS
< status ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 flags=31 i2cf=2 cyc=43 tlm=off next=2 done=1 reason=timeout
> PING
< pong 241223
```

- `connL=1 connR=1`, `cyc=43`, no wedge: the brick's LOGIC is powered
  and answers encoder I2C. The board did not wedge on the I2C
  transaction, so this is not the unpowered-brick-wedge case.
- But the 2 mm move ended with `reason=timeout` (1000 ms) rather than
  completing, and `i2cf=2`. Per `playfield-testing.md`, encoder I2C
  answering is NOT proof the motor drive has power; the brick's logic
  can run from the micro:bit's 3V3 while the battery switch is off.
  A move that times out is what unpowered motors look like.
- Net: consistent with tovez's battery switch being OFF (motor drive
  and, if the RJ11 rail is battery-derived, the module both dark), or
  with the J1 cable/module unseated. UNVERIFIED which; both need
  someone at the bench. No further motion was commanded.
