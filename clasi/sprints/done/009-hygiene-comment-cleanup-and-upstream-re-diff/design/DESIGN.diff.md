---
source_file: DESIGN.md
source_hash: 4ccaf205c417073b9be7a6cc67ef86a0a7e1530f0f65f4aa2b4d077e0510c834
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -1,6 +1,6 @@
 # src — the DiffDrive extension
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-25 · **Status:** in-flux (as-built through sprint 009, closed and merged — the 2026-08-23 code review's comment-hygiene work order applied across every layer below, with every REWRITE checked against `verify-comments.md`'s corrections and, for unsampled items, the same load-bearing test; the vendored kernel re-diffed against current upstream (`League-Robotics/radio-robot`, kernel now at `src/firm/diffdrive/`), all five `diffdrive.h` truncated comments restored, and this section's own §2 provenance statement now the one place the upstream path/repo/maintenance-boundary is stated — see §15; before that, sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
 
 `src/` is flat — no subdirectories — so this one document carries the
 logical subsystem breakdown as sections. Global conventions (units
@@ -70,10 +70,31 @@
 **Dependencies.** None. This is the bottom of the stack.
 
 **Invariants.**
-- *Vendored, synced copy*: extracted from the radio-robot firmware
-  (`src/firm/control/`); a fidelity suite in that repo holds the two
-  byte-for-byte to the same control law. Fix kernel bugs in both
-  repos, never only here.
+- *Vendored, synced copy*: extracted from
+  [`League-Robotics/radio-robot`](https://github.com/League-Robotics/radio-robot),
+  where the kernel currently lives at
+  `src/firm/diffdrive/differential_drive.{h,cpp}` (**sprint 009**: the
+  kernel moved within that repo since this package was first vendored;
+  `src/firm/control/differential_drive.h` — the path this section
+  previously named — is now a thin forwarding-adapter header, not the
+  kernel itself). A fidelity suite in that repo holds the two
+  byte-for-byte to the same control law; fix kernel bugs in both
+  repos, never only here, until the firmware is cut over to depend on
+  this package directly. **One known exception** (found by this
+  sprint's upstream re-diff, not introduced by it): `cycleGapCount`/
+  `cycleGapCount_` — the idle-gap re-anchor counter from
+  `clasi/issues/done/first-move-after-idle-runs-at-full-duty.md`
+  (commit 704c40d) — exists only in this repo's copy and has not yet
+  been ported upstream; no other divergence, comment or code, was
+  found in either file. This is the one authoritative statement of
+  the kernel's upstream repo and path — per-file headers in `src/`
+  point at this paragraph rather than each restating it (see §15).
+  Maintenance boundary: the kernel files (`diffdrive.h`/`.cpp`) are a
+  synced copy, edited in both trees; the port/shim files
+  (`nezha_port.*`, `otos_port.*`, `radio_transport.*`,
+  `platform_ports.h`, `shims.cpp`, `main.ts`) are this repo's own —
+  *ported from*, not *synced with*, their respective upstream
+  references — and are edited here only.
 - Each `step()` runs split-phase encoder sampling:
   `requestSample()` → 4 ms settle sleep → `tick()` per wheel. Anything
   that lands other I2C traffic inside that settle window destroys the
@@ -1558,3 +1579,78 @@
   is a real design choice (see `src/DESIGN.md` §1's deliberate
   `shims.cpp`-has-no-header convention) better made deliberately in its
   own review than folded into a Minor here.
+
+## 15. Sprint 009 — comment cleanup and upstream re-diff, change summary
+
+**No diagram.** This sprint composes nothing new — no module, no
+cross-module dependency, no dependency-direction change, no data-model
+change (mirrors sprint 020's own precedent for the same reason). The
+layer map in §1 and every module's responsibility/dependency
+description elsewhere in this document are unchanged by this sprint;
+a diagram here would just redraw §1's table.
+
+**What changed.**
+- **Vendored-kernel re-diff and restoration.** `diffdrive.h`'s five
+  comments truncated mid-sentence during a past lossy vendoring step
+  (lines 81, 84, 90, 91, 125) are restored verbatim from upstream
+  `League-Robotics/radio-robot` `src/firm/diffdrive/`. The pair is
+  re-diffed against that current location; any divergence beyond
+  comments is catalogued as deliberate or fixed if proven accidental
+  (scoped narrowly — not a kernel refactor). §2's "Vendored, synced
+  copy" invariant above is now the one authoritative statement of the
+  kernel's upstream repo, current path, and maintenance boundary —
+  every per-file provenance comment in `src/` (`diffdrive.*`,
+  `otos_port.*`, `radio_transport.*`, `nezha_port.cpp`) points at this
+  paragraph instead of independently restating a path that goes
+  stale, closing the failure mode that let a superseded path
+  (`src/firm/control/`) and an unresolvable repo name
+  (`radio-robot-elite`) both survive as long as they did.
+- **Comment-hygiene work order.** The 2026-08-23 code review's
+  135-item audit (11 DELETE, 123 REWRITE, 1 ADD across 59 files, ~16%
+  of ~854 audited blocks) is applied throughout every layer this
+  document describes, corrected against `verify-comments.md`'s
+  adversarial spot-check wherever it overrides the audit — 8 of 16
+  sampled REWRITEs would otherwise have destroyed load-bearing
+  content, so every unsampled REWRITE gets the same "preserves every
+  invariant, unit, measured value, and derivation" check before
+  landing. Six comments the audit or its correction pass would have
+  regressed were identified during planning as already superseded by
+  better comments sprints 006-008 wrote (`motion_engine.h`'s
+  `rotationalSlip_` derivation chain, `shims.cpp`'s `tickDrive()`/
+  settle-loop essay, `wire_handler.cpp`'s decode-clamp region,
+  `radio_transport.h`'s `kMaxPayloadBytes` relationship,
+  `protocol.cpp`'s `kVersion` sync note, `protocol.h`'s telemetry-gap
+  note) and were left alone or re-derived from current code rather
+  than overwritten.
+- **Comment-standards guidance.** `docs/code-review/guidelines.md`'s
+  existing comment-hygiene dimension gains a subsection distilling the
+  audit's five recurring anti-patterns (ticket-archaeology headers,
+  reviewer-justification essays, stale cross-layer claims, diff
+  restatement, orphaned comments surviving code motion), so future
+  work doesn't regenerate the noise this sprint removed.
+
+**Why.** The audit ran before sprints 006-008 rewrote large parts of
+the exact files it targets; running the cleanup after all three
+(deliberately, per this sprint's own charter) means the work order
+applies once, to the code as it actually ends up, at the cost of every
+item needing re-anchoring by content match rather than by the audit's
+now-stale line numbers.
+
+**Impact on existing components.** None structurally — every module's
+responsibility, boundary, and dependency set above is unchanged. The
+only observable-behavior change permitted is a narrowly-scoped
+accidental-divergence fix in `diffdrive.{h,cpp}`, if the re-diff finds
+one, verified against the specific upstream contract it restores.
+
+**Migration concerns.** None. No data migration, no wire-format
+change, no deployment sequencing beyond the ordinary flash cycle this
+sprint's own build-checkpoint ticket exercises.
+
+**Open questions.** None new. The pre-existing `tools/` retrofit gap
+(§10) and the target-viability build-checkpoint convention (§11) are
+unaffected by this sprint; two small filing requests this sprint's
+planning surfaced (a DIAG-has-no-v6-equivalent note in
+`wire_adapter.cpp`, and several `tools/` scripts speaking a retired
+wire vocabulary) are left for the team-lead to convert into CLASI
+issues rather than resolved here, per this sprint's behavior-neutral
+scope.
```
