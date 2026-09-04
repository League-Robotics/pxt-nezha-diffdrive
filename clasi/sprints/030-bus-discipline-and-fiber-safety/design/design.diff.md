---
source_file: design.md
source_hash: ee1692c3861791b302a8133cb32f9c9568fe3272a56fef0c718ab81b90dec516
---
# Diff: design.md

Comparison of the sprint overlay copy of `design.md` against its pristine (seed-commit) canonical version.

```diff
--- design.md (pristine)
+++ design.md (current)
@@ -143,7 +143,7 @@
 parse `TLM:` has not yet been retrofit onto the new frame (sprint
 005).
 
-### Execution model (tick model, sprint 002; single executor, sprint 028)
+### Execution model (tick model, sprint 002; single executor, sprint 028; bus and fiber discipline, sprint 030)
 
 The kernel's own background fiber is deliberately unwired. Every
 control cycle runs on whichever fiber calls `tickDrive()`, which
@@ -157,11 +157,7 @@
 MessageBus-forked fiber as it did through sprint 027. This closes the
 one place in the package where two fibers could do float work
 concurrently — the FPU yield-hazard the VFP guard (sprint 026) makes
-safe rather than eliminates — and makes the I2C bus-discipline
-invariant (below) structural: exactly one fiber ever ticks the kernel
-for engine-facing motion, so nothing can land OTOS traffic inside an
-encoder settle window by forgetting a convention three call sites used
-to have to remember independently. A `motionOwner_` field on the
+safe rather than eliminates. A `motionOwner_` field on the
 protocol fiber arbitrates a wire request arriving while a RUN job holds
 the drivetrain (refused, not silently overwritten); `RUN:abort`/
 `RUN:clearestop` bypass the queue and act immediately regardless.
@@ -173,13 +169,33 @@
 (`dispatchJob()`, `_registerRunDispatch()`, the component diagram) and
 sprint 028's own record for the design rationale.
 
+**Correction (sprint 030):** sprint 028's record above claimed this
+collapse made the I2C bus-discipline invariant "structural." That was
+true only for the kernel tick itself (`tickDrive()`/`kernel.step()`) —
+it was never true for the OTOS sensor, which has its own family of
+entry points (`otosBegin/Read/Zero/Calibrate/SetOffset`, `seedPose`)
+that issued I2C with no relationship to `tickDrive()`'s serialization
+at all, plus a background telemetry sampler and a block-fiber "start
+drive" loop that read the sensor with no gate whatsoever. **Sprint
+030** closes that gap: `tickDrive()`'s own `stepBusy` flag is promoted
+to a small bus-ownership guard (`BusGuard`, `core/bus_guard.h`) that
+every OTOS entry point acquires before touching the bus, alongside
+`tickDrive()` itself — see `src/DESIGN.md` §7. The same sprint also
+closes the fiber-identity gap in the tick-driven service hook (a
+button-handler fiber calling `tickDrive()` during a `RUN` job used to
+run the wire dispatcher a second time concurrently) and gives the block
+program's own fiber an explicit place in `motionOwner_` (`kBlock`) —
+see `src/DESIGN.md` §8.
+
 ### Sensor doctrine
 
 The OTOS world sensor is consulted at **move boundaries only** — a
 move runs entirely on encoder odometry and is never steered in flight.
 The overhead camera is a diagnostic, never a control input. All OTOS
-I2C traffic must run on the same fiber that ticks the kernel (shared
-bus with the Nezha encoder; see `src/DESIGN.md`).
+I2C traffic shares a bus with the Nezha encoder and must never land
+inside its select→read settle window; as of **sprint 030** this is
+enforced by a bus-ownership guard every OTOS entry point acquires, not
+only documented as a convention (see `src/DESIGN.md` §7).
 
 ### Host-vs-target language standard
 
```
