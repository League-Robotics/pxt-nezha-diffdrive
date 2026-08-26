---
status: done
sprint: 019
tickets:
- 019-001
- 019-002
- 019-003
- 019-004
---

# Wire and shim minors: HELP truncation, a re-typed product id, undocumented duty units

Priority: **Medium** -- four small, independent, individually cheap fixes.

## `execHelp()` silently truncates and can drop its own terminator

`wire_handler.cpp:779` builds the HELP reply with a lambda bounded at
`pos < sizeof(buf) - 1`, and appends the newline **last**. Today's 18 verbs
produce ~110 bytes against a 240-byte buffer, so it fits. The landmine: the
first thing lost to truncation is the line terminator, and a HELP reply without
a newline is a line the host's reassembler never completes -- it glues the next
reply onto it.

`execRun()`, twenty lines below, gets this right (a `kMaxLineBytes + 1` buffer
with a comment on exactly this hazard). `execHelp` has neither the guard nor a
test.

**Fix**: a `static_assert` on the summed table width, or reserve a final byte
for the newline, or emit HELP as multiple lines when it would overflow.

## The OTOS product id is re-typed across the shim boundary

`platform/otos_port.h:102` defines `kExpectedProductId = 0x5F` and gates
`initialized_` on it. `blocks/world.ts:20` independently re-types the literal
(`return otosBegin() == 0x5F`), plus a third statement in a `shims.cpp:1081`
comment.

If the id ever changes, the port initializes fine, `connected()` goes true,
`worldTrackingReady()` returns true, `engineGoToW()` selects the OTOS -- and
`startWorldTracking()` returns **false**, so every program gated on it refuses
to run against a healthy sensor, disagreeing with its own sibling readback.

**Fix**: `startWorldTracking()` should call `otosBegin()` and return
`worldTrackingReady()`. The caller has no business knowing the product id.

## `dutl`/`dutr` are percent x 100, and nothing says so

`NezhaMotorPort::appliedDuty()` returns a fraction in [-1, 1];
`diffdrive.cpp:795` multiplies by 100 (so `Output.appliedDutyLeft` is
**percent**, as `diffdrive.h:136` documents); `shims.cpp:797 diagValue(12)`
multiplies by 100 **again**. So `probe(12)` and the wire's `dutl` column read
**10000 at 100% duty**.

Both source comments say "duty x100", which reads naturally as "percent" and is
wrong by 100x. `tools/tlm.py:249-259` -- the module that calls itself *"The only
place any wire -> engineering-unit scale factor is written"* -- documents `x`,
`y`, `ox`, `oy`, `h`, `oh`, `vl`, `vr` and **omits `dutl`/`dutr` entirely**.

**Fix**: add the two columns to `tlm.py`'s unit table with the derivation, and
change the two source comments. Also worth asking whether the second x100 earns
its place -- the wire is text, so integer percent loses nothing.

## A "no-op" motion command does not stop prior motion

`wheelsX()`/`wheelsV()` call `cancelMove()` (which clears the move-engine flag
**without touching the kernel**) and then return early on a zero-magnitude or
non-positive-cruise command; `moveX()`/`startSegment()` do the same without even
that. The kernel's previous command and lease survive.

So `WHEELS_X 0 0 100 1000` during a `WHEELS_V` hold is acked `ok`, clears the
planner, and **the robot keeps driving**. The wire's `cruise` refusals close
most routes in, which is why this is Medium and not High -- but the documented
contract ("a no-op -- nothing is driven") is not what it does when something was
already driving. Same family as `stop-move-does-not-stop-continuous-drive.md`.

Detail: [`docs/code-review/2026-08-26/raw/correctness-wire-blocks.md`](docs/code-review/2026-08-26/raw/correctness-wire-blocks.md).
