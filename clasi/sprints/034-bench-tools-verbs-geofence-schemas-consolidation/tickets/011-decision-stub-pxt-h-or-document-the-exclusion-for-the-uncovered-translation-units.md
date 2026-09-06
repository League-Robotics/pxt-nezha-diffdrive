---
id: '011'
title: 'Decision: stub pxt.h or document the exclusion for the uncovered translation
  units'
status: done
use-cases:
- SUC-007
depends-on:
- '010'
github-issue: ''
issue: host-harness-gaps.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Decision: stub pxt.h or document the exclusion for the uncovered translation units

## Description

**This is a decision ticket, not an investigation.** Decide, record the
decision with its reasoning, and implement whichever branch you chose.
Both branches are acceptable outcomes; an open-ended exploration is not.

Some translation units under `src/` are compiled by **nothing** on the
host, because they include `pxt.h` (directly or transitively via
`platform_ports.h`) and `pxt.h` is CODAL-bound. The review said seven;
**it is eight today** -- `src/comms/wifi_uart.cpp` landed with the WiFi
transport. Verified 2026-09-06 by grepping `#include "pxt.h"` across
`src/**/*.cpp`:

    src/shims.cpp
    src/platform/otos_port.cpp
    src/platform/nezha_port.cpp
    src/platform/vfp_guard.cpp
    src/comms/protocol.cpp
    src/comms/radio_transport.cpp
    src/comms/serial_transport.cpp
    src/comms/wifi_uart.cpp

**Re-derive this list yourself** rather than trusting the one above --
that is part of the ticket, and the count has already moved once.

The gap matters: sprint 027's single-serial-producer work landed in
`protocol.cpp`, and only the hex checkpoint gates it. `test_cxx11_syntax_gate.py`
covers a deliberate list of host-portable sources and dedicated
syntax-check TUs; `test_kernel_harness.py` compiles production sources
with **no** `-I` (matching PXT) while the C++11 gate passes `-I src`,
which the real build lacks -- a consistency nit the review recorded
separately.

## The decision, and the criteria to decide it by

**Branch A -- a stub `pxt.h`** that lets these eight compile at
`-std=c++11` as a syntax gate.
**Branch B -- a documented exclusion** in `tests/DESIGN.md` naming each
file, why it cannot be compiled on the host, and what *does* gate it.

Decide by these criteria, in this order:

1. **Would the stub prove anything the tree does not already prove?**
   `tests/host/test_include_paths_match_target.py` already covers every
   `#include` under `src/` **with no compiler**, including these
   pxt.h-bound files -- the review calls it "the right shape for the gap".
   If a stub only re-proves includes resolve, it adds nothing.
2. **Can the stub be honest?** `pxt.h` brings CODAL types, `uBit`, fibers
   and PXT's own macros. A stub that declares enough for these eight to
   *parse* will not model behaviour. If the stub must fake a type whose
   real definition affects whether the code is correct, the gate is
   green for the wrong reason.
3. **Maintenance cost.** A stub is a second definition of a vendored
   header. When CODAL or PXT moves, the stub drifts -- and a drifting
   stub fails *loudly for the wrong reason*, which is worse than a
   documented gap.
4. **What breaks if we do nothing?** Name it concretely: which
   already-shipped bug would a syntax gate on these eight have caught?

**The bar for Branch A is criterion 1.** If the honest answer is "it
proves the file parses, which `test_include_paths_match_target.py`
plus the hex checkpoint already cover between them", choose Branch B.
The sprint's Design Rationale 7 states the position: a stub that
compiles but models nothing produces the worst available outcome, a
green gate that proves less than what exists.

**Branch B is a legitimate result and must not be treated as a
failure to deliver.** A documented, specific, current exclusion is a
real artifact.

## Acceptance Criteria

- [x] The current list of pxt.h-bound, host-uncompiled `.cpp` files is
      re-derived from the tree and recorded (not copied from the issue).
- [x] A decision is recorded against all four criteria above, with the
      answer to criterion 4 stated concretely.
- [x] **If Branch A**: the stub exists, the eight compile in the C++11
      gate, and the stub's own header comment states exactly what the
      gate does and does not prove -- so no future reader mistakes it for
      behavioural coverage. *(N/A -- Branch B chosen.)*
