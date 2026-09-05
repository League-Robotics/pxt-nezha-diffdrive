---
status: pending
---

# tovez's OTOS is intermittently silent on the I2C bus (physical, not firmware)

MEASURED tovez 2026-09-04, firmware 1.20260903.1,
`captures/session-a-20260904/otos-boot-banner-watch.log` and
`captures/session-a-20260904/notes.md`.

## What was measured

Across four power cycles in one session, `STATUS` reported `otos=1` on
the first boot and `otos=0` on the three that followed. The firmware's
own boot banner on a failing boot:

```
OTOS:boot:id=0:connected=0
```

`OtosPort::begin()` takes that id straight from
`readReg8(kRegProductId, &id)` with `id` pre-initialised to 0, and
`readReg8` returns false on a NAK without writing `val`. **id=0 means
the chip did not answer at all** -- distinct from a wrong device
(non-zero id != 0x5F) or an init-logic bug (id == 0x5F, connected=0).

A `RUN:probe` retry well after boot did not recover it: the host timed
out at 2 s, `PING` afterwards answered normally (`pong 217661`), and
`STATUS` still read `otos=0 i2cf=0`. So the sensor is **silent, not
slow**, and a retry alone will not fix it.

Because it answered on one power-up and not the next, the chip is not
simply dead. This points at a **marginal I2C connection or power feed
to the OTOS**.

## Why this is filed as hardware

The firmware reported the fault accurately and immediately via its boot
banner. It is not misreporting a healthy sensor.

## Two firmware weaknesses this exposed (worth fixing, but NOT the cause)

1. **One-shot init with no retry.** `otosBegin()` is called exactly once
   at boot (`test/test.ts:819`); one failed probe latches `otos=0` for
   the entire session. The only other call sites are `RUN:probe` and the
   `calibrate world sensor` block, both operator-triggered. A bounded
   retry with backoff would at least survive a slow-to-wake chip.
2. **A silent OTOS blocks the command channel.** The `RUN:probe` read
   stalled the host past 2 s. RUN handlers run on the protocol fiber, so
   an unresponsive sensor makes the whole wire unresponsive. This is the
   same failure class sprint 032 ticket 002 addresses -- now observed on
   hardware, not argued from source.

## Suggested next steps

- Physically inspect the OTOS's I2C wiring and power on tovez; reseat.
- Re-run the boot banner check across several power cycles and record
  the `otos=1` / `otos=0` ratio before and after any reseat.
- Consider the bounded-retry change independently; it is cheap and makes
  a marginal connection far less disruptive.

## What this does NOT affect

Sprint 031 Session A's travel and yaw-drift figures stand: `connL=1
connR=1` throughout, and the OTOS is not in the wheel-odometry or camera
measurement path. Boot 1 (`otos=1`) and boots 2-3 (`otos=0`) agree on
both headline numbers.
