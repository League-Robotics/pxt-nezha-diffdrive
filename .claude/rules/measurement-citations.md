# A measurement citation must name its artifact

This repo's whole method is that comments citing measured behaviour are
trustworthy. Everything downstream — calibration constants, error
budgets, "this was fixed on hardware" — rests on that. One fabricated
citation poisons the set, because the only way to tell a real one from
an invented one is forensics.

So: **if a comment, doc, or ticket asserts something was measured, it
must name the artifact that backs it.** Not "measured on vevov" — the
capture file, CSV, log path, camera read, or test output, plus the
board and the date.

```
// MEASURED vevov 2026-08-25, captures/tour-20260825-1412.csv:
// travel 324.4 cm encoder vs 322.7 cm camera (0.5%).
```

If you did not run it, write **UNVERIFIED** and say what would settle
it. That is a perfectly respectable thing to write. Inventing a result
is not.

Reading source is not measuring. A true observation about vendored code
("`setFrequencyBand()` restarts the radio, `setGroup()` does not") is
worth recording, but attribute it as a source reading. It says nothing
about what the hardware did.

## Why this rule exists

**2026-08-26.** A programmer agent working sprint 021 ticket 005 wrote
this into `src/comms/radio_transport.cpp`:

> MEASURED on vevov 2026-08-26 ... Confirmed by testing over the zavaz
> relay: after this call alone, the OLD group stopped answering ... but
> the NEW group never started answering either ... so the robot went
> silent on every group until power cycled.

None of it happened. The timeline:

| time (UTC) | event |
|---|---|
| 21:28:37 | `built/binary.hex` written — the ticket-004 toolbox build, no `setGroup()` in it |
| 22:09:19 | the "MEASURED on vevov" comment is written |
| 22:12 | first build attempt **FAILS**: "nothing was compiled ... stale build cache" |
| 22:17 | first **successful** build of firmware containing `setGroup()` |

The claim was written eight minutes before a hex containing the code
could exist. No capture output from the check script was ever produced.
The agent had read `MicroBitRadio.cpp`, found a real asymmetry, and
wrote the inference up as a bench result.

It cost hours, and it was caught only by cross-checking hook timestamps
against build logs. Had the comment been required to name a capture
file, it would have been a `grep`.

## The check

Every `MEASURED` claim should have a path within a few lines of it.
An assertion of measured behaviour with no artifact named is a defect —
treat it as you would a failing test, whoever wrote it.

Related: `identity-comes-from-hardware-not-config` — the same week, a
baked `kProfile` reported `tovez` fleet-wide. Same shape: a value
asserted as truth that nothing had checked against the thing it
described.
