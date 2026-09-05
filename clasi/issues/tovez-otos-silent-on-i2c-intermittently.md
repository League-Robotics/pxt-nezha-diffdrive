---
status: pending
---

# A late OTOS power-on cannot recover it: `otosBegin()` is one-shot

MEASURED tovez 2026-09-04, firmware 1.20260903.1,
`captures/session-a-20260904/notes.md` and
`captures/session-a-20260904/otos-boot-banner-watch.log`.

## Root cause: the OTOS's own power/enable was OFF. The sensor is fine.

This issue has been wrong twice; both errors are left visible because
the reasoning matters more than the tidy answer.

1. First it claimed an "intermittent physical fault -- a marginal I2C
   connection or power feed." Wrong: no reseat was needed.
2. Then it claimed "the Nezha brick was off." **Also wrong** -- the
   brick was demonstrably powered the whole time. The robot drove
   ~30 cm under command on every one of the three Session A boots,
   camera-measured, and `connL=1 connR=1` once the kernel ticked.
   Motors do not turn on an unpowered brick.

What was actually off was power or an enable to the **OTOS
specifically**. The stakeholder switched something on and the sensor
answered immediately; **which device that was has not been established
and is deliberately not named here.** The drivetrain was powered
throughout, which is why `connL`/`connR` came up normally while `otos`
stayed 0.

Once the stakeholder powered it on, a forced retry answered immediately
and correctly:

```
RUN:probe  ->  OPROBE:95:1        # 95 == 0x5F == kExpectedProductId
STATUS     ->  ... otos=1 ...
```

No reseat, no rewiring, no power-cycle. The sensor was never faulty.

`.claude/rules/playfield-testing.md` already says, in its own section
heading, "**The robot is OFF -- check this first**." The evidence was
consistent with an unpowered brick the whole way through
(`connL=0 connR=0 otos=0` at every boot before the first tick) and
"marginal connection" was a more exotic explanation than the facts
required. Recorded here so the next reader reaches for the power switch
before the soldering iron.

## The real defect: one failed probe latches `otos=0` for the session

`otosBegin()` is called **exactly once**, at boot
(`test/test.ts:819`). `OtosPort::begin()` sets
`initialized_ = ok && (id == kExpectedProductId)`, and `connected()`
returns `initialized_ && connected_`. Nothing retries automatically --
the only other call sites are the `RUN:probe` handler
(`test.ts:647`) and the `calibrate world sensor` block
(`src/blocks/world.ts:22`), both operator-triggered.

So if the OTOS is unpowered (or the chip merely slow) at that instant,
the board reports `otos=0` **for the rest of the session**, and powering
it on afterwards changes nothing. That is exactly what was observed:
`STATUS` still read `otos=0` with `cyc=0` after the sensor came on, and
only the forced `RUN:probe` retry brought it up.

This is a real usability defect. A student or bench operator who
powers the sensor on a moment late gets a board that silently has no
world sensor, with no indication that a retry would fix it -- while the
drivetrain works perfectly, which makes it look like a sensor fault
rather than a sequencing one.

### Suggested fix

A bounded retry: re-attempt `otosBegin()` on a backoff (or on the first
world-frame read that finds `connected() == false`) instead of trusting
one probe at boot. Cheap, and it makes power-on ordering stop mattering.

## Secondary: a silent OTOS blocks the command channel

With the OTOS unpowered, `RUN:probe`'s read stalled the host past its
2 s timeout; `PING` afterwards answered normally, so the board did not wedge
-- the wire was simply unresponsive for the duration. RUN handlers run
on the protocol fiber, so an unresponsive sensor freezes the whole
command channel.

Same failure class as sprint 032 ticket 002, now observed on hardware
rather than argued from source. Worth citing there.

## What this does NOT affect

Sprint 031 Session A's travel and yaw-drift figures stand. `connL=1
connR=1` throughout every run once the kernel ticked, and the OTOS is
not in the wheel-odometry or camera measurement path. Boot 1
(`otos=1`) and boots 2-3 (`otos=0`) agree on both headline numbers,
which is itself evidence the OTOS state did not affect them.
