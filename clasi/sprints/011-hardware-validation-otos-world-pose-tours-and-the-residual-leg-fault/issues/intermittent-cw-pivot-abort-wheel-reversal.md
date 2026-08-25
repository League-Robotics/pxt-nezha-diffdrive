---
status: in-progress
sprint: '011'
tickets:
- 011-002
- 011-003
- 011-004
- 011-006
---

# Residual intermittent leg fault in square tours (successor issue)

> **2026-08-20 rewrite.** This issue originally blamed a CW-pivot
> wheel-reversal failure; every theory it contained has since been
> tested on instrumented hardware. RETIRED THEORIES (with the evidence
> that killed each): battery sag (stakeholder-confirmed fine),
> tick-loop starvation (GAP telemetry: worst inter-tick gap 48 ms in
> both passing and failing runs), encoder 0x46 latch (wpk streak
> instrumentation: max driven identical-read streak 2 ticks across all
> campaigns), direction mirroring (fixed by the port swap, camera-
> verified), track/scrub calibration (measured and applied).
>
> ROOT CAUSE FOUND AND FIXED for the dominant failure (commit 3e919e5):
> move completion never delivered the kernel's neutral to the motors --
> the completing tick's caller exits its while(tickDrive()) loop, the
> staged zero needs one more step, and the wheels coasted at full duty
> until the starvation watchdog's ~100-150 ms port stop. Intermittency
> came from the protocol fiber's co-ticking (also removed, ownership
> flag) sometimes delivering the missing step by luck. The
> through-zero reversal-dwell hole (wedgelab (20,50] ms latch window)
> was also closed the same day.

## What remains

After the fixes: turn overshoot is gone (headings close within ~7 deg
consistently), tours complete ~70% with near-misses at the 60 mm
threshold. The residual: occasional distance-leg errors (a straight
overrunning or a tour truncating mid-leg, e.g. finals (-275,141) or
(471,671,273deg) in the 2026-08-20 warm campaign). Signature differs
from the fixed class: heading usually still closes. Instrumentation in
place for the hunt: GAP (tick gaps), wpk (encoder streaks), DIAG over
radio at 1 Hz, per-run radio/USB TLM traces.

Next probes: per-leg believed-vs-target logging at move end (what did
serviceMove think it hit?); check the moveDeadline path (duration
math) for legs that truncate; first-move-after-boot special-casing.
