---
source_file: src-root-DESIGN.md
source_hash: 04c746b8702390121601ff95fd206a1ae71961f9a46c22760243b9678b27d2b5
---
# Diff: src-root-DESIGN.md

Replaces the "Known inert surfaces" note on `WireAdapter::lastDone()`/
`lastDoneReason()` with a description of the real completion channel
sprint 005 builds (one new `shims.cpp` bridge read plus the existing
diagnostic-flags path, no new `MotionEngine` reference), including the
two ordering hazards found and fixed during ticket 004's own
implementation (lease-verb dispatch racing its own supersede
resolution; `onEstop()`'s forced-unconditional commit), and marks the
two now-resolved "Open questions" bullets (the telemetry-gap retrofit
and the inert completion channel) resolved, following this doc's own
established `~~struck~~` convention for closed items.

```diff
--- src-root-DESIGN.md (pristine)
+++ src-root-DESIGN.md (current)
@@ -410,13 +410,28 @@
 live `MotionEngine` reference on `WireAdapter`; a stateful return value
 on all six bridge functions instead of the one needed).
 
+Two ordering hazards were found and fixed while implementing this:
+(1) a lease-style verb's own dispatch (`setWheelsTimed()`/
+`engineWheelsX()`/`engineMoveV()`, all routing through
+`MotionEngine::wheelsV()`/`wheelsX()`, whose first act is
+`cancelMove()`) must resolve a still-pending PREVIOUS motion as
+superseded *before* that dispatch runs, or the cancellation reads as
+the old motion having reached its own stop condition; (2) `onEstop()`
+commits `kEstop` unconditionally, never through the "trust the natural
+resolution first" path every other force-resolve call site uses,
+because `estopAll()`'s own `engine.endMove()` already clears
+`engineMoveActive()` synchronously while `diagValue(kDiagEstopped)` is
+still stale (an `Output` field that only updates on the kernel's next
+`step()`) — a naive natural-first commit would misread that
+combination as `kStop`.
+
 **Dependencies.** `wire_handler.h`; `shims.cpp` free functions by
 forward declaration only (`stopAll`, `estopAll`, `setWheelsTimed`,
 `setKernelValue`, `getConfigValue`, `diagValue`, `engineWheelsX`,
 `engineMoveX`, `engineDefaultCruiseMmS`, `engineMoveV`, `engineGoToR`,
-`engineGoToW`, `engineMoveActive` (sprint 005), and — sprint 004 ticket
-004 — `poseX`, `poseY`, `poseHeading`, `otosGet`, `wheelSpeed`). Holds
-no kernel/engine/Rig reference of its own.
+`engineGoToW`, `engineMoveActive` — sprint 005 ticket 004 — and —
+sprint 004 ticket 004 — `poseX`, `poseY`, `poseHeading`, `otosGet`,
+`wheelSpeed`). Holds no kernel/engine/Rig reference of its own.
 
 ## 6. Transports — `serial_transport.*`, `radio_transport.*`
 
```
