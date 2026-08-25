---
source_file: tools-DESIGN.md
source_hash: 8e431d384e455f6e5f9e8ed264e2346aa6c1b0d88cebd0010cd9a17f88bcf20d
---
# Diff: tools-DESIGN.md

Adds full documentation for the new `test_tlm.py` (sprint 005) unit
test file across every section this doc already uses for
`test_make_deploy_triage.py` — Purpose, Orientation, Constraints and
Invariants, Interfaces, and Coverage — so the new file is pinned to
the same standard as the existing one from day one.

```diff
--- tools-DESIGN.md (pristine)
+++ tools-DESIGN.md (current)
@@ -1,6 +1,6 @@
 # tests/tools — unit tests for the repo's own Python tooling
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (sprint 005 adds `test_tlm.py`, pinning `tools/tlm.py`'s telemetry parser)
 
 ---
 
@@ -17,7 +17,7 @@
 different fixtures, different failure modes — one shared harness would
 fit neither well.
 
-One file so far: `test_make_deploy_triage.py`, pinning
+Two files: `test_make_deploy_triage.py`, pinning
 `tools/make_deploy.py`'s build-checkpoint triage (added sprint 008,
 ticket 006) — the logic that decides whether a real `pxt build`
 attempt succeeded, hard-failed, or hit a known-benign abort worth
@@ -30,11 +30,22 @@
 each one caught only because some ticket happened to need real build
 evidence. The triage is now the standing mechanism that catches that
 class; this file is what makes it fail loudly, instead of silently, if
-someone breaks it later. Nothing under `tools/` knows this directory
-exists.
+someone breaks it later.
 
+`test_tlm.py` (sprint 005) applies the same "tests that can fail"
+theme to `tools/tlm.py`'s `TlmStream` telemetry parser and its three
+fail-loud guards (`require_stream()`, `write_tlm_csv()`, the
+`.meta.json` zero-frame refusal) — the parser this sprint introduced
+specifically to replace six tools' worth of scattered, silently-broken
+arity logic (`tour_watch.py:202`, `tour_capture.py:70`), so it is
+pinned here from day one rather than left to drift the same way. Both
+files import the module under test directly, in-process; nothing under
+`tools/` knows this directory exists.
+
 ## 2. Orientation
 
+### `test_make_deploy_triage.py`
+
 Two parts, one file:
 
 - **Fixtures** — module-level string constants holding synthetic and
@@ -54,6 +65,41 @@
 Run: `uv run pytest tests/tools/test_make_deploy_triage.py`, or as
 part of the whole suite (`uv run pytest` from the repo root).
 
+### `test_tlm.py` (sprint 005)
+
+Imports `tools/tlm.py`'s `TlmStream` directly (same `sys.path`-insert
+convention as `test_make_deploy_triage.py`) and feeds it synthetic and
+captured `thdr`/`t` lines, no serial/radio link involved:
+
+- **Header tracking** — a `thdr` sets the current column set; an
+  identical re-read is a no-op; a second `thdr` after 20 frames with an
+  unchanged column set is still accepted (the firmware's 1 Hz memo
+  re-emit, not an error); a `t` before any `thdr` counts into
+  `orphan_frames` and is not added to `frames`.
+- **`seq`-gap loss** — consecutive `seq` values with a gap increment
+  `dropped`/`loss_pct` by the right amount; a 7-bit wraparound
+  (127 → 0) is not miscounted as a gap.
+- **Arity/malformed rejection** — a `t` line whose value count disagrees
+  with the last `thdr`'s column count counts into `malformed`, is not
+  added to `frames`, and does not raise (fail-loud is `require_stream`/
+  `write_tlm_csv`'s job, not a parse-time exception here).
+- **Unit helpers** — `pose_cm`/`otos_cm`/`wheels_mms` against the
+  shared golden frame in
+  [`tests/host/golden_telemetry.py`](../host/golden_telemetry.py) (the
+  same fixture `tests/host/test_wire_telemetry_projection.py` uses as
+  expected *emitted* wire bytes, imported here as parser *input*, so
+  emitter and parser are pinned against one shared source of truth and
+  cannot silently drift apart from each other).
+- **Fail-loud guards** — `require_stream()` raises before any
+  run-triggering `send()` is observed on a fake link when no `t` frame
+  arrives inside its timeout, and returns normally once one does;
+  `write_tlm_csv()` raises on zero accumulated frames and leaves no
+  file on disk, and writes normally (with a matching `.meta.json`
+  sidecar) otherwise.
+
+Run: `uv run pytest tests/tools/test_tlm.py`, or as part of the whole
+suite.
+
 ## 3. Constraints and Invariants
 
 - **A real compile diagnostic wins, unconditionally.**
@@ -82,6 +128,18 @@
   tests replace every collaborator that would otherwise shell out or
   touch disk state. A future test that needs a real `pxt build` does
   not belong in this file.
+- **`test_tlm.py`: an absent CSV is unambiguous; an empty one is not
+  — never assert the opposite.** Every fail-loud-guard test asserts
+  *both* halves of that: the raising path leaves no file on disk, and
+  the non-raising path's file/sidecar actually matches the fed data.
+  Asserting only "it raised" without also checking "and wrote nothing"
+  would leave the guard's whole reason for existing unverified.
+- **`test_tlm.py`: parser input is the emitter's own expected-output
+  fixture, not a hand-rolled one.** `tests/host/golden_telemetry.py`'s
+  `EXPECTED_T_LINE`/`EXPECTED_THDR_LINE` (what `WireHandler` is proven
+  to emit) are fed to `TlmStream` as-is; a test that instead
+  hand-wrote its own "plausible" `t` line could pass while silently
+  disagreeing with what the firmware actually sends.
 
 ## 4. Design
 
@@ -103,13 +161,24 @@
 ### Exposes
 - **`uv run pytest tests/tools/test_make_deploy_triage.py`** — this
   file alone.
-- Also runs as part of **`uv run pytest`** from the repo root, and the
-  once-per-sprint gate `close_sprint` runs.
+- **`uv run pytest tests/tools/test_tlm.py`** (sprint 005) — this file
+  alone.
+- Both also run as part of **`uv run pytest`** from the repo root, and
+  the once-per-sprint gate `close_sprint` runs.
 
 ### Consumes
 - **`tools/make_deploy.py`**'s `classify_attempt()` and `build()` —
   see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Build checkpoint
   triage" section for the contract this file pins.
+- **`tools/tlm.py`**'s `TlmStream`, `require_stream()`,
+  `write_tlm_csv()`, and the unit-conversion helpers (sprint 005) —
+  see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Telemetry
+  (`tlm.py`)" section.
+- **`tests/host/golden_telemetry.py`**'s expected wire-frame constants,
+  as parser input (sprint 005) — the same fixture
+  `tests/host/test_wire_telemetry_projection.py` uses as expected
+  emitted bytes, so `test_tlm.py` cannot silently drift from what the
+  firmware actually sends.
 
 ## 6. Coverage — what is and is not tested here
 
@@ -119,6 +188,11 @@
 manifest-omission-caught-via-the-same-path case; `build()`'s
 retry-then-succeed path, its bounded-retry failure path (the benign
 shape recurring on retry), and its no-retry-on-hard-failure path.
+`TlmStream`'s header tracking (fresh, no-op re-read, 20-frame memo
+re-emit), `seq`-gap loss counting and 7-bit wraparound, arity/malformed
+rejection, orphan-frame counting, the unit-conversion helpers against
+the shared golden frame, and both fail-loud guards' raising and
+non-raising paths.
 
 Not covered, by design: `sync()` (manifest promotion/rewrite),
 `flash()` (the `mbdeploy` subprocess), and `main()` — none of them are
@@ -127,4 +201,8 @@
 which this subsystem's whole purpose is to avoid needing. A real build
 against a sprint's own combined final state is verified manually and
 recorded in `tools/DESIGN.md`'s "Build checkpoint triage" section, not
-exercised here.
+exercised here. For `test_tlm.py`: a live radio link's actual loss
+behavior is not exercised here either — that is the sprint's
+real-hardware end-to-end check (`tour_run.py --tour world` against a
+real robot), not a unit test; this file only pins the parsing/guard
+*logic* against synthetic and captured-but-replayed frames.
```
