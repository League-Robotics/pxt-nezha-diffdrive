---
id: 009
title: Harness include paths match the real build
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: host-harness-masks-include-path-errors.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Harness include paths match the real build

## Description

**This is the sprint's only ticket carrying real risk.** Every other ticket
in this sprint is docs, config, or a purely additive test. This one changes
how the host harness compiles code, and doing so can surface latent
include errors across the whole tree that the harness has been hiding.
That's the point -- not a side effect to avoid -- but it's why this is its
own isolated ticket rather than folded into anything else, so any fallout
doesn't entangle the doc-focused tickets.

`tests/host/test_kernel_harness.py`'s `compile_shared_lib()` defaults
`include_dirs = [_SRC_DIR, _TEST_DIR]` -- i.e. it passes `-I src` (plus the
test dir). The real PXT build passes **no** `-I src`; it resolves every
`#include "..."` relative to the including file's own directory (plain C
quote-include search, since PXT stages files at their `pxt.json`-relative
path). With `-I src` on the compiler command line, both a bare-name include
and a `src`-qualified include resolve, so **the host harness is more
permissive than the real target** -- a wrong include passes 597 host tests
and then fails only in the remote cloud C++ compiler.

Sprint 013 ticket 001/002 worked out and corrected-in-place the exact rule,
after getting it wrong once:

> An `#include "..."` resolves **relative to the including file's own
> directory**. The real PXT build passes no `-I src`, so there is no
> project-root base to qualify against.

| includer | target | correct form |
|---|---|---|
| `src/otos_port.h` (root-level) | `src/core/diffdrive.h` | `"core/diffdrive.h"` |
| `src/core/diffdrive.cpp` | `src/core/diffdrive.h` | `"diffdrive.h"` |
| `src/motion/motion_engine.h` | `src/core/diffdrive.h` | `"../core/diffdrive.h"` |

This is the same class of defect as the already-fixed `-std=c++20` vs.
`-std=c++11` divergence (`tests/host/test_cxx11_syntax_gate.py` is the
precedent for closing exactly this shape of harness/target gap
mechanically).

## What to change -- pick one, informed by what you find

The source issue lists two options, in order of preference; this ticket
should default to attempting option 1 first and fall back to option 2 if
option 1 turns out to be too invasive to land safely in one ticket:

1. **Drop `-I src` from the host harness** and compile with the include
   base the real build uses (no project-root `-I`), so host compilation
   exercises the true include graph. Most faithful, but likely requires
   restructuring how `compile_shared_lib()` and its various shim `.cpp`
   files pass source paths -- since shim files under `tests/host/` may
   themselves rely on `-I src`-style resolution to reach `src/` headers,
   this may need per-file working-directory tricks or explicit relative
   includes in the shims too. Read `test_kernel_harness.py`'s
   `compile_shared_lib()` and every shim `.cpp`/`.h` under `tests/host/`
   before starting, since the caveat in the source issue is explicit: "the
   exact harness invocation should be re-read... before implementing, and
   whether every host test module passes the flag has not been checked."
2. **Add a mechanical include-shape gate** instead of (or in addition to)
   changing the harness: a new host test, in the `test_cxx11_syntax_gate.py`
   spirit, that parses every `#include "..."` under `src/` and asserts,
   for a file at directory `D` including `"X"`, that `(D / X)` resolves to
   a file that exists on disk. This is cheap (no compiler), deterministic,
   and catches all three failure modes in the table above with one rule.

Given the fallout risk, **do option 2 regardless of whether option 1 is
also attempted** -- it's the low-risk, high-value guard, and it's valuable
on its own even if dropping `-I src` from the harness proper turns out to
be too large a change for this ticket. If `-I src` removal (option 1)
surfaces real include errors in `src/` (i.e. the harness was masking an
actual latent defect, not just being more permissive in a way that
happened not to matter), fix those includes to the correct relative form --
that's a comment/include-directive fix, not a behavior change, and stays
within this sprint's "no firmware behaviour changes" boundary as long as
only the `#include` line's spelling changes and not what gets included.

## Acceptance Criteria

- [ ] A new host test (option 2) mechanically verifies every `#include
      "..."` under `src/` resolves relative to its own including file's
      directory, matching the real PXT build's resolution rule.
- [ ] Either: (a) `-I src` is dropped from the harness and host compilation
      now matches the real build's include resolution, with any surfaced
      include errors fixed; or (b) `-I src` remains for now (if removal
      proved too invasive for one ticket) but the new mechanical gate from
      option 2 is in place and passing, and the ticket's completion notes
      explain why option 1 was deferred.
- [ ] If any `#include` directive is corrected as a result of this ticket,
      only the include path's spelling changes -- no included content,
      logic, or behavior changes.
- [ ] The full host suite (`uv run pytest tests/host/`) still passes.
- [ ] No firmware behavior changes.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` in full -- this
  ticket's whole purpose is to test whether the compile step itself still
  works correctly, so every existing host test is the regression check.
- **New tests to write**: the include-shape gate test (option 2), e.g.
  `tests/host/test_include_paths_match_target.py`.
- **Verification command**: `uv run pytest tests/host/` (full run, not
  scoped -- this ticket's blast radius is the whole compile harness).
