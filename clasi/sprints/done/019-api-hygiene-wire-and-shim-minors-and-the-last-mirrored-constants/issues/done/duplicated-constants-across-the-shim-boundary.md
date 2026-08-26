---
status: done
sprint: 019
tickets:
- 019-005
- 019-006
---

# Repeated constants: pi x13, the centidegree conversion x5, two default speeds

Priority: **Low** -- no defect today, but every un-guarded mirrored constant in
this repo has eventually drifted.

## `3.14159265f` and the cdeg->rad conversion

`3.14159265f` appears **8 times in `shims.cpp` alone**, plus `otos_port.h:107`,
`motion_engine.cpp:17` (`kPi`), `heading_wrap.h:52` (its own longer literal),
and `Math.PI` on the TS side.

The **cdeg -> rad** conversion is written out verbatim five times in
`shims.cpp` -- `:272` (`driveTwist`), `:300` (`driveTwistTimed`), `:385`
(`startMove`), `:1155` (`otosSetOffset`), `:1166` (`seedPose`):

```cpp
static_cast<float>(yawRate) * 0.01f * 3.14159265f / 180.0f
```

...and inverted twice more (`:840` `poseHeading()`, `:1093` `otosGet()`'s local
`kRadToCdeg`). `otosGet()` is the only site that names the conversion.

`shims.cpp`'s own header states the boundary convention -- *"integers only. mm,
mm/s, centidegrees, centidegrees/s"* -- which is exactly where this belongs:

```cpp
constexpr float kCdegToRad = 0.01f * 3.14159265f / 180.0f;
constexpr float kRadToCdeg = 1.0f / kCdegToRad;
```

Seven sites, one definition, and the boundary convention gets a name instead of
a paragraph.

## Two default speeds in two units

`blocks/motion.ts:55` `defaultSpeed = 15` (cm/s) and `shims.cpp:143`
`defaultCruiseMmS_ = 150.0f` (mm/s), with the latter's comment asserting they
match -- and citing `main.ts`, retired two sprints ago.

Nothing enforces the match, and they are independently settable
(`default_cruise` over the wire, `setDefaultSpeed` from a block), so they
diverge the moment either is used. That may be correct by design -- one is the
wire's sentinel resolution, the other the block layer's move speed -- in which
case the comment's claim that they *match* is a snapshot, not a contract, and
should say so.

## Context

Every mirrored constant here that has a drift test (`kVersion`, the four
240-byte line caps, `RUN_EVENT_SOURCE`, the `kDiag*` ordinals) has held across
five sprints. Every one without has drifted or is structurally able to -- see
`travel-calib-not-propagated-to-docs-and-tools.md` and the `0x5F` case in
`wire-and-shim-minor-defects.md`. The rule that falls out: **every mirrored
constant gets a drift test, or gets merged.** These two are merge candidates.
