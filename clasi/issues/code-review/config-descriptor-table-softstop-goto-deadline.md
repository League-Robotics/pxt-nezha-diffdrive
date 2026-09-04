---
status: pending
sprint: '032'
---

# One config descriptor table replacing five ordinal switches; one softStop(); go-to deadline as a config field

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: CO-04, CO-05, CO-06 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)). Triage #11.

## Description

The config surface is five hand-synchronised ordinal tables:
`setKernelValue` (34 cases), `getConfigValue` (34 cases),
`WireAdapter::kFields`, `ConfigField` in TS, and `diagValue` (30 cases).
The "ordinal 30" comment error in `protocol.h:281` is what that costs.
The soft-stop triplet (`engine.endMove` + `kernel.neutral` +
`deliverStopNow`) is written in `stopAll`, `endMove`, the watchdog and
`updateMove`. `pendingGoToDeadlineMs_` is per-call state stored on the
singleton to dodge PXT's 4-argument shim limit.

## Remedy

- One descriptor table `{name, ordinal, get, set, unit}` in `shims.cpp`
  that `kFields` and both switches read; generate `ConfigField` from it
  (a script and a drift test are acceptable where PXT cannot import).
- `Rig::softStop()`; four call sites become one.
- The go-to timeout becomes a config field like the other knobs, deleting
  the two-shim handoff.

## Acceptance

- Host test: every wire name round-trips SET/GET; every ordinal has one
  definition.
- `grep -c 'deliverStopNow' src/shims.cpp` is 1.
