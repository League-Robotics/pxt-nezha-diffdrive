---
source_file: core-DESIGN.md
source_hash: 5e1718853f0149954e6062a22ff6f14bbb67f5d59c4f2ecd400dadd975f3009f
---
# Diff: core-DESIGN.md

Comparison of the sprint overlay copy of `core-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- core-DESIGN.md (pristine)
+++ core-DESIGN.md (current)
@@ -9,6 +9,20 @@
 arbitration). Per the layer map, everything here compiles with libc
 only — no I2C, no CODAL, no MakeCode, no geometry.
 
+**Sprint 029** made four small, independently-justifiable patches to
+`diffdrive.cpp` (K1-K4: integrate the twist-hold reference from the
+post-floor half-differential; freeze the position reference on a stale
+encoder tick; anti-windup clamp the position reference; a
+`rearmReferences()` deferred request) plus one fleet-bake config change
+(K5: `vMin = 0`, since the speed floor moves up to the motion engine's
+new `MotionLimits`) — see
+[`docs/design/motion-profile-unification.md`](../../docs/design/motion-profile-unification.md)
+§4.5. Whether this repo keeps a byte-identical vendored copy of
+`radio-robot-elite/src/firm/diffdrive/` (paired-PR for every kernel
+change) or owns a local fork (a behavioral fidelity test instead) is an
+open stakeholder decision this sprint surfaces but does not resolve —
+see `clasi/issues/code-review/decide-the-kernel-fork.md`.
+
 Detail (the kernel's tick model, encoder-servo loop, and API) lives in
 [`src/DESIGN.md`](../DESIGN.md) §2; the two helper headers' one-line
 contracts are in §1's layer map table, and `encoder_glitch_armor.h`'s
```