- [x] **If Branch B**: `tests/DESIGN.md` gains a section naming each
      file, the reason it cannot be host-compiled, and what gates it
      instead (`test_include_paths_match_target.py`, the hex checkpoint,
      `test_cxx11_syntax_gate.py`'s deliberate list). It must be
      specific enough that adding a ninth such file is noticeably absent
      from it.
- [x] Either way, `tests/DESIGN.md` is updated -- Branch A still needs
      the "what this proves" note.
- [x] The `-I src` inconsistency between `test_cxx11_syntax_gate.py` and
      `compile_shared_lib()` is either fixed or recorded as a known,
      reasoned difference in the same place.
- [x] While in `test_cxx11_syntax_gate.py`, apply the review's
      comment-hygiene replacement #9 (the sprint-004 ticket history in
      its module docstring); the replacement text is supplied verbatim in
      the review.
- [x] `tests/host/test_wire_grammar.py`'s assert-less
      `test_kernel_harness_still_importable` gets an assertion or is
      deleted -- a vacuous test in the file that gates the wire grammar
      is exactly the wrong place for one.

## Implementation Plan

### `tests/DESIGN.md` is not in this sprint's design overlay

`seed_sprint_design_overlay` derives an overlay slug relative to the
nearest source root, so `tools/DESIGN.md` and `tests/DESIGN.md` both
derive `DESIGN.md` and collide; the overlay holds `tools/DESIGN.md`.
**Edit `tests/DESIGN.md` canonically anyway** -- that is where it
belongs. Flag in your ticket record that the team-lead must sync it by
hand at close, because the overlay will not carry it.

### Files

- `tests/DESIGN.md` (both branches).
- Branch A only: a stub header under `tests/host/`, and
  `tests/host/test_cxx11_syntax_gate.py`.
- `tests/host/test_wire_grammar.py`.

### Depends on

Ticket 010 -- which lands `tests/host/conftest.py` and touches the same
harness files.

## Testing

- **Existing tests to run**: `uv run pytest tests/host -q` (foreground,
  scoped).
- **New tests to write**: Branch A -- the eight files in the gate's
  compile list. Branch B -- a test that the documented exclusion list
  matches the tree, so a ninth pxt.h-bound `.cpp` fails here rather than
  being silently uncovered. **Branch B's test is the valuable half of
  Branch B**; do not skip it.
- **Verification command**: `uv run pytest tests/host -q`

## Decision record

**Branch B — a documented exclusion.** No stub `pxt.h` was written.

### The re-derived list

Derived 2026-09-06 from the tree by a transitive closure over
`#include "..."` under `src/`, resolving each include the way the real
PXT build does (relative to the including file's own directory, no
project-root `-I`), starting from every `src/**/*.cpp`. This is a
source reading, not a measurement. Eight files reach `pxt.h`; the
count and the membership match the issue's list, and the *reason* now
distinguishes direct from transitive:

| file | reaches pxt.h |
|---|---|
| `src/shims.cpp` | directly, and via `platform/{nezha_port,otos_port,platform_ports}.h` |
| `src/comms/protocol.cpp` | transitively, via `platform/platform_ports.h` |
| `src/comms/radio_transport.cpp` | directly |
| `src/comms/serial_transport.cpp` | directly |
| `src/comms/wifi_uart.cpp` | directly |
| `src/platform/nezha_port.cpp` | transitively, via `platform/nezha_port.h` |
| `src/platform/otos_port.cpp` | transitively, via `platform/otos_port.h` |
| `src/platform/vfp_guard.cpp` | directly |

The seven remaining `.cpp` under `src/` are clean: `comms/run_bridge.cpp`,
`comms/wifi_link.cpp`, `comms/wire_adapter.cpp`, `comms/wire_handler.cpp`,
`core/diffdrive.cpp`, `motion/motion_engine.cpp`, `motion/velocity_shaper.cpp`
— every one of them already in `test_cxx11_syntax_gate.py`'s compile list.

### The four criteria

**1. Would the stub prove anything the tree does not already prove? No.**
`test_include_paths_match_target.py` already covers every `#include`
under `src/`, these eight included, with no compiler. What a stub would
add is "this file parses against a *fake* `pxt.h`", which is a strictly
weaker claim than "this file compiles against the real one" — the claim
the hex checkpoint already makes. The residual signal a stub could
offer is a C++14+ construct in the project's own code inside these
eight, and that surface has been shrinking on purpose: sprint 033 alone
moved the RUN bridge (`comms/run_bridge.cpp`), the transport sink
(`comms/transport_sink.h`), the config field table (`comms/config_fields.h`),
`radioRxClassify()` (`comms/radio_transport.h`) and the odometry fold
(`motion/odometry.h`) out into host-portable seams that the C++11 gate
*does* compile. **This is the bar the ticket names, and it is not met.**

