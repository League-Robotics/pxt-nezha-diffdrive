# `configure motor` on hardware — tovez, 2026-09-12

Board: tovez, fw 1.20260912.6 (+ uncommitted diag ordinals 35-40 and the
`wire`/`setwire`/`spinone` RUN verbs). Carrier: WiFi TCP to
tovez.local -> 192.168.1.187. Bench stand, wheels up.

## 1. The call changes the live wiring

Read out of the two NezhaMotorPorts (diag 35-38), not from a copy of the
request.

    RUN setwire 21          # left, port 2, forward
    WIRE before  leftPort=2 leftSign=-1 rightPort=1 rightSign=1
    WIRE after   leftPort=2 leftSign=1  rightPort=1 rightSign=1

Persisted across later, separate commands and survived a MOVE_X.

## 2. The swap — the call that used to be a silent no-op

    RUN setwire 12          # left asks for port 1, where RIGHT lives
    WIRE before  leftPort=2 leftSign=-1 rightPort=1 rightSign=1
    WIRE after   leftPort=1 leftSign=-1 rightPort=2 rightSign=1

The pair exchanged ports; right kept its own +1.

## 3. Direction actually reverses — the physical measurement

`spinone 0` drives the LEFT wheel at 12 cm/s for 600 ms and reports the
brick's own counter (diag 39), which does NOT pass through fwdSign.
Same command every time; only the direction dropdown changed:

| leftSign | rawDelta | posDelta |
|---|---|---|
| -1 | -472 | +472 |
| +1 | **+352** | -370 |
| -1 | -467 | +115 |

The raw counter reverses with the sign and flips back when restored, so
the motor physically turns the other way. posDelta cannot show this:
position = (raw - offset) * fwdSign, so it stays self-consistent under a
flip -- which is exactly why the original no-op was invisible.

## Two traps this run hit

**The stall latch, not a dead brick.** Every move first came back
`reason=stall` with `rawDelta=0` on both wheels, which looks exactly like
the documented "robot is switched off" signature. It was not: `flags` is
printed in HEX, and `flags=35` is 0x35 = ready|stallHalted|connL|connR --
the stall latch was set and the estop bit was clear. `SET stall_clear 1`
(the field NAME; `SET 17 1` by ordinal silently does nothing) cleared it,
`flags` went to 0x31, and the wheels turned. Decode the hex before
concluding anything about power.

**connL/connR are a stale snapshot until the kernel ticks.** They read 0
with `cyc=0` on a perfectly healthy board; one MOVE_X and they read 1.

**tovez's USB serial drops ~half its characters** on this cable -- via
`mbdeploy connect` as well as a pyserial session (`WRE now letPort=2`,
`rawBefoe=42478`). Every number above came over WiFi TCP, which was
clean. Its IP is 192.168.1.187, not the 192.168.4.11 in tovez.json.
