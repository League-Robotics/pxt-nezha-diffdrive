---
status: pending
---

# GO_TO_W has no encoder-odometry fallback, so it is unimplemented on any robot without an OTOS

`motion-api.md` §3.6 specifies `go_to_w`'s pose source as **pluggable — OTOS
when fitted, encoder odometry otherwise**, with epoch-guarded rebaseline and
unwrapped heading.

Sprint 003 built the pluggable half properly: `diffDrive::PoseSource` is a
3-method port, `OtosPort` implements it, and `FakePoseSource` makes `goToW`
host-testable (11 tests). But only the OTOS side was wired. There is no
encoder-odometry implementation of `PoseSource` anywhere.

Ticket 012 handled the consequence honestly rather than papering over it:
`onGoToW` answers `Wire::Result::kUnimplemented` when no pose source is
connected — "recognized, not wired on this build", which is exactly the right
code. It does not silently drive to a garbage pose.

## Why this matters beyond tidiness

**"No OTOS fitted" is a real fleet state, not a theoretical one.** The OTOS is
on vevov. The rest of the fleet — tovez, gopiv, zeguz — does not have one. So
`GO_TO_W`, one of the six headline motion verbs, is currently a no-op on most
robots the extension will run on, and students would meet it as a verb that
exists in the block list and does nothing.

The odometry itself already exists — `odomUpdate()` in `shims.cpp` maintains a
dead-reckoned pose from encoder counts, and the block API's `poseX`/`poseY`/
`heading` expose it. What is missing is an adapter presenting it as a
`PoseSource`, plus the epoch-guarded rebaseline and heading unwrapping §3.6
calls for.

## What to do

1. Implement an `EncoderPoseSource : diffDrive::PoseSource` over the existing
   odometry.
2. Decide the selection rule — OTOS when present, encoder otherwise — and put
   it in ONE place, not at each call site.
3. Honour §3.6's two named details: epoch-guarded rebaseline, and heading kept
   unwrapped. The unwrapping matters concretely here: the OTOS heading register
   spans ±pi across int16, so exactly pi lands one LSB outside range and clamps
   (measured: 180° reads back 179.89°).

Worth stating plainly in whatever ships: encoder odometry drifts and OTOS does
not, so a `GO_TO_W` served by encoders is a materially weaker promise than one
served by the OTOS. That difference should be visible to a caller, not hidden
behind an identical-looking verb.
