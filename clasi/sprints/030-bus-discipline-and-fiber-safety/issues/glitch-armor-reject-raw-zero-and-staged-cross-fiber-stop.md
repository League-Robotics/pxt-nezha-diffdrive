---
status: in-progress
sprint: '030'
tickets:
- 030-004
---

# Glitch armor: reject a raw-zero encoder read explicitly; prefer a staged stop over a cross-fiber write while stepBusy

Priority: **Low** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Finding: RC-02 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)). Triage #16.

## Description

`deliverStopNow()` (`shims.cpp:336`) and the watchdog (`:825-828`) write
the motor register from whichever fiber calls them, by design (sprint 006),
which is the Phase-F interposition the design forbids elsewhere. A
destroyed sample "reads as raw 0" (`nezha_port.cpp:378-379`), and
`EncoderGlitchArmor` rejects only `|raw - lastGood| > 5000`
(`encoder_glitch_armor.h:98`). The 0x46 counter is never device-reset, so
for the first ~40 cm after the brick powers up a raw 0 is within 5000 of
the last good value and is accepted as real motion; position jumps toward
0 and back and `odomUpdate()` integrates both.

## Remedy

- Reject `raw == 0` when `lastGoodRaw != 0` (the documented Phase-F
  signature) as `kRejectPending`.
- When `stepBusy` is set, stage the stop for the busy fiber to deliver at
  the end of its step instead of writing across it; keep the immediate
  write for the not-busy case.

## Acceptance

- `test_encoder_glitch_armor.py`: a raw 0 after a nonzero good value is
  rejected; a genuine counter restart (two consistent implausible reads)
  still rebaselines.
