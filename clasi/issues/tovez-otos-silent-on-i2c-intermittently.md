---
status: pending
---

# A late Nezha-brick power-on cannot recover the OTOS: `otosBegin()` is one-shot

MEASURED tovez 2026-09-04, firmware 1.20260903.1,
`captures/session-a-20260904/notes.md` and
`captures/session-a-20260904/otos-boot-banner-watch.log`.

## Root cause: the Nezha brick was OFF. The sensor is fine.

An earlier revision of this issue concluded the OTOS had an
"intermittent physical fault -- a marginal I2C connection or power
feed." **That was wrong**, and the correction matters because it points
at a completely different fix.

The brick was simply off. Once the stakeholder powered it on, a forced
retry answered immediately and correctly:

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

So if the brick is off (or the chip merely slow) at that instant, the
board reports `otos=0` **for the rest of the session**, and powering the
brick on afterwards changes nothing. That is exactly what was observed:
`STATUS` still read `otos=0` with `cyc=0` after the brick came on, and
only the forced `RUN:probe` retry brought it up.

This is a real usability defect. A student or bench operator who
switches the brick on a moment late gets a board that silently has no
world sensor, with no indication that a retry would fix it.

### Suggested fix

A bounded retry: re-attempt `otosBegin()` on a backoff (or on the first
world-frame read that finds `connected() == false`) instead of trusting
one probe at boot. Cheap, and it makes power-on ordering stop mattering.

## Secondary: a silent OTOS blocks the command channel

With the brick off, `RUN:probe`'s read stalled the host past its 2 s
timeout; `PING` afterwards answered normally, so the board did not wedge
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
