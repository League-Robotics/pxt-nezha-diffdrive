---
id: '004'
title: OTOS heading-wrap on seed and PoseSource contract cleanup
status: open
use-cases: [SUC-004]
depends-on: []
github-issue: ''
issue: otos-seed-heading-clamp.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# OTOS heading-wrap on seed and PoseSource contract cleanup

## Description

`OtosPort::writePoseMm()` (`src/otos_port.cpp:57-69`) clamps all three
channels (x, y, heading) to ±32767 LSB before quantizing. Clamping is
correct for x/y (±10 m full-scale range) but wrong for heading, which
is a wrap-mandatory quantity: ±32767 LSB ≡ ±179.89°. Seeding with a
heading outside ±180° — a 0–360° camera-yaw convention value, or the
project's own deliberately-unwrapped odometry heading (`r.heading`)
echoed back through `poseHeading()` — silently clamps: 350° lands at
+179.89° instead of −10°, up to ~170° of error (code review R-05,
KERN-05, CONFIRMED, numbers re-derived in `verify-kernel.md`). This
poisons exactly the drift measurement `seedPose()`'s own contract
comment says the two pose sources' later divergence is meant to
measure — they no longer start agreed.

Related Minor (KERN-08): `OtosPort::heading()` reports a value wrapped
to ±π by the chip's own int16 register, but `PoseSource::heading()`'s
contract comment (`motion_engine.h:139`) claims "(unwrapped)"
universally. This sprint adds a second `PoseSource` implementation
(`EncoderPoseSource`, ticket 007) that is deliberately *unwrapped*
(matching `Rig`'s existing odometry contract, and matching
motion-api.md §3.6's explicit requirement that the encoder-based
source keep heading unwrapped) — so the two implementations
legitimately disagree on wrap convention, and the interface's contract
comment must say so rather than asserting one universal answer. This
is safe because `MotionEngine::goToR()`/`goToW()` consume `heading()`
only through `cos()`/`sin()` (wrap-invariant) — no consumer differences
two `heading()` reads.

**Fix, at the module level:** wrap the heading channel into (−π, π]
before it reaches `writePoseMm()`'s quantizer (x/y keep their existing
clamp — this is a heading-only change). Update
`PoseSource::heading()`'s doc comment in `motion_engine.h` to state the
wrap convention is implementation-defined and must only be consumed
via `cos()`/`sin()`, not a single universal "(unwrapped)" claim.

**Host-testability constraint (decided at planning time, not deferred):**
`otos_port.h` includes `pxt.h` unconditionally, so `OtosPort` cannot be
compiled into any host test at all — there is no existing seam that
exercises its I2C-bound methods host-side, and none of this ticket's
work can change that. The wrap math therefore lives in a new,
dedicated host-portable header, `src/heading_wrap.h` (one pure
function, e.g. `wrapRadians(float) -> float`, no dependencies of any
kind — smaller in scope than ticket 005's `encoder_glitch_armor.h`).
`OtosPort::setPose()` calls it; a host test exercises it directly,
proving the same LSB round-trip (350° → −10°) the real register write
would produce, without I2C anywhere in the link. This is the only way
this ticket's Acceptance Criteria (below) are host-testable at all —
do not attempt to test through `OtosPort::setPose()` itself.

**C++11 gate coverage:** `heading_wrap.h` has no `pxt.h` dependency and
should be added to `tests/host/test_cxx11_syntax_gate.py`'s coverage
via a small dedicated syntax-check translation unit (it has no natural
`.cpp` of its own). `otos_port.cpp` itself (the actual call site) is
**not** covered by that gate and cannot be made so — it includes
`pxt.h` unconditionally. A green host suite proves `heading_wrap.h`'s
math is correct and syntax-valid at C++11; it does **not** prove
`otos_port.cpp`'s call site compiles for either real embedded target.

## Acceptance Criteria

- [ ] A host test drives `heading_wrap.h`'s wrap function directly at
      350°/−350°/720° (converted to radians) and asserts the result
      matches the correctly wrapped equivalent (e.g. 350° → −10°),
      including a round-trip through the same LSB quantization
      `writePoseMm()` uses, so the test proves what the real register
      write would produce.
- [ ] `OtosPort::setPose()` calls `heading_wrap.h`'s function before
      handing heading to `writePoseMm()`; x/y are unaffected (still
      clamped, not wrapped) — a code-reading check, since `OtosPort`
      itself cannot be host-tested (see above).
- [ ] `PoseSource::heading()`'s doc comment in `motion_engine.h` no
      longer asserts a single universal "(unwrapped)" contract; it
      states the wrap convention is implementation-defined and must be
      consumed only via cos/sin.
- [ ] `OtosPort`'s own class-level or method-level comment documents
      that it reports heading wrapped to (−π, π] (resolving KERN-08 by
      making the contract honest, not by changing behavior).
- [ ] `heading_wrap.h` is added to `tests/host/test_cxx11_syntax_gate.py`'s
      covered-files list via a small dedicated syntax-check translation
      unit.

## Implementation Plan

**Approach:**
1. Create `src/heading_wrap.h`: one pure, header-only function
   (e.g. `inline float wrapRadians(float rad)`) that normalizes any
   float radian value into (−π, π], no includes beyond `<cmath>`.
2. In `OtosPort::setPose()`, wrap `heading` through it before calling
   `writePoseMm(kRegPositionXl, xF, yF, heading)`. Leave
   `writePoseMm()`'s x/y clamp untouched — this is a heading-only
   change.
3. Update `motion_engine.h`'s `PoseSource::heading()` doc comment and
   `otos_port.h`'s `OtosPort::heading()` comment.
4. Add `heading_wrap.h` to the C++11 syntax gate's file list.

**Files to modify:**
- `src/heading_wrap.h` (new) — the wrap function.
- `src/otos_port.cpp` — `setPose()` calls it.
- `src/motion_engine.h` — `PoseSource::heading()` doc comment.
- `src/otos_port.h` — comment on `OtosPort::heading()`'s wrap
  convention.
- `tests/host/test_cxx11_syntax_gate.py` — add `heading_wrap.h`.
- `tests/host/` — new test(s) for `heading_wrap.h` directly.

**Testing plan:** host-only, against `heading_wrap.h` directly (see
Acceptance Criteria — do not attempt to test through `OtosPort`, which
cannot be host-compiled).

**Documentation updates:** `motion_engine.h`, `otos_port.h` doc
comments (above). No canonical design-doc overlay edit needed beyond
`design/DESIGN.md`'s existing overlay content.
