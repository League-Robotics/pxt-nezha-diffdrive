---
source_file: DESIGN.md
source_hash: bb5eb8504411ea403913c41b4aedab1be52686ee26c1ea4a3cf93b84aeb7fdac
---

# Diff: DESIGN.md

Updates the header/status line to include sprint 010; adds sprint 010's
changes to the RadioTransport paragraph (§6, RX/TX capacity raised to
240, reject-not-truncate) and the STATUS paragraph (§5, new `cyc=`
field); resolves the radio-RX-capacity Open Question and adds two new
ones (the GET-formatting fix, the dead-brick observability fix) in §10;
and appends a new §15 "Sprint 010 — architecture diagram and change
summary" section following this document's own established
per-sprint-update convention (§12/§13/§14).

```diff
--- DESIGN.md (seed, commit 9e5f0c5)
+++ DESIGN.md (sprint 010 overlay)
@@ -1,6 +1,6 @@
 # src — the DiffDrive extension
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 010, closed and merged — sprint 008: wire hardening and tests that can fail (timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap); sprint 010: port-layer robustness (`RadioTransport`'s RX/TX capacity raised to match the wire's 240-byte ceiling with no reassembly protocol needed, an over-length fragment now rejected rather than truncated, `STATUS` gains a `cyc` field so "never ticked" is distinguishable from "brick unreachable," the Nezha I2C bus-hang question investigated, and a `GET`-path float-formatting overflow fixed across every configured field); sprints 005 and 009 roadmapped, not yet detail-planned)
 
 `src/` is flat — no subdirectories — so this one document carries the
 logical subsystem breakdown as sections. Global conventions (units
@@ -333,7 +333,17 @@
 wire-reachable OTOS check — R-22/WIRE-06) plus a decimal `i2cf=` fault
 count sourced from the same `diagValue(8)` call the telemetry `i2cf`
 column reads (see the Telemetry projection paragraph below), so the
-two can never disagree. `onRun()` is an honest `kUnknown` — the real
+two can never disagree. **Sprint 010** adds a decimal `cyc=` field the
+same way, sourced from the already-existing `diagValue(kDiagCycleCount)`
+call (ordinal 16) telemetry's own `cyc` column already reads — no new
+kernel-facing state. This closes a real observability gap a bench
+session surfaced: `active_`/`connected_`/`i2cFaultCount_` are only
+written inside `step()`/`collect()`, so a healthy kernel nothing has
+ever ticked and a kernel behind a genuinely unreachable brick report the
+*identical* `ready=0 connL=0 connR=0 i2cf=0` STATUS line. `cyc=0` now
+tells an operator "nothing has ticked yet — the rest of this line is not
+evidence of a fault," reading STATUS alone with no telemetry
+subscription needed. `onRun()` is an honest `kUnknown` — the real
 by-name test trigger is protocol.cpp's MessageBus RUN bridge, a CODAL
 mechanism this host-portable class must never touch.
 
@@ -439,7 +449,23 @@
 **only** called inside that handler because polling an empty queue
 kills the program within two polls (measured; CODAL EmptyPacket
 refcounting). Multi-fragment inbound reassembly is deliberately out of
-scope. Send-path scratch buffers are members, not stack locals — the
+scope — and, as of **sprint 010**, deliberately unneeded: this
+project's own `pxt.json` sets `microbit_radio_max_packet_size: 250`,
+so a single physical fragment's payload capacity (≈247 bytes) already
+exceeds the wire grammar's 240-byte line ceiling on both directions,
+meaning a legally-encoded v6 line of any length the grammar permits
+always arrives (or departs) as exactly one fragment. `rxLine_` grows
+from 64 to 240 bytes accordingly, and a single-fragment datagram whose
+declared length exceeds that (now 240-byte) capacity is **rejected**
+outright — dropped, never delivered — rather than the previous
+behavior of silently truncating to whatever fit and delivering that
+truncated prefix as though it were the complete line (the hazard that
+let an over-length command execute as a different, shorter, legal one).
+The accept/reject decision is a small, pure, host-portable function
+living directly in this header (no CODAL dependency, no new file
+needed), and a new `rxOversizeDropped_` diagnostic counts the rejection
+alongside the existing `rxFrames_`/`rxAccepted_`. Send-path scratch
+buffers are members, not stack locals — the
 protocol fiber's 2 KB stack overflowed and hard-faulted with them on
 the stack (measured). Those buffers are no longer single-fiber-only
 (sprint 004 ticket 002): the protocol fiber (via `RadioSink::write()`)
@@ -458,12 +484,17 @@
 `emitLine()` (§8) now names this constant directly instead of
 re-declaring its own bare `200` literal, so the two can never drift
 apart silently again the way they already had (WIRE-05/R-21). The
-*value* is unchanged — still 200, still radio's real capacity ceiling
-— this sprint single-sources the constant, it does not raise radio's
-capacity: that is `radio-rx-capacity-fragmentation.md`'s scope (sprint
-010), which also already tracks the adjacent, still-open finding that a
-legal `FULL`-mode telemetry frame can itself reach up to 239 bytes,
-above this same cap (§10's Open Questions).
+*value* was unchanged by sprint 008 — single-sourcing the constant's
+*name*, not raising radio's capacity, was that sprint's scope. **Sprint
+010** is what raises the value: `kMaxPayloadBytes` moves from 200 to
+240, matching `SerialTransport::kMaxLineBytes`/
+`Wire::WireHandler::kMaxLineBytes` exactly rather than staying
+deliberately tighter — see this section's own RX paragraph above for
+why no reassembly protocol was needed to get there, and §15 below for
+the full change. The previously-open finding that a legal `FULL`-mode
+telemetry frame can reach up to 239 bytes (§10's Open Questions) now
+fits the raised 240-byte cap, with exactly 1 byte of headroom — closed,
+but noted as thin, not comfortable.
 
 **Layering.** Both know bytes and framing only — no verbs, no COBS,
 no semantics. Siblings under Protocol, deliberately uncoupled from
@@ -887,16 +918,37 @@
   — that retrofit is sprint 005 (roadmapped, not yet detail-planned).
 - `WireAdapter::lastDone()`/`lastDoneReason()` permanently inert —
   hosts cannot observe motion completion via the reliability channel.
-- Radio RX is a single 64-byte fragment slot with no multi-fragment
-  reassembly (unchanged this sprint — sprint 004 closed the *grammar*
-  question, not the *capacity* one). An inbound line longer than one
-  fragment is clamped to a parseable prefix rather than reassembled or
-  rejected, which can execute as a different, shorter, legal command,
-  not merely drop one — and radio's own TX cap (`kMaxPayloadBytes` =
-  200) is already provably exceedable by a legal, if pathological,
-  telemetry frame (up to 239 bytes measured). Filed as
-  `clasi/issues/radio-rx-capacity-fragmentation.md`, claimed by sprint
-  010.
+- **(Resolved, sprint 010)** ~~Radio RX is a single 64-byte fragment slot
+  with no multi-fragment reassembly... radio's own TX cap
+  (`kMaxPayloadBytes` = 200) is already provably exceedable by a legal,
+  if pathological, telemetry frame (up to 239 bytes measured).~~
+  `RadioTransport`'s RX and TX buffers both now match the wire grammar's
+  240-byte line ceiling exactly, with no reassembly protocol needed
+  (§6) — a single physical radio fragment already carries a full
+  240-byte line under this project's own fleet radio configuration. An
+  inbound line whose declared length exceeds 240 bytes is now rejected
+  outright rather than clamped to a parseable, executable prefix. The
+  239-byte pathological telemetry frame now fits the raised TX cap, with
+  1 byte of headroom — closed, but flagged as thin margin for any future
+  FULL column addition. See §15.
+- **(New, sprint 010)** `GET`'s float-to-wire-text formatting
+  (`WireHandler::formatConfigValue()`) silently overflowed its
+  `uint32_t` scaling intermediate for any config field whose real
+  magnitude reached roughly 4295, substituting a fixed, plausible-
+  looking wrong value (`4294.967040`) rather than the true configured
+  value — found via `full_duty_velocity` (10795.0), the only field in
+  today's 18-entry table whose real value crossed that line, but generic
+  to any field or future value that does. Fixed sprint 010 (widened
+  intermediate arithmetic, input bounded before scaling). See §15.
+- **(New, sprint 010)** A healthy kernel nothing has ever ticked and a
+  kernel behind a genuinely unreachable Nezha brick reported the
+  identical `STATUS` line (`ready=0 connL=0 connR=0 i2cf=0`), because
+  `active_`/`connected_`/`i2cFaultCount_` are only written inside
+  `step()`/`collect()`. Sprint 010 added a `cyc=` field to `STATUS`
+  (§5) closing the observability half. The actual I2C bus-hang guard for
+  a truly unreachable brick remains under investigation as of sprint
+  010's own close — see §15 for what was confirmed and what remains
+  open.
 - **(Resolved, sprint 008)** ~~The post-move settle loop is
   hardware-only-tested.~~ Its bounded-iteration/break-on-rest decision
   is now a `MotionEngine` helper, host-tested directly (§9). Remaining,
@@ -1558,3 +1610,144 @@
   is a real design choice (see `src/DESIGN.md` §1's deliberate
   `shims.cpp`-has-no-header convention) better made deliberately in its
   own review than folded into a Minor here.
+
+## 15. Sprint 010 — architecture diagram and change summary
+
+Substantial-tier sprint update (see `sprint.md`'s Architecture section
+for the full sizing decision and rationale). Two hardware port
+boundaries (radio, the Nezha I2C bus) and one wire-formatting boundary,
+grouped by *kind* — a port that silently does or reports the wrong thing
+instead of failing loudly — the same theme sprint 006 used to group five
+independent kernel/odometry findings. No new module is introduced; the
+vendored kernel (`diffdrive.{h,cpp}`) stays byte-unchanged throughout
+(the dead-brick investigation deliberately does not touch it — see
+below), so no cross-repo (radio-robot firmware) resync is triggered by
+this sprint.
+
+**Sprint Changes (recap — module level; see §5/§6 above for detail):**
+
+- `radio_transport.h`/`.cpp` — `rxLine_` grows 64→240 bytes;
+  `onDatagram()` rejects (rather than truncates-and-accepts) a
+  single-fragment datagram whose declared length exceeds that capacity,
+  counted on a new `rxOversizeDropped_` diagnostic; the accept/reject
+  decision is a pure, host-portable function added directly to the
+  (already host-portable) header. `kMaxPayloadBytes` raised 200→240.
+- `wire_handler.h`/`.cpp` — `Wire::StatusFields` gains `cyc`;
+  `execStatus()`'s format string gains ` cyc=%lu`. `formatConfigValue()`
+  widens its scaling intermediate (float-then-`uint32_t` → a
+  wide-enough intermediate, e.g. `double`) and bounds the input value
+  before scaling, closing a silent-overflow defect generic to any config
+  field whose real magnitude reaches roughly 4295 — found via
+  `full_duty_velocity` (10795.0), fixed for the whole 18-entry table via
+  a looped host test, not a one-field patch.
+- `wire_adapter.cpp` — `WireAdapter::status()` populates the new `cyc`
+  field from the already-existing `diagValue(kDiagCycleCount)` call; no
+  new forward declaration, no `shims.cpp` change for this item.
+- `nezha_port.h`/`.cpp` — the I2C bus-hang guard question was
+  investigated (ticket 004), not committed to a specific mechanism at
+  planning time; see this section's own Risk/Open-Questions treatment
+  below for what a reader of this doc at a later date should expect to
+  find recorded about the outcome (the investigation's own finding,
+  and whether it justified a code change here).
+- `tests/host/` — a new host-portable test exercises
+  `radio_transport.h`'s accept/reject predicate directly (no link
+  against `radio_transport.cpp`); a new drift test ties
+  `RadioTransport::kMaxPayloadBytes`,
+  `Wire::WireHandler::kMaxLineBytes`, and
+  `SerialTransport::kMaxLineBytes` together; `test_wire_telemetry_frame.py`'s
+  pinned boundary assertions move from 200 to 240; `WireMockAdapter` and
+  the real-`WireAdapter` test surface gain `cyc` coverage; a new looped
+  test sweeps all 18 `kFields` entries through `GET` for the
+  formatting-overflow fix.
+
+**No component/module diagram.** Every edge these changes travel already
+exists (`src/DESIGN.md` §1's layer map): `WireAdapter`'s new `cyc` field
+reads an already-existing `diagValue()` forward declaration; the radio
+buffer/predicate changes stay entirely inside `RadioTransport`; the
+`formatConfigValue()` fix stays entirely inside `WireHandler`; the
+dead-brick investigation reaches no further than the already-existing
+`shims.cpp → NezhaMotorPort → Motor::begin()/tick()` relationship. No
+new module is composed, and no new cross-module edge is added anywhere
+in this sprint — the same reasoning sprint 008 and sprint 020 each used
+to omit their own diagrams under the substantial tier.
+
+**No entity-relationship diagram.** No persistent data model exists in
+this embedded package, unchanged by this sprint.
+
+**No dependency-direction graph** beyond this statement: dependency
+direction is unchanged (Presentation/wire → MotionEngine → Kernel/ports,
+kernel at the bottom); nothing in this sprint adds, removes, or reverses
+an edge.
+
+**Migration concerns.** Three real wire-behavior changes, all detailed
+in `sprint.md`'s own Architecture section and repeated here for the
+overlay's own completeness: (1) an inbound radio line whose declared
+length exceeds 240 bytes is now dropped outright instead of silently
+truncated-and-executed as a shorter command — a deliberate safety
+improvement, not a regression, with no known in-tree caller depending on
+the old truncation behavior; (2) `STATUS` gains one new `key=value`
+field (`cyc=`), purely additive, following the exact precedent sprint
+004 ticket 004 set for `i2cf=`; (3) `GET full_duty_velocity` (and any
+future field whose real magnitude crosses ~4295) now replies with the
+true configured value instead of a fixed wrong constant — a correctness
+fix a host should never have built logic around the old value for, since
+it was transparently nonsensical. No data persists across power cycles
+anywhere in this system, so none of the three carries a data-migration
+question beyond the behavior changes themselves.
+
+**Risk.** The dead-brick guard's actual runtime behavior against a truly
+unreachable brick is, by this sprint's own design, not proven by any
+host test — `nezha_port.cpp` requires `pxt.h` and has no host-portable
+seam for a non-returning I2C call. Whatever ticket 004 concluded and
+whatever (if anything) it changed in `nezha_port.cpp` is proven only by
+ticket 005's bench checklist, executed after this sprint closes. A
+reader relying on this document to know the dead-brick question's final
+state should read ticket 004/005's own recorded outcomes, not assume
+this section describes a confirmed guard mechanism.
+
+**Design Rationale (selected decisions — condensed; full versions with
+alternatives-considered live in `sprint.md`'s own Architecture section):**
+
+*Decision: close radio's capacity gap by enlarging buffers to the wire's
+existing 240-byte ceiling and rejecting the narrow residual overflow,
+not by building multi-fragment reassembly.* The physical single-fragment
+MTU (≈247 bytes, this project's own `microbit_radio_max_packet_size:
+250`) already exceeds the wire grammar's 240-byte line cap on both
+directions, so reassembly across multiple physical fragments solves a
+problem that does not exist at this MTU — confirmed by
+`radio_transport.h`'s own pre-existing header comment, not a new
+assumption introduced by this sprint.
+
+*Decision: `STATUS`'s new `cyc=` field reuses the existing
+`kDiagCycleCount` readback rather than inventing a new tri-state "motor
+health" signal.* The distinction this sprint's Goals require is already
+fully derivable from two already-exposed numbers (`cyc`, `i2cf`/`connL`/
+`connR`) once `cyc` is visible outside FULL telemetry; a new enum would
+be speculative generality ahead of that combination even being tried.
+
+*Decision: fix `formatConfigValue()` by widening its intermediate
+arithmetic and bounding the input, not by raising the post-scale clamp
+or special-casing `full_duty_velocity`.* `uint32_t` cannot represent
+`real_value × 1,000,000` for any real value much past ~4295 no matter
+where a clamp is set inside its range — the type, not the clamp
+threshold, is the actual ceiling, so only widening the intermediate
+removes it.
+
+**Open Questions (sprint 010, beyond §10's own entries above):**
+
+- Which codal-nrf52/codal-microbit-v2 release this project's build
+  resolves, and whether it already includes upstream's own I2C
+  transaction-timeout/`waitForStop` hang-recovery work — ticket 004's
+  central research question, gating any further dead-brick
+  implementation.
+- Whether `Motor::begin()`/`tick()` should eventually gain an explicit
+  bounded-wait/status-returning contract (a kernel-level, cross-repo
+  change to the vendored `diffdrive.{h,cpp}`) — deliberately deferred,
+  not assumed, pending ticket 004's findings.
+- A bench session that motivated this sprint also observed a wire-native
+  `WHEELS_X` command accepted with no error while `cyc` stayed at 0 for
+  the command's own duration, distinct from a `RUN:`-bridged block
+  command that did tick the kernel — not one of this sprint's three
+  claimed issues, not fixed here, but now trivially reproducible given
+  `cyc=`'s new visibility in `STATUS`. Flagged for a future
+  investigation.
```
