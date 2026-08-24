---
status: in-progress
sprint: '006'
tickets:
- 006-005
- 006-006
---

# Brick MCU reset mid-session teleports odometry ~4 m (bench check + rebaseline)

Priority: **Medium** — code review 2026-08-23, R-07 (KERN-07; code path
CONFIRMED statically, hardware premise UNVERIFIABLE without bench).

If the Nezha brick's MCU resets mid-session (brownout, wiring blip), its
encoder counters restart from zero. The glitch armor's two-strike rule
accepts the discontinuity as truth on the second read; no production path
rebaselines the counters. Statically certain: a ~−50k-count jump maps to a
~4 m pose teleport and a 1–2 M counts/s speed spike. What needs hardware:
whether a brick reset actually zeroes the 0x46 counter registers.

**Decisive bench experiment** (from `verify-kernel.md`): power-cycle the
brick mid-drive while watching DIAG ordinals 10/11 and pose. Distinct from
the filed `unpowered-nezha-brick-wedges-program-at-boot` (boot-time wedge);
this is the mid-session variant. Follow this project's measurement doctrine:
prove the instrument (DIAG capture running) before interpreting the fault.

## What to do

1. Run the bench experiment; record numbers in the issue.
2. If confirmed: rebaseline on discontinuity (treat an impossible delta as
   "reset detected" — re-zero the baseline instead of integrating it), and
   surface a DIAG counter for it.

## The fix already shipped (ticket 005) — nothing left to design here

Item 2 above is **done**. Sprint 006 ticket 005
(`clasi/sprints/006-motion-correctness-goto-geometry-and-odometry-truth/tickets/done/005-encoder-glitch-armor-rebaseline-on-discontinuity-host-testable.md`)
shipped the host-testable half of this fix:

- `src/encoder_glitch_armor.h` (new, host-portable, no `pxt.h`) —
  `EncoderGlitchArmor::evaluate(raw)` owns the two-strike plausibility
  state and returns `Decision::{kAccept, kAcceptAsRebaseline,
  kRejectPending}`. `kMaxDeltaCounts = 5000` is unchanged numerically
  but is now a named constant with a recorded derivation (24 ms cycle,
  `fullDutyVelocity` = 10795 counts/s -> ~259 counts/cycle, ~518 over a
  worst-case two-cycle gap; 5000 sits ~10x above plausible motion and
  ~10x below the ~50,000-count discontinuity this issue targets).
- `src/nezha_port.cpp::collect()` (lines ~199-245) now calls
  `glitchArmor_.evaluate(raw)`. `kRejectPending` is unchanged from the
  pre-fix behavior (HOLD: position/velocity/sampleTime all stay put,
  `++glitchCount_`). The new third outcome, `kAcceptAsRebaseline`,
  re-anchors `encOffset_ = raw - static_cast<int32_t>(lastPosition_) *
  fwdSign_` (line 233) and increments `rebaselineCount_` — this maps
  the new raw value onto the position already held, so pose stays
  continuous across the event and that tick's velocity reads ~0
  instead of the multi-m/s spike the old two-strike accept produced.
- `src/shims.cpp::diagValue()` **ordinal 27** (confirmed in source,
  lines 801-810): `left.rebaselineCount_ + right.rebaselineCount_` —
  0 across a normal session, increments once per rebaseline event.
  Exposed to TS test scripts via the `//%`-annotated `probe(int)` shim
  (`shims.cpp:1044`, `probe(what) { return diagValue(what); }`).

**Nobody running this bench experiment needs to design or implement
anything.** The fix is in place; this checklist is only about
observing whether it behaves as designed on real hardware.

## Bench Checklist (stakeholder handoff)

**This section does not run the experiment.** Everything below is for
whoever executes the bench run (the stakeholder, or a future
hardware-validation sprint — sprint 011 is already scoped to include
this same experiment, see its `sprint.md`). Nothing in this section was
performed while writing it; no pass/fail is recorded here.

### 0. Prove the instrument is watching, first

Per this project's own measurement doctrine (an instrument that fails
by going quiet is indistinguishable from a robot correctly doing
nothing — see `project-knowledge`/session memory on "measurement
before diagnosis"): before power-cycling anything, confirm the
capture side is actually alive.

- If reading pose/position from the wire telemetry stream: send `TLM
  FULL` (or confirm it is already the active subscription — `STATUS`
  reports the current mode in its `tlm=` field) and confirm `t` frames
  are arriving with `seq` visibly incrementing tick over tick. A silent
  serial/radio line reads identically to "robot doing nothing" —
  do not proceed until frames are confirmed flowing.
