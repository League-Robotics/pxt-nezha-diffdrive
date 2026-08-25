---
source_file: tools-root-DESIGN.md
source_hash: 31731447094110f2ff6662d0dd3f84104d1b71407a0c11cbece5848d684c6f74
---
# Diff: tools-root-DESIGN.md

Documents everything sprint 005 changed in `tools/`: the new
"Telemetry (`tlm.py`)" section (ticket 001); `camproc.py`/`field.py`'s
link-layer consolidation, including the `APRILTAGS_VENV`-env-var
interpreter-resolution mechanism (ticket 003, resolving sprint.md's
Open Question 2); `make_deploy.py`'s `--testrig` scratch-copy build
path (ticket 005); and the five ground-truth tools' retargeting onto
named RUN verbs (ticket 006). Replaces the stale "Known limitation —
the telemetry gap" section with a "Resolved" one, `~~struck~~` per
this doc's own convention.

```diff
--- tools-root-DESIGN.md (pristine)
+++ tools-root-DESIGN.md (current)
@@ -6,10 +6,11 @@
 and charting the robot. Flat root, no subsystems. Run under `uv`
 (`uv run python tools/<script>.py`) — including `robotlink.py`, now
 that `pyproject.toml` declares `pyserial` (sprint 005; previously only
-the system interpreter had it); `camlink.py` still runs under the
-aprilcam pipx venv, its interpreter resolved once by `camproc.py`
-rather than hardcoded per spawn site. Conventions (units, frames,
-camera doctrine) are in
+the system interpreter had it, so every bench tool ran only under a
+different interpreter than the project's own test/dev environment);
+`camlink.py` still runs under the aprilcam pipx venv, its interpreter
+resolved once by `camproc.py` rather than hardcoded per spawn site.
+Conventions (units, frames, camera doctrine) are in
 [`docs/design/design.md`](../docs/design/design.md).
 
 ## Link layer — what everything talks through
@@ -27,16 +28,23 @@
   round (`mount_yaw_rad = -pi/2`) — an unregistered tag reports a
   plausible but wrong position.
 - **`camproc.py`** (sprint 005) — owns camera-subprocess lifecycle:
-  resolves the AprilTags interpreter once (not six hardcoded spawn
-  sites), surfaces a spawned camera's `ERR` lines to the calling tool
-  instead of discarding them, and invalidates a cached pose once the
-  stream is marked dead — a mid-session camera death is now a visible
-  failure, not a silently frozen pose fed back into `place()`/`fix()`.
+  resolves the AprilTags interpreter once via `resolve_venv()` (the
+  `APRILTAGS_VENV` env var, defaulting to the historically-correct
+  path — not six hardcoded spawn sites, two of which pointed at a
+  stale venv where `import aprilcam` no longer worked), surfaces a
+  spawned camera's `ERR` lines to the calling tool instead of
+  discarding them, and invalidates a cached pose (`.latest`/`.fix()`
+  both go `None`) once the stream is marked dead — a mid-session
+  camera death is now a visible failure, not a silently frozen pose
+  fed back into `place()`/`fix()`.
 - **`field.py`** (sprint 005) — owns playfield geometry: the dot/corner
-  constants, `wrap()`, and corner scoring that used to be copied into
-  seven separate `Cam` wrapper scaffolds (with two incompatible
-  `latest` tuple orders) across the tour/ground-truth tools. Consumes
-  `camlink.py`'s existing shared `Cam` rather than re-wrapping it.
+  constants, `wrap()`, `score_corners()` (gap-aware corner scoring),
+  and `path_deviation()` that used to be copied into seven separate
+  `Cam` wrapper scaffolds (with two incompatible `latest` tuple orders
+  — now unified to `(x_cm, y_cm, yaw_deg)`, documented in the module's
+  own docstring) and 4 disagreeing corner-scoring implementations
+  across the tour/ground-truth tools. Consumes `camlink.py`'s existing
+  shared `Cam` (via `camproc.py`) rather than re-wrapping it.
 
 ## Telemetry (`tlm.py`, sprint 005)
 
@@ -68,7 +76,20 @@
   `disablesVariants: ["mbdal"]` dropped (kept, it produces a hex that
   is dead on the device). Deletes the hex up front and verifies it
   exists afterwards, because the expected V1 `TS9283` error
-  nondeterministically deletes it.
+  nondeterministically deletes it. `test/testrig.ts` (the zeguz OTOS
+  rig, sprint 005) is a separate, mutually exclusive on-robot program
+  from `test.ts` -- each has its own top-level `basic.forever` loop and
+  button handlers, so the two must never both be promoted into one
+  scratch copy's `files`. `--testrig` builds/type-checks `testrig.ts`
+  alone in its own scratch copy (`.tmp/deploy-testrig/`), generated
+  fresh from `pxt.json`'s `testFiles` list on every run the same way
+  the primary deploy is -- this is what makes `testrig.ts` "built as
+  part of a routine, automated path" again, closing the build-hygiene
+  half of `testfiles-are-not-type-checked-testrig-is-broken.md` (its
+  old hand-curated scratch copy never contained the file at all, which
+  is how it sat uncompilable for weeks unnoticed). Produces no
+  flashable hex that matters -- it exists only to prove `testrig.ts`
+  compiles, so `--flash` is rejected together with `--testrig`.
 
 ### Build checkpoint triage (`make_deploy.py`, sprint 008)
 
```
