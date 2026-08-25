---
source_file: design.md
source_hash: 78c98189a5007580bfb97875725790f1482a1b9129db7e8d56d727968e461313
---

# Diff: design.md

One-line units-ladder table cell updated: `main.ts` (student-facing
Blocks layer) no longer exists as a single file after sprint 012 —
the row now names the five new modules that carry the Blocks API
(`motion.ts`/`pose.ts`/`stop.ts`/`world.ts`/`run.ts`) and points to
`src/DESIGN.md` §9/§15 for the full module map. No unit or convention
changes; this is a file-location correction only.

```diff
--- a/docs/design/design.md
+++ b/docs/design/design.md
@@ -56,7 +56,7 @@
 
 | Layer | Units |
 |---|---|
-| Blocks (`main.ts`, student-facing) | cm, cm/s, degrees, degrees/s |
+| Blocks (`src/motion.ts`/`pose.ts`/`stop.ts`/`world.ts`/`run.ts`, student-facing — sprint 012 split these out of a single `main.ts`; see `src/DESIGN.md` §9/§15) | cm, cm/s, degrees, degrees/s |
 | TS→C++ shim boundary | **integers only**: mm, mm/s, centidegrees, centidegrees/s |
 | Kernel config across the shim boundary | value × 1000 as an integer (the ×1000 fixed-point convention; `setKernelValue`/`getConfigValue` in `shims.cpp`) |
 | MotionEngine | mm, mm/s, radians, ms |
```