**2. Can the stub be honest? No, and criterion 4's own example shows
where it breaks.** `pxt.h` brings `uBit`, fibers, `NRF52Serial`,
`MicroBitRadio` and PXT's `//%` annotation machinery. A stub must
invent signatures for all of it, and a signature is exactly what the
one real defect in these eight turned on (below). `shims.cpp` is the
worst case: its 2067 lines are largely a PXT block surface that no C++
stub models at all.

**3. Maintenance cost.** A stub is a second definition of a vendored
header — `pxt_modules/core/pxt.h` plus its whole CODAL transitive set.
It drifts on every pxt-microbit or codal-microbit-v2 bump and then
fails loudly for the wrong reason, which is worse than a documented
gap because it costs a debugging session to discover it is not about
this project's code at all.

**4. What breaks if we do nothing? — concretely.** I searched the
sprint history for build breaks that landed in these eight. There are
two, and a `-std=c++11 -fsyntax-only` compile against a stub would have
caught **neither**:

- **`serial_transport.cpp:40`, sprint 004 ticket 007 Defect B.**
  `uBit.serial.setRxBufferSize(kRingBytes)` with `kRingBytes = 480`
  silently truncated to a `uint8_t` parameter. What caught it was the
  real build log's own `-Woverflow` plus reading codal-core's actual
  header. A stub has to invent that parameter's type: declare it `int`
  and the gate is green over the bug; declare it `uint8_t` and the gate
  only "catches" a fact it was already told. And the gate asserts on
  `returncode`, so a warning passes either way. This is criterion 2
  failing on a real, shipped defect rather than in the abstract.
- **`shims.cpp`, sprint 015 ticket 006.** `engineGoToR`'s five-argument
  `//%` shim crashed the PXT compiler with a deterministic, retry-surviving
  `TS9200`. That is PXT's annotation compiler, not the C++ front end;
  no stub `pxt.h` models it.

The honest answer to "what breaks if we do nothing" is therefore: the
hex checkpoint stays load-bearing for these eight, which it already is
and which both of the above were in fact caught by. The real risk —
untested *logic* hiding in a CODAL-bound TU — is addressed by
extraction, not by stubbing, and the exclusion table now records that
per file so the next reader reaches for extraction first.

### What was implemented

- `tests/DESIGN.md` — new section "Translation units nothing on the
  host compiles": a row per file naming what binds it to the target and
  what gates it instead, the two blanket gates
  (`test_include_paths_match_target.py`, the hex checkpoint), a "why no
  stub" paragraph, and a pointer to the guard test.
- `tests/host/test_pxt_bound_exclusion_is_current.py` (new, 12 tests) —
  Branch B's mandatory guard. Re-derives the closure from the tree and
  fails if the table disagrees in either direction; also asserts no
  file appears in both the table and the C++11 gate's compile list.
  Negative-checked by dropping a throwaway `src/comms/ninth_probe.cpp`
  containing `#include "pxt.h"` into the tree: the test failed with
  `['comms/ninth_probe.cpp'] reach pxt.h ... but DESIGN.md's table does
  not name them`. The probe file was removed; `git status src/` clean.
- `tests/host/DESIGN.md` — its "Not covered, by design (CODAL-bound)"
  prose now points at the canonical table instead of forking from it.

### Riders

- **The `-I src` inconsistency: FIXED, not recorded.** All seven
  production sources in the gate's list compile clean at
  `-std=c++11 -fsyntax-only` with no `-I` at all, so the gate now draws
  the same line `compile_shared_lib()` draws: production `src/` files
  get no `-I` (matching PXT's real resolution); only this directory's
  own `*_syntax_check.cpp` scaffolding gets `-I src`, which it needs to
  name a `src/` header at all. The reasoning is in the test function's
  docstring and the module docstring, at the site.
- **Comment hygiene #9: applied**, replacement text verbatim from
  `docs/code-review/2026-09-02/raw/tools-and-tests.md`, plus the
  still-load-bearing scope note (what qualifies for the list, the
  include policy, and the pointer to the exclusion section) that the
  one-liner does not carry.
- **`test_kernel_harness_still_importable`: given an assertion**, not
  deleted — the import is real (this file uses `compile_shared_lib()`),
  so the test now asserts that symbol exists and is callable, which is
  the only way the import can break the file.

### For the team-lead at close

`tests/DESIGN.md` is **not** in this sprint's design overlay — the
overlay slug collides with `tools/DESIGN.md` and the overlay holds
`tools/`. It was edited canonically per the ticket's Implementation
Plan; **sync it by hand at close, the overlay will not carry it.**
`tests/host/DESIGN.md` is in the same position.

### Verification

`uv run pytest tests/host -q` → 1165 passed in 28.26s.
`uv run pytest tests/tools -q` → 567 passed in 27.92s (ruff gate green).
