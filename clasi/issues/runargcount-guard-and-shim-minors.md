---
status: pending
sprint: '007'
---

# runArgCount null guard + small-shim Minors batch

Priority: **Low** — code review 2026-08-23, R-15 + grouped Minors (BLK-02
CONFIRMED-narrowed; Minors from correctness-blocks/modularity annexes).

1. **runArgCount guard (R-15)**: `main.ts:233-235` dereferences `runParts`
   without the `!runParts` guard its sibling `runArgText()` has. Any call
   before the first RUN event is the documented panic-980 silent boot
   death. Narrowing from verification: any top-level
   `onRun`/`onRunCommand` registration disarms it via `ensureRunState()`,
   so exposure is programs using `runArgCount` with no handler registered.
   One-line fix; add the guard.
2. **Minors batch** (fix in the same pass; each is one-to-five lines —
   details in `docs/code-review/2026-08-23/raw/`):
   - dead `microphone` dependency in pxt.json (BLK Minor)
   - tsconfig file set cannot type-check main.ts (missing serial.ts ref)
   - dead `maxNudges` variable (main.ts:546)
   - `goToWorld` exported JSDoc still promises repeat-until-arrival; the
     one-pass rewrite made that false (contradicts the
     camera-is-diagnostics doctrine)
   - DIAG `case 25` spliced between the `// 23/24` comment and its cases
     (shims.cpp:707-712) — reorder
   - float→int cast UB at the wire boundary for values near 2^31
     (WIRE-08: host INT32_MIN vs target VCVT saturate divergence;
     SET ×1000 overflow) — clamp before cast
   - `[18]`-sized verb tables under-initialized: add-a-verb fails loudly
     but remove-a-verb compiles silently (WIRE-09, narrowed to
     unrecognized-verb/HELP paths) — size from the array or static_assert
