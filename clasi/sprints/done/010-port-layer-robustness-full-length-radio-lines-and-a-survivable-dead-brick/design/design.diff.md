---
source_file: design.md
source_hash: 4b17e87cf0fcdec07b5349365418abdc06facbf71e01235be312ae3b9bbe0aca
---

# Diff: design.md

Updates the header/status line to include sprint 010, and replaces the
"Protocol versioning" section's paragraph describing radio's RX-capacity
gap as an open issue with a description of sprint 010's resolution
(RX/TX buffers raised to match the wire grammar's 240-byte ceiling, no
reassembly protocol needed, reject-not-truncate on over-length input).

```diff
--- design.md (seed, commit 9e5f0c5)
+++ design.md (sprint 010 overlay)
@@ -7,7 +7,7 @@
 ---
 # DiffDrive — System Design
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** in-flux (as-built through sprint 008, closed and merged — sprints 004, 006, 007 and 008 all closed and merged: radio speaks full v6 with a `thdr`/`t` telemetry frame; motion correctness (goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W); student API (stall-latch clear and readback, the `driveTick()` contract, the wire `cruise == 0` sentinel, simulator parity, a `rotationalSlip` setter); and wire hardening with a standing per-sprint build-checkpoint convention. Sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 010, closed and merged — sprints 004, 006, 007, 008 and 010 all closed and merged: radio speaks full v6 with a `thdr`/`t` telemetry frame and now carries the wire grammar's full 240-byte line capacity on both RX and TX; motion correctness (goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W); student API (stall-latch clear and readback, the `driveTick()` contract, the wire `cruise == 0` sentinel, simulator parity, a `rotationalSlip` setter); wire hardening with a standing per-sprint build-checkpoint convention; and port-layer robustness (radio line capacity reconciled with the wire's own ceiling, STATUS gains a `cyc` field so "never ticked" is distinguishable from "brick unreachable," and a GET-path float-formatting overflow fixed across every configured field). Sprints 005 and 009 roadmapped, not yet detail-planned)
 
 ## What the system is
 
@@ -116,10 +116,17 @@
 receive side now speaks the full v6 grammar too, through its own
 `Wire::WireHandler` over the same shared adapter serial uses, with the
 old `RUN:` prefix preserved as a fallback on both transports rather
-than a radio-only ceiling (see `src/DESIGN.md` §8). Radio's remaining
-limit is one of *capacity*, not grammar: a single 64-byte RX fragment
-slot with no multi-fragment reassembly
-(`clasi/issues/radio-rx-capacity-fragmentation.md`). v6 now **does**
+than a radio-only ceiling (see `src/DESIGN.md` §8). **Sprint 010**
+closed radio's remaining capacity gap: `RadioTransport`'s RX and TX
+buffers now match the wire grammar's own 240-byte line ceiling exactly
+(`Wire::WireHandler::kMaxLineBytes`, `SerialTransport::kMaxLineBytes`),
+not the previous, arbitrary 64-byte RX / 200-byte TX limits — no
+multi-fragment reassembly protocol was needed, because this project's
+own fleet radio configuration (`microbit_radio_max_packet_size: 250`)
+already carries a full 240-byte line in one physical fragment on both
+transports. A single-fragment line whose declared length exceeds 240
+bytes is now dropped outright rather than truncated to a parseable
+(and executable) prefix — see `src/DESIGN.md` §6. v6 now **does**
 carry a data-bearing telemetry frame — `thdr`/`t`, built in sprint 004
 — replacing the old cleartext `TLM:` stream the same way the rest of
 v5 was replaced, though the bench tooling in `tools/` that used to
```
