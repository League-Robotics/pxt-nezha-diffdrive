# gopiv reflashed with the WiFi link, 2026-09-04 (farm node hodr) -- module silent, brick suspect

Build `build.log`: `WiFi link ENABLED, ssid='Busboom Mesh'`, no geometry
bake (gopiv has none), radio link ON. Hex `gopiv-wifi.hex` sha256
df9842b66e5df89fbd59df3e306ef4dc652637d8882cb3be9c5f6affef635b4d.
Flash `flash-1.log`: first try, 103 pages.

After the flash gopiv never announced on mDNS and gopiv.local:7654 never
opened (2 min). On hodr's serial daemon (port 36133,
`console-listen-2.log`) the firmware is driving the UART and the module
returns nothing: `DBG:wifi state=1 ... restarts=14 sent=0 rx=0 ...
cmd=AT+CWMODE=1 reply=` cycling through ATE0 / CIPSERVER=0 / CWMODE=1 --
identical to `../fleet-flash-20260904/gopiv-wifi-listen.log` yesterday
on the same node, whereas on the FIELD this morning the same board joined,
announced, and ran a sweep over TCP before the link died mid-sweep.

`console-brick-check.log`: at boot `STATUS` read `connL=0 connR=0
i2cf=0 cyc=0` (brick not answering I2C). A 2 cm `MOVE_X 20 0 0 2000 #1`
was acked and then the board went silent -- no `status`, no `pong` in
6 s, no more `DBG:wifi` lines: the dead-brick I2C wedge (CODAL's I2C
timeout never fires). The module is powered from the brick's RJ11 rail,
so an unpowered brick explains the silent module AND the wedge, and a
weak battery browning out under motor load would fit the field dropout.
UNVERIFIED until the brick switch/charge is checked and the robot
power-cycled.
