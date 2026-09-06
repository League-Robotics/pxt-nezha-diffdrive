---
source_file: host-DESIGN.md
source_hash: 9f143c5c3354ee6be56afcd01269f7f01917b7c7db6f123717a683a0612d74bf
---
# Diff: host-DESIGN.md

Comparison of the sprint overlay copy of `host-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- host-DESIGN.md (pristine)
+++ host-DESIGN.md (current)
@@ -1,10 +1,10 @@
 # tests/host — native host test harness
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable
-(as of sprint 008: boundary-value timeout coverage for all six motion
-verbs, `kVersion`/`RUN_EVENT_SOURCE` drift tests, the `WaHandle`
-wedge/`setWheelsTimed`/config-rounding re-sync plus its own drift test,
-a new settle-loop shim, and `TLM AUTO`/`BUFFER` pinning tests)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
+stable. The motion-engine shim is compiled once per session in
+`conftest.py` (§2); which translation units this harness can and cannot
+reach is enumerated in `tests/DESIGN.md` and enforced by
+`test_pxt_bound_exclusion_is_current.py` (§6).
 
 ---
 
@@ -116,6 +116,26 @@
   `compile_shared_lib()` (defined in `test_kernel_harness.py`,
   reused by every later suite: same compiler invocation, no CMake)
   and asserts through the handle.
+- **`conftest.py`** (sprint 034 ticket 010) — the ONE place the
+  motion-engine shim is compiled. Thirteen files here drive the same
+  four translation units behind the same `meCreate()` handle, and each
+  used to carry its own copy of the source list, its own `_bind()` and
+  its own session-scoped `motion_lib` fixture with its own `out_name` —
+  so the identical compile ran thirteen times a session, and one source
+  list existed in thirteen places to drift. `conftest.py` now holds
+  `MOTION_SHIM_SOURCES`, a `_bind_motion_lib()` that is the union of
+  those thirteen binders (70 symbols; no two files had disagreed about
+  a signature), and the `motion_lib` fixture they all take by name.
+  MEASURED 2026-09-06, `uv run pytest tests/host tests/tools -q`:
+  75.30 s before (1719 passed), 57.88 s / 58.47 s after (1722 passed --
+  three new tests this ticket adds). The remainder of the run is not the
+  compile: `tests/tools` alone takes ~28 s on its own, unchanged by this. Consequence: those
+  files share ONE `ctypes.CDLL` object now, so a binder applied at call
+  time (`test_segment_lazy_origin.py`'s `_bind_rebase()`) mutates shared
+  state and must stay signature-compatible with the union. This is not a
+  general "fixtures go in conftest" policy — the kernel, wire and
+  run-queue shims are different source lists with one owner file each,
+  and they stay where they are.
 
 Run: `uv run pytest` from the repo root. Modeled on
 radio-robot-lib's `tests/protocol` harness.
@@ -173,6 +193,9 @@
 ## 5. Interfaces
 
 ### Exposes
+- **`motion_lib`** (`conftest.py`) — the compiled-once, fully bound
+  motion-engine shim, available by name to every test file in this
+  directory.
 - **`uv run pytest`** — the whole suite from a clean checkout;
   scope with a path (`uv run pytest tests/host/test_wire_grammar.py`).
   Also the once-per-sprint gate `close_sprint` runs.
@@ -208,7 +231,10 @@
 `test_regression_post_move_neutral.py`, which stays as the "why this
 matters" test); and `TLM AUTO`/`BUFFER` `thdr`/`err` pinning.
 
-Not covered, by design (CODAL-bound): `nezha_port`, `otos_port`, the
+Not covered, by design (CODAL-bound) — the canonical list, per file,
+with what gates each one instead, is `tests/DESIGN.md` "Translation
+units nothing on the host compiles", held against the tree by
+`test_pxt_bound_exclusion_is_current.py`. In summary: `nezha_port`, `otos_port`, the
 transports, `protocol.cpp`'s fiber loop and RUN bridge, and
 `shims.cpp`'s real Rig composition/watchdog — hardware sessions are
 their only test. Where a decision inside one of those has been pulled
```
