# gopiv hardware acceptance attempt -- 028/001, 2026-09-02

**Outcome: BLOCKED.** Could not flash the ticket's build to gopiv, so
`captures/gopiv-profile-sweep-20260901/tight_tour.py` was never re-run
and no MEASURED re-run capture exists for this ticket. This file
documents exactly what was tried and observed, per
`.claude/rules/measurement-citations.md` -- nothing below is a MEASURED
claim about the fix's on-hardware behavior; it is UNVERIFIED pending a
working flash path.

## Build

`uv run python tools/make_deploy.py --robot gopiv` (after wiping
`.tmp/deploy-head/`, which held a stale `--robot tigez` scratch build)
succeeded cleanly: `.tmp/deploy-head/built/binary.hex` (1,585,241
bytes), attempt 1. `nezha_port.cpp` compiled with no new warnings (one
pre-existing sign-compare warning at line 469, unrelated to this
ticket's change).

## Flash attempts (all failed identically)

`uv run mbdeploy deploy --remote gopiv --hex .tmp/deploy-head/built/binary.hex`,
five separate invocations across ~13:25-13:33 PDT:

```
0004300 C SWD/JTAG communication failure (No ACK); check USB cable, reduce debugger clock [__main__]
flash failed with a transient-looking probe/communication error -- retrying once before any mass-erase decision.
0003186 C SWD/JTAG communication failure (No ACK); check USB cable, reduce debugger clock [__main__]
Error: flash failed (exit 1) with no recognized recoverable signature -- not mass-erasing.
Error: flash failed (exit 1)
```

Every attempt failed with the same `SWD/JTAG communication failure (No
ACK)` on both the initial try and the automatic retry -- a persistent
probe-level failure, not a one-off transient.

## Board-present check

`ssh -i ~/.ssh/raspi-cluster_ed25519 jtl@192.168.1.150 'ls /dev/ttyACM*'`
-> `/dev/ttyACM0` (present). `lsusb` shows the mbed CMSIS-DAP device
(`0d28:0204`) enumerated. So the board is physically connected and its
VCOM/CMSIS-DAP USB interface enumerates -- this is NOT the
"board absent" or obviously "motor power off" case the ticket's
contingency describes.

## Wire-protocol check on whatever firmware is currently running

`uv run mbdeploy connect --remote gopiv "HELLO"` -> `Error: no response
from gopiv (192.168.1.150:38755) within 2s.` Matches the pre-existing
note in the dispatch brief: gopiv does not answer PING/STATUS/VER/HELLO
over the farm right now, on whatever firmware it currently has loaded
(not this ticket's build -- the flash never landed).

## Host-side corroborating evidence

`ssh ... 'dmesg | tail -30'` on the farm host (meili, 192.168.1.150) at
13:33 PDT shows USB host-controller level errors around the same USB
port the micro:bit CMSIS-DAP enumerates on:

```
WARN::dwc_otg_hcd_urb_dequeue:639: Timed out waiting for FSM NP transfer to complete on 5
WARN::dwc_otg_hcd_urb_dequeue:639: Timed out waiting for FSM NP transfer to complete on 1
WARN::dwc_otg_hcd_urb_dequeue:639: Timed out waiting for FSM NP transfer to complete on 0
WARN::dwc_otg_hcd_urb_dequeue:639: Timed out waiting for FSM NP transfer to complete on 6
```

This is the Raspberry Pi's own `dwc_otg` USB host controller reporting
failed/timed-out USB transfers -- consistent with (and a plausible root
cause of) the SWD "No ACK" failures pyOCD reported. No `sudo` available
on this account (`jtl@meili`, per existing fleet convention) to reset
the USB subsystem or power-cycle the port remotely, and no
`mbdeploy` subcommand exists to trigger a USB/probe reset over the
farm.

## Conclusion

The hardware-acceptance criterion in
`clasi/sprints/028-single-executor-honest-encoder-velocity-and-a-frame-zeroing-verb/tickets/001-frozen-encoder-read-holds-the-previous-velocity-instead-of-manufacturing-a-zero.md`
is left **unchecked**, annotated as BLOCKED on a farm-host USB
transport fault external to this ticket's code change, not on
anything the fix itself did. Retry once the meili host's USB
connection to gopiv's CMSIS-DAP probe has been power-cycled or
otherwise recovered (needs a human with physical or `sudo` access to
the Pi).