- If reading `probe(27)`/`probe(23)`/`probe(24)` (see "How to read the
  counters" below): confirm the on-device test script is actually
  printing/logging a stable value (even if 0) for several ticks before
  the power-cycle, not silently stalled.

### 1. The hardware step

Power-cycle the Nezha brick **mid-drive**, with the microbit's tick
loop still alive — i.e. the robot is actively commanded to drive (a
`driveTick()`/`updateMove()` loop running), and only the brick's own
power is interrupted and restored (momentarily disconnect/reconnect
the brick's power lead), not the microbit's. This is the mid-session
variant named in `verify-kernel.md`'s KERN-07 write-up — distinct from
`clasi/issues/unpowered-nezha-brick-wedges-program-at-boot.md`'s
boot-time wedge, which this checklist does not test.

The fleet's test robot for this project is **vevov**. Coordinate
before flashing or driving it — boards are shared across parallel
sessions (check for other agents holding it first).

### 2. What to watch, and how to read it

Two signal groups, from two different accessors — neither is
currently wired to the other, so both must be read:

- **DIAG ordinals 10/11 (`positionLeft`/`positionRight`, the raw
  per-wheel accumulated counts) and pose (`x`/`y`/`h`).** Both ARE
  already on the wire today (v6's telemetry frame, `TLM FULL`): ordinal
  10/11 surface as the `posl`/`posr` columns, and pose as the `x`/`y`/`h`
  columns (sourced from `poseX()`/`poseY()`/`poseHeading()` in
  `wire_adapter.cpp`, the same values `odomUpdate()` would teleport per
  R-07's own arithmetic). Note: the desktop-side `tools/` bench tooling
  has not yet been retrofit to parse the v6 `t` frame automatically
  (sprint 005, still in `roadmap` status as of this ticket) — reading
  these live today likely means watching the raw wire text over serial
  rather than a polished chart, unless that retrofit has landed by the
  time this bench run happens.
- **`probe(27)` (rebaselineCount_, ticket 005's new counter) and
  `probe(23)`/`probe(24)` (glitchCount_, the pre-existing per-wheel
  counter).** These are NOT wire-telemetry columns — they are only
  reachable via the `//%`-annotated `probe(int)` TS shim
  (`shims.cpp:1044`), which needs a small on-device test script
  (the `test.ts`/`testrig.ts` pattern already used elsewhere in this
  project) that samples `probe(27)`, `probe(23)`, and `probe(24)` once
  per tick into arrays and dumps them over serial afterward — the same
  "sample into arrays, dump afterwards" pattern `shims.cpp`'s own
  comment above `probe()` documents, because a live request/reply
  round-trip mid-move is documented dangerous on this rig (a 197.5 mm
  leg collapsed to 0.3 mm the one time it was tried).

### 3. The specific numbers to record

1. **Baseline**, sampled for a few ticks *before* the power-cycle:
   `posl`, `posr`, `x`, `y`, `h`, `probe(27)`, `probe(23)`,
   `probe(24)`.
2. **The power-cycle event itself** — timestamp or tick number.
3. **After reconnect**, sampled per-tick for several seconds:
   the same eight values, with particular attention to:
   - The tick (if any) where `probe(23)` or `probe(24)` increments —
     this is the first implausible reading (`kRejectPending`), held.
   - The tick (if any) where `probe(27)` increments — this is the
     second, self-consistent reading (`kAcceptAsRebaseline`), where
     `encOffset_` re-anchors. A real brick reset should show the
     glitch counter tick immediately *before* the rebaseline counter
     ticks (the two-strike sequence), not the rebaseline counter alone.
   - `posl`/`posr`'s raw values across the same window (do they show
     the ~−50,000-count-class jump the issue's own arithmetic
     predicts, consistent with the brick's 0x46 counter actually
     restarting near zero?).
   - `x`/`y`/`h` across the exact same window (does pose hold
     continuous, or jump?).
4. **Position delta**: `posl`/`posr` and `x`/`y`/`h`, before vs. after,
   computed directly from the recorded numbers above — not estimated.

### 4. What "confirmed" vs. "ruled out" looks like

- **Confirmed**: `probe(27)` increments across the power-cycle event,
  AND `x`/`y`/`h` show no discontinuity at that same tick (pose holds
  at its pre-reset value rather than jumping by anything near the ~4 m
  this issue's arithmetic predicts for an unmitigated jump). This means
  the brick's counter really did restart near zero, and the armor
  caught it as designed.
- **Ruled out**: no discontinuity signature appears at all in
  `posl`/`posr` across the power-cycle (the brick's counter did NOT
  reset near zero — e.g. it held its value in battery-backed state, or
  the bus simply wedged instead, which would show up as
  `connectedLeft`/`connectedRight` or `i2cFaultCount` moving instead).
- **Anything else — record it as its own finding, not a pass/fail.**
  In particular: `probe(27)` increments but pose teleports anyway
  (wiring is broken somewhere despite the code-review-confirmed
  reasoning); `probe(23)`/`probe(24)` climbs repeatedly without
  `probe(27)` ever following (the two-strike sequence never resolves
  to rebaseline — e.g. the counter keeps jumping to new, mutually
  *inconsistent* values, so `rejMag <= kMaxDeltaCounts` never holds);
  or the observed jump magnitude is nowhere near the ~50,000-count
  scale this issue's arithmetic assumes. Any of these means the
  mechanism did not behave as designed and is its own follow-up issue,
  not a silent confirmation.

### 5. The false-positive side — does it stay quiet during real fast motion?

Just as important as whether the armor fires on a real reset is
whether it does **not** fire during legitimate fast motion — a
too-tight `kMaxDeltaCounts` would show up here, not in the reset test.
Separately from the reset experiment, run an ordinary bench pass with
no brick power-cycle at all — full-duty driving, quick direction
reversals, the kind of motion this project's own bench scripts
(`tools/turn_sweep.py`, `tools/tour_run.py`, etc.) already exercise —
and sample `probe(27)`, `probe(23)`, `probe(24)` throughout. All three
should read **0** for the entire run. If any of them increments during
ordinary driving with no reset, that is a distinct finding (the 5000
count threshold is tighter than this robot's real achievable per-cycle
motion) and should be filed as its own follow-up, separate from this
issue's reset-detection result.

### No bench run has been performed, and no result is reported here

**This checklist is a handoff, not a report.** Nothing in this section
was executed as part of writing it, and no acceptance criterion in
this ticket (006) or claim in this issue depends on a hardware result.
The numbers above are placeholders describing what to record — filling
them in, and judging confirmed/ruled-out/other, is the bench operator's
job, not this ticket's.

**What remains unproven, stated plainly:** `nezha_port.cpp` and
`shims.cpp` both include `pxt.h` unconditionally and cannot be built
into any host test (`tests/host/DESIGN.md` S6 lists `nezha_port` under
"not covered, by design"). Ticket 005's actual wiring — the
`collect()` call sites, the `encOffset_ = raw -
static_cast<int32_t>(lastPosition_) * fwdSign_` re-anchor formula, and
the `rebaselineCount_`/`glitchCount_` increments — is verified by code
review only. `tests/host/test_encoder_glitch_armor.py` proves
`EncoderGlitchArmor`'s pure decision logic is correct in isolation; it
proves nothing about whether `collect()` calls it correctly, whether
the offset formula is wired to the right operands on a real device, or
whether the DIAG ordinal actually reaches the value the code review
traced. This bench run is that wiring's first real exercise, on any
hardware, ever.

## Design Note: the `encOffset_` re-anchor formula (for the record)

Worth preserving so a future reader does not "simplify" ticket 005's
fix back to something that looks equivalent but isn't. The sprint's
own design overlay (`sprint.md`'s SUC-005 main flow, step 3) describes
the fix only as "`collect()` re-anchors its position offset (same
technique the existing manual `rebaseline()` already uses)." Taken
literally, "the same technique" is `NezhaMotorPort::rebaseline()`'s own
form (`src/nezha_port.cpp:287-292`): `encOffset_ =
glitchArmor_.lastGoodRaw()`, which maps `pos` to **0** on the next
read (since `pos = (raw - encOffset_) * fwdSign`, setting `encOffset_
= raw` forces `pos = 0`).

Applied literally at the rebaseline site, `encOffset_ = raw` would
NOT produce continuity here: it would snap `pos` to 0 immediately
rather than holding it at `lastPosition_` — relocating the
discontinuity rather than eliminating it. In a long-running session,
where `lastPosition_` can itself be tens of thousands of counts from
the origin, that relocated jump can be just as large as the teleport
this ticket exists to fix.

The shipped code (`src/nezha_port.cpp:233`) instead solves for the
`encOffset_` that makes `pos == lastPosition_` for the *new* `raw`
value: `encOffset_ = raw - static_cast<int32_t>(lastPosition_) *
fwdSign_`. This is the correct generalization of `rebaseline()`'s
existing offset technique — from "map the next read to 0" to "map the
next read to whatever position was already held" — and it is what
actually satisfies the overlay's stated *intent* (position stays
continuous across the event), not what its literal wording alone
would produce.
