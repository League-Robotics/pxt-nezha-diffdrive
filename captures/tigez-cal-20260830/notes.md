# tigez calibration session — 2026-08-30 (afternoon)

Tag identified: **AprilTag 57** (tag36h11) on tigez, mount height
117 mm (stakeholder). Registered with the aprilcam daemon
(`register_tag apriltag 57 mount_z=11.7`; camera IS located:
nadir (3.06, -2.80), height 128.23 cm), which moved the reported
world position (38.3, -0.3) -> (35.1, -0.5) cm — a 3.2 cm parallax
correction at that spot, matching height/geometry prediction.

The daemon's idle detection bursts MISS tag 57 in get_tags about half
the time (borderline decode — soft focus at 11.7 cm elevation), but
get_tag / the CLI resolve it on demand every time. OpenCV
DICT_APRILTAG_36h11 decodes it in the same frame at default params.

Radio link: torture pool 192.168.1.12:8760, !CG 55 114, HELLO banner
`device NEZHA2 robot tigez 3527777815`. STATUS, TLM FULL snapshot
(all-zero counts), TLM OFF all worked sequenced (#1..#3).

## WEDGE — first motion command killed the board

`MOVE_X 80 0 100 22000 #4` was ACKed, then the robot went silent
mid-session: no further STATUS replies on the same open link, camera
shows 0.10 cm displacement (noise — did not move), and a fresh
radio_check gives 0/4 pong on 55/114 AND on 4/10.

Pre-wedge STATUS: `ready=0 active=0 connL=0 connR=0 otos=0 wedge=0
flags=0 i2cf=0 cyc=0 tlm=off next=1 done=0 reason=none` — kernel never
ticked, encoders never answered. Same shape as vevov 2026-08-27
(unpowered Nezha brick): micro:bit healthy on radio until the first
motor/encoder I2C transaction, which hangs CODAL's I2C forever.

**Diagnosis: the Nezha brick's motor power is OFF (or the micro:bit is
powered but the brick isn't).** Needs physical intervention: switch the
brick ON and power-cycle the robot. No gauti/BREAK path exists on tigez.

## Bench debug after the second field wedge (~13:3x)

Field power-cycle revived the micro:bit but the SECOND radio MOVE_X
wedged it identically (0/4 pong after, zero camera motion). Moved to
the bench (farm node meili, USB): still silent over USB serial —
plugging USB did not reset it because the brick kept it powered.
`mbdeploy deploy --remote tigez --hex .tmp/deploy-head/built/binary.hex`
hard-reset it (pyOCD), board came back clean.

Bench MOVE_X over USB serial (192.168.1.150:39805), brick ON:

```
MOVE_X 200 0 120 10000 #1 -> ack 1 0 none
STATUS -> ready=1 connL=1 connR=1 cyc=166 flags=31 done=1 reason=stop
TLM FULL through a second MOVE_X 200: 95 t-frames,
  posl 2561->5133 (delta 2572), posr 2577->5133 (delta 2556)
  odom x 202->404 mm, h -> 0; acks: ack1/ack2/ack3 all clean
```

Wheels spin, encoders count, kernel ticks, no wedge. **posl/posr are
in TENTHS of a shaft degree**: believed 202 mm / 2572 counts = 0.0785
mm/count = 0.785 mm/deg = the fleet-default wheel (pi*90mm/360).

CONFIRMED DIAGNOSIS: on the playfield the Nezha brick's motor rail was
OFF while something still powered the micro:bit. Every motor/encoder
I2C transaction on the unpowered rail hangs CODAL forever (same as
vevov 2026-08-27). The board itself and the firmware are healthy.

## Third wedge (~13:5x) — and the real diagnosis: brick battery collapses under LOADED motor start

Back on the field, pre-move STATUS was HEALTHY: `ready=1 connL=1
connR=1 cyc=360 done=2 reason=stop` — the board had run continuously
since the bench (done=2 carried over, no reboot in transit), so the
brick was powering the micro:bit at idle just fine.

`MOVE_X 80 0 100 20000 #1` -> `ack 1 2 stop` -> total silence: every
subsequent STATUS unanswered on the same open link, TLM OFF #2
unacked, radio_check 0/4 on both addresses. Camera: 0.00 cm motion.

Bench vs field, same board, same firmware, same battery:
- bench (USB + wheels UNLOADED): motors spin, encoders count, no wedge
- field (battery only + wheels LOADED): board dies at motor engage,
  every time (3/3)

USB kept the micro:bit alive on the bench, and unloaded wheels draw
far less than loaded breakaway current. On the field the loaded
breakaway inrush collapses the brick's supply and the micro:bit
browns out / wedges mid-I2C.

**Diagnosis: tigez's Nezha brick battery is flat or failing — it holds
idle load but collapses under loaded motor start.** Fix: charge or
replace the brick's battery. The board needs another power-cycle first
(third wedge).

## ROOT CAUSE FOUND (bench, ~14:0x-14:2x): fw 1.20260829.1 wedges on radio+motion

Retraction first: the earlier "brick battery collapses under load"
diagnosis was WRONG (stakeholder called it, correctly). The brick and
battery are fine.

Reproducible kill-test (mbdeploy remote serial to meili + torture
relay 55/114):

| firmware | move w/ radio silent | move w/ radio PINGs arriving |
|---|---|---|
| master (1.20260829.1) | OK (2/2, done=2 cyc=583) | DEAD every time (3/3 bench, 3/3 field) |
| v0.20260829.3 (ver 0.20260829.2) | OK | OK (2/2: 9 + 4 pongs mid-move, done=2 cyc=750) |

Failure signature on master: MOVE_X ack truncated at "ac" (died
mid-serial-write, within ~ms of execMoveX), then BOTH USB serial and
radio dead until pyOCD reset. Also reproduced mid-move: a 3 m move ran
fine for 4 s radio-silent (active=1 cyc=287), radio pings began, ONE
pong answered, then dead. So ANY v6 radio exchange concurrent with the
running motor kernel is fatal, not just kernel start.

WEDGE HAZARD: a wedge mid-move leaves the Nezha brick's last motor
command LATCHED — the wheels keep spinning until a hardware reset
(pyOCD via `mbdeploy deploy`). The move timeout is enforced by the
(dead) kernel, so it never fires.

Regression window: v0.20260829.3..master = 3 commits (ab796aa,
0039e3f, 88b4c77) touching only blocks/*.ts, comms/protocol.{cpp,h},
comms/radio_transport.{cpp,h}, test/test.ts (radio opt-in gates,
enableRadioLink at test.ts top level, group injection). Not yet
bisected to a single commit; the kill-test above is the reproducer
(runs on any benched robot — tovez on hodr is predicted to die the
same way on its 1.20260829.1).

tigez is now running the v0.20260829.3 build (self-derives 55/114
from its silicon name) for calibration. Fleet fw 1.20260829.1 must be
treated as UN-DRIVABLE OVER RADIO until fixed.

## ROOT CAUSE, named by hardware watchpoint (evening)

ssh (`eric@`, no-password sudo) + pyOCD on meili made this decidable.

The board was never "hung": it HARD-FAULTS. pyOCD halt on the wedged
chip: IPSR=3 (HardFault), HFSR=0x40000000 (FORCED),
CFSR=0x00008200 (PRECISERR|BFARVALID), BFAR=0x474E4988. Stacked frame
gave PC=0x29f5e; addr2line -> `DifferentialDrive::controlStep`.
Disassembly of the faulting site:

```
29f5a:  ldr r0, [r4, #4]    ; r0 = this->right_   (the NezhaMotorPort)
29f5c:  ldr r3, [r0, #0]    ; r3 = its VTABLE POINTER
29f5e:  ldr r3, [r3, #56]   ; <-- FAULT: r3 is 0x474E4950 = "PING"
29f60:  blx r3              ; virtual call
```

The motor port's **vtable pointer had been overwritten with the ASCII
radio payload**, so the next virtual call jumped through garbage.

Hardware watchpoint on that word (`catch2.py`, session scratchpad;
breakpoint controlStep -> read `this` -> watch `*(this+4)` i.e. the
right port's vptr at 0x2000bd18) caught the writer:

```
right.vptr = 0x474e4950            <- already corrupted
WRITE pc=0x0004a788 lr=0x0002ece5
```

addr2line: `memset` called from
**`codal::MicroBitRadio::queueRxBuf()`, MicroBitRadio.cpp:222** --
i.e. `FrameBuffer *newRxBuf = new FrameBuffer();`. The allocator
handed CODAL a block that OVERLAPS the live Rig object, and the
value-initialisation zero-filled it. So: **heap corruption, exposed by
the radio RX path's per-packet FrameBuffer allocation** (250-byte
buffers -- `microbit_radio_max_packet_size: 250` in pxt.json). Nothing
to do with the motion code, which is why every fix aimed there failed.

## SHIPPED: fail-safe fault handling (src/platform/nezha_port.{h,cpp})

The reason a fault became a RUNAWAY ROBOT is that `HardFault_Handler`
resolved to the weak default in codal-nrf52's
`gcc_startup_nrf52833.S:303` -- an infinite loop. No panic, no display,
every fiber dead, brick still driving.

Now: `diffdrive_emergency_motor_stop()` writes "run 0" to both motor
ports over I2C with no object/fiber/scheduler dependency, and the
HardFault/MemManage/BusFault/UsageFault handlers call it and then
`NVIC_SystemReset()`. `DIFFDRIVE_FAULT_SPIN` builds a debug variant
that holds the fault state (motors already stopped) for pyOCD.
Do NOT print from the handler: `uBit.serial.printf()` blocks there
forever (measured -- board stayed in the handler, IPSR=3).

MEASURED after the fix, 8 moves with radio hammering:
**0 unrecoverable, 8/8 faults auto-recovered, 43 radio replies.**
The fault still happens every move -- the heap corruption is NOT fixed
-- but it is now a ~1 s self-healing reboot instead of a runaway robot.
