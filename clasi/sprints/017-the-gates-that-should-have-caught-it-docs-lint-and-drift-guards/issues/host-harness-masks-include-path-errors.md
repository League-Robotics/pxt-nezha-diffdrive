---
status: in-progress
sprint: '017'
tickets:
- 017-009
---

# The host test harness passes `-I src`, so it cannot see include-path errors the real build fails on

Priority: **High** — this is a structural blind spot, not a bug. It means a
green 597-test suite is not evidence that the firmware's `#include` graph is
correct, and the failure it hides appears only in the CLOUD C++ compile.

## What was found

Sprint 013 ticket 001 moved four files into `src/core/` and had to establish how
PXT resolves includes. Two rules, both verified against a real
`tools/make_deploy.py` build:

| include shape | correct form | wrong form fails how |
|---|---|---|
| cross-directory | `#include "core/diffdrive.h"` | bare name -> `fatal error: diffdrive.h: No such file or directory` |
| same-directory sibling | `#include "diffdrive.h"` | qualified -> `fatal error: core/diffdrive.h: No such file or directory` |

The same-directory case is the surprising one and it is the reverse of what the
sprint plan assumed. PXT stages files at their `pxt.json`-relative path, and the
C preprocessor's quote-include search checks the **including file's own
directory first** — so from inside `src/core/`, `"core/diffdrive.h"` resolves to
`src/core/core/diffdrive.h`.

## Why the host suite cannot catch either mistake

`tests/host/`'s compile harness passes **`-I src`**. The real PXT build does
not. With `-I src` on the command line, BOTH the bare and the qualified form
resolve, so every include arrangement looks correct to pytest.

That is the whole problem: **the host harness is more permissive than the
target.** A wrong include passes 597 tests and then fails in the cloud
compiler, where the diagnostic is remote, slow, and buried in a long build log.

## This is the same shape as an already-known divergence

`tests/host/` compiles `-std=c++20` while both embedded targets compile
`-std=c++11` — a gap that let a `Wire::Column` NSDMI regression pass 253 tests
while no hex could be built for either target, until a mechanical
`test_cxx11_syntax_gate.py` was added to close it.

`-I src` is the same class of defect: a harness convenience that silently
widens what compiles. It deserves the same treatment.

## Options, in rough order of preference

1. **Drop `-I src` from the host harness** and compile with the include base the
   real build uses, so host compilation exercises the true include graph. Most
   faithful; may require per-file working directories to emulate PXT's staging.
2. **Add a mechanical include-shape gate** in `tests/host/`, in the spirit of
   `test_cxx11_syntax_gate.py` and `test_pxt_manifest_completeness.py`: parse
   every `#include "..."` under `src/`, and assert the path is bare iff the
   target is a sibling in the same directory, and qualified-relative-to-`src/`
   otherwise. Cheap, deterministic, and needs no compiler.
3. Do nothing and rely on the per-ticket build. Rejected as a standing policy —
   it works while sprint 013 is running and mandating builds, but the guard has
   to survive the sprint.

Option 2 is probably the right first move; option 1 is the real fix.

## Caveat

The `-I src` observation comes from ticket 001's report, which established it
while diagnosing a real build failure. The exact harness invocation should be
re-read from `tests/host/` before implementing, and whether every host test
module passes the flag (or only some) has not been checked.

## Related

- `tests/host/test_cxx11_syntax_gate.py` — the precedent for closing a
  harness/target divergence mechanically.
- `tests/host/test_pxt_manifest_completeness.py` — same family; its own
  non-recursive `iterdir()` would have silently stopped checking moved files
  until ticket 001 made it recursive.

---

## CORRECTION (2026-08-25): the rule is simpler than first written above

The table above says cross-directory includes are "qualified relative to
`src/`". That is **wrong for sibling directories** and cost ticket 002 a build
cycle to discover. Ticket 002 moved `motion_engine.h` into `src/motion/` and its
inherited `#include "core/diffdrive.h"` — correct while the file sat at `src/`
root — failed with `fatal error: core/diffdrive.h: No such file or directory`.
It needed `"../core/diffdrive.h"`.

**The unified rule, which predicts all three observed cases:**

> An `#include "..."` resolves **relative to the including file's own
> directory**. Plain C quote-include behaviour. The real PXT build passes no
> `-I src`, so there is no project-root base to qualify against.

| includer | target | correct form |
|---|---|---|
| `src/otos_port.h` | `src/core/diffdrive.h` | `"core/diffdrive.h"` |
| `src/core/diffdrive.cpp` | `src/core/diffdrive.h` | `"diffdrive.h"` |
| `src/motion/motion_engine.h` | `src/core/diffdrive.h` | `"../core/diffdrive.h"` |

This makes the proposed mechanical gate (option 2 above) both simpler and
stronger: for every `#include "X"` in a file at directory D, assert that
`(D / X)` resolves to a file that exists. One rule, no special cases, and it
catches all three failure modes without a compiler.
