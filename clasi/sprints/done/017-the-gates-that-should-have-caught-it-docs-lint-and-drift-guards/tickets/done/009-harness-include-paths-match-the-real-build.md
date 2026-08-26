---
id: 009
title: Harness include paths match the real build
status: done
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

- [x] A new host test (option 2) mechanically verifies every `#include
      "..."` under `src/` resolves relative to its own including file's
      directory, matching the real PXT build's resolution rule.
- [x] Either: (a) `-I src` is dropped from the harness and host compilation
      now matches the real build's include resolution, with any surfaced
      include errors fixed; or (b) `-I src` remains for now (if removal
      proved too invasive for one ticket) but the new mechanical gate from
      option 2 is in place and passing, and the ticket's completion notes
      explain why option 1 was deferred.
- [x] If any `#include` directive is corrected as a result of this ticket,
      only the include path's spelling changes -- no included content,
      logic, or behavior changes.
- [x] The full host suite (`uv run pytest tests/host/`) still passes.
- [x] No firmware behavior changes.

## Completion notes

Did **both** option 1 and option 2, per the ticket's "do option 2
regardless" instruction, and option 1 turned out not to require any
fallback: `tests/host/test_kernel_harness.py`'s `compile_shared_lib()`
now compiles each source to its own object file with `-c` instead of one
combined multi-file command line. A production source under `src/` is
compiled with **no `-I` at all** (matching the real PXT build exactly);
a `tests/host/` shim/test source still gets `include_dirs` (`-I src -I
tests/host`), since that scaffolding legitimately needs a project-root
path into `src/` and is never part of a real build. The object files are
then linked into the same `.so` as before -- `compile_shared_lib()`'s
signature and every caller are unchanged.

Manually verified the drop is not a no-op before trusting the green
suite: copied `diffdrive.h`/`.cpp` to a scratch directory, rewrote the
same-directory sibling include as the wrong qualified form
(`#include "core/diffdrive.h"` instead of `#include "diffdrive.h"`), and
confirmed (a) the OLD single-command-with-`-I src` shape still compiles
it (proving the old harness really did mask this), and (b) the NEW
no-`-I` per-file shape fails with `fatal error: 'core/diffdrive.h' file
not found` -- the exact real-build failure this ticket exists to
surface.

No `#include` line anywhere under `src/` needed correcting: sprint 013
tickets 001/002 already left every include in the includer-relative form
the CORRECTED rule requires, so dropping `-I src` from the production
compiles surfaced zero latent defects. `uv run pytest tests/host/` --
501 passed (up from the pre-ticket count by the one new gate file's 30
tests: 29 parametrized include-shape cases + 1 "at least one case
collected" guard).

The new gate, `tests/host/test_include_paths_match_target.py`, is a pure
filesystem check (no compiler) that walks every `.c/.cc/.cpp/.cxx/.h/
.hh/.hpp` file under `src/`, parses every `#include "..."` directive
line (a real directive only -- `^\s*#include\s+"..."`, so it does not
mistake `src/comms/radio_transport.h`'s commented-out `// #include
"wire_handler.h" (...)` for a live directive), and asserts
`(includer.parent / included).is_file()`. It deliberately exempts
`pxt.h`: that header ships with the `core` dependency declared in
`pxt.json` (`pxt_modules/core/pxt.h`) and is resolved through that
dependency's own include path in a real build -- a genuine, separate
mechanism from the project-root `-I` this ticket is about, and the same
exemption `test_cxx11_syntax_gate.py` already documents for the same
files. This gate covers every include under `src/`, including the
pxt.h-bound production files (`protocol.cpp`, `radio_transport.cpp`,
`serial_transport.cpp`, `nezha_port.{h,cpp}`, `otos_port.{h,cpp}`,
`shims.cpp`) that no compiled host test reaches at all -- coverage
`compile_shared_lib()` alone cannot provide.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` in full -- this
  ticket's whole purpose is to test whether the compile step itself still
  works correctly, so every existing host test is the regression check.
- **New tests to write**: the include-shape gate test (option 2), e.g.
  `tests/host/test_include_paths_match_target.py`.
- **Verification command**: `uv run pytest tests/host/` (full run, not
  scoped -- this ticket's blast radius is the whole compile harness).
