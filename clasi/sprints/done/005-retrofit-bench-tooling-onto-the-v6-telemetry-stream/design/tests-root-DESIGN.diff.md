---
source_file: tests-root-DESIGN.md
source_hash: a92db123a6927cb5710fb16ac86208aea16e54646902a5ca9b30da45f2b5dc21
---
# Diff: tests-root-DESIGN.md

Notes the `tests/tools/` subsystem now has two files, not one, adding
`test_tlm.py` (sprint 005) alongside `test_make_deploy_triage.py`
(sprint 008).

```diff
--- tests-root-DESIGN.md (pristine)
+++ tests-root-DESIGN.md (current)
@@ -13,13 +13,18 @@
   stack, wire adapter) compiled for the desktop with the system
   compiler and driven from pytest through `ctypes`, against fake
   ports. No micro:bit, PXT, or CODAL anywhere in the link.
-- [`tools/`](tools/DESIGN.md) (sprint 008) — plain-Python unit tests
-  over `tools/` scripts' own logic, no shim compilation and no
-  hardware/network. One file so far: `test_make_deploy_triage.py`,
-  pinning `tools/make_deploy.py`'s `classify_attempt()` (hard-failure
-  vs. known-benign-retry vs. unknown build-output triage) against
+- [`tools/`](tools/DESIGN.md) (sprint 008, extended sprint 005) —
+  plain-Python unit tests over `tools/` scripts' own logic, no shim
+  compilation and no hardware/network. `test_make_deploy_triage.py`
+  pins `tools/make_deploy.py`'s `classify_attempt()` (hard-failure vs.
+  known-benign-retry vs. unknown build-output triage) against
   saved/synthetic build-log fixtures — see `tools/DESIGN.md`'s "Build
   checkpoint triage" section for what the logic itself decides.
+  `test_tlm.py` (sprint 005) pins `tools/tlm.py`'s `TlmStream` parser
+  against the shared golden telemetry fixture in
+  `tests/host/golden_telemetry.py` — header tracking, seq-gap loss
+  counting and wraparound, arity/malformed rejection, orphan frames,
+  and the unit-conversion helpers.
 
 Not to be confused with the sibling `test/` root (singular) — those
 are PXT `testFiles`, on-robot MakeCode programs with no assertions,
```
