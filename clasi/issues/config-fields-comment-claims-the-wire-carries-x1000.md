---
status: pending
---

# `config_fields.h`'s comment claims the WIRE carries config values x1000. It does not.

`src/comms/config_fields.h`, on `ConfigFieldDescriptor::unit`:

```c
  const char* unit;    // of the UNSCALED value; the wire carries it
                       // x1000 (shims.cpp's own boundary convention)
```

**The wire does not carry it x1000.** The wire carries the real,
unscaled value in both directions. The x1000 lives entirely on the
SHIM boundary, between `wire_adapter.cpp` and `shims.cpp`, and it
cancels before it ever reaches the wire:

- `WireAdapter::onSet` (`src/comms/wire_adapter.cpp`) takes the float
  off the wire, computes `value * 1000.0f`, and passes the rounded int
  to `setKernelValue`, which immediately multiplies by `0.001f`
  (`src/shims.cpp`). Net: identity.
- `WireAdapter::onGet` reads `getConfigValue(ordinal)` — which returns
  `lround(v * 1000.0)` — and multiplies by `0.001f` before it goes out.
  Net: identity.

So `SET rotational_slip 0.886` stores 0.886, and `GET rotational_slip`
answers 0.886. The comment describes the wrong boundary.

## What it cost

MEASURED tovez 2026-09-15/16 by the nezha-robot-template session (its
capture log; numbers reported to this repo, not re-run here). Reading
the comment as written, that session sent the value it believed the wire
wanted:

- `SET rotational_slip 886` stored **886.0**, exactly as the code
  should: `886 * 1000 * 0.001 = 886`.
- That makes the effective track width `b = 114.2 / 886 = 0.13 mm`.
- `MotionEngine::beginSegment` computes a rotation's wheel-travel target
  as proportional to the effective track width
  (`yawTarget = rotation * 0.5f * effectiveTrackWidth() * cpm`,
  `src/motion/motion_engine.cpp`), so a b of 0.13 mm makes the target
  ~0. Every commanded turn completed on arrival in 5-6 control cycles
  having physically rotated about 0.3 degrees.
- The reported odometry heading — 104.58, -209.16, 557.75 degrees for
  commanded 90/-90/360 — was `(dRight - dLeft) / b` computed with that
  same absurd b. Arithmetically correct, given the geometry it was
  handed.

That session produced and then retracted three theories (a stuck STATUS
flag, `resetPose()` not zeroing, `move()` misreporting heading) and one
headline calibration result, all traceable to this one comment. The
robot looked defective; it was obeying a number the comment told a
caller to send.

## Why this is a defect, not a nit

This project's whole method rests on comments being trustworthy
(`.claude/rules/measurement-citations.md`). A comment that names the
wrong boundary is worse than no comment: it is confidently wrong, it
sits on the one struct every wire config field is declared through, and
the failure it produces looks like a firmware fault rather than a
caller error.

Note the trap is asymmetric and quiet. A wrong value in this field does
not error, does not clamp, and does not warn — `onSet`'s only guard is
the overflow ceiling, which 886 passes easily. The robot simply stops
being able to turn.

## Fix

1. Correct the comment: the wire carries the value UNSCALED; the x1000
   convention applies only across the `shims.cpp` boundary.
2. Check every other place that describes this convention, including
   `setKernelValue`'s and `getConfigValue`'s own doc comments and
   whatever host-facing docs describe `SET`/`GET`, so the corrected
   statement is consistent.
3. Consider a plausibility guard on the fields where a wrong scale is
   catastrophic rather than merely wrong. `rotational_slip` at 886 is
   not a value any real drivetrain has. A refusal, or even a clamp,
   would have turned this evening into one error line.
4. **Pin the round trip with a host test**, so a corrected comment
   cannot silently drift back out of agreement with the code: `SET
   <field> 0.886` followed by `GET <field>` must answer 0.886, for a
   sub-unity field. A test is what makes the statement enforceable;
   the comment is only a claim. `tests/host/test_wire_motion_verbs.py`
   is the style precedent, and
   `tests/host/test_config_surface_single_source.py` already pins the
   ordinal binding between the two halves of this same table, so the
   scaling convention is the obvious gap next to it.

Note `setKernelValue`'s own `// [x1000 scaled]` signature comment and
`getConfigValue`'s `// -> [x1000 scaled]` are both CORRECT: those
functions genuinely take and return scaled ints. Only the
`config_fields.h` comment, which attributes that convention to the
wire, is wrong. Fixing it means making the distinction explicit rather
than deleting a line — the x1000 is real, it just lives one layer in
from where the comment puts it.

Found 2026-09-16 by team-lead, verified by source reading of
`wire_adapter.cpp`'s `onSet`/`onGet` and `shims.cpp`'s
`setKernelValue`/`getConfigValue`. The hardware consequences above are
the template session's measurements, reported to this repo; no artifact
has been handed over yet.
