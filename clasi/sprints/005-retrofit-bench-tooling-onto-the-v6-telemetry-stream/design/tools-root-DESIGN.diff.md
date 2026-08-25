---
source_file: tools-root-DESIGN.md
source_hash: 39aab7a7bfe058eb8559e167a07355b3f0b83f87f1f6749e3a8be7602dd00765
---
# Diff: tools-root-DESIGN.md

Comparison of the sprint overlay copy against its pristine (seed-commit) canonical version.

```diff
--- tools-root-DESIGN.md (pristine)
+++ tools-root-DESIGN.md (current)
@@ -68,7 +68,20 @@
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
