---
id: '011'
title: 'Decision: stub pxt.h or document the exclusion for the uncovered translation
  units'
status: in-progress
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

- [ ] The current list of pxt.h-bound, host-uncompiled `.cpp` files is
      re-derived from the tree and recorded (not copied from the issue).
- [ ] A decision is recorded against all four criteria above, with the
      answer to criterion 4 stated concretely.
- [ ] **If Branch A**: the stub exists, the eight compile in the C++11
      gate, and the stub's own header comment states exactly what the
      gate does and does not prove -- so no future reader mistakes it for
      behavioural coverage.
- [ ] **If Branch B**: `tests/DESIGN.md` gains a section naming each
      file, the reason it cannot be host-compiled, and what gates it
      instead (`test_include_paths_match_target.py`, the hex checkpoint,
      `test_cxx11_syntax_gate.py`'s deliberate list). It must be
      specific enough that adding a ninth such file is noticeably absent
      from it.
- [ ] Either way, `tests/DESIGN.md` is updated -- Branch A still needs
      the "what this proves" note.
- [ ] The `-I src` inconsistency between `test_cxx11_syntax_gate.py` and
      `compile_shared_lib()` is either fixed or recorded as a known,
      reasoned difference in the same place.
- [ ] While in `test_cxx11_syntax_gate.py`, apply the review's
      comment-hygiene replacement #9 (the sprint-004 ticket history in
      its module docstring); the replacement text is supplied verbatim in
      the review.
- [ ] `tests/host/test_wire_grammar.py`'s assert-less
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
