---
id: '001'
title: 'RadioTransport RX capacity: enlarge rxLine_ to 240 bytes and reject (not truncate)
  an over-length fragment'
status: open
use-cases: ['SUC-001']
depends-on: []
github-issue: ''
issue: radio-rx-capacity-fragmentation.md
completes_issue: false  # TX half + the three-numbers drift test land in
  # ticket 002 -- that is the ticket that fully closes this issue.
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# RadioTransport RX capacity: enlarge rxLine_ to 240 bytes and reject (not truncate) an over-length fragment

## Description

`RadioTransport::rxLine_` (`src/radio_transport.h:185`) is a 64-byte
buffer with no relationship to the wire grammar's own 240-byte line
ceiling (`Wire::WireHandler::kMaxLineBytes`) — it is an arbitrary
implementation choice, not a physical or protocol limit.
`RadioTransport::onDatagram()` (`src/radio_transport.cpp:50-65`)
currently does this when a single-fragment (`START|END`) datagram's
declared `LEN` exceeds `sizeof(rxLine_)`:

```cpp
if (len > sizeof(rxLine_)) len = sizeof(rxLine_);
```

...silently truncating to whatever fits and still delivering it as if it
were the complete line. Downstream, `WireHandler::feed()` then parses
that truncated prefix as a legal (but different, shorter) command and
executes it — the dangerous half of
`radio-rx-capacity-fragmentation.md`.

**Key finding from sprint planning (see sprint.md's Architecture, Step 6
Design Rationale): no multi-fragment reassembly is needed.** This
project's own `pxt.json` sets `microbit_radio_max_packet_size: 250`, and
`radio_transport.h`'s own header comment already states that "with the
250-byte fleet packet size every relay-forwarded command line qualifies"
as a single fragment. The physical single-fragment payload capacity
(≈247 bytes, `kMtu = MICROBIT_RADIO_MAX_PACKET_SIZE - kFrameHeaderBytes`)
already exceeds the wire grammar's 240-byte line cap. `onDatagram()`
already only accepts a complete `START|END` single-fragment message —
the only defect is that its own receive buffer is smaller than the wire
ceiling it should be able to carry whole.

**The fix:**

1. Enlarge `rxLine_` from `[64]` to `[240]` (name the bound off
   `Wire::WireHandler::kMaxLineBytes` if a host-portable way to reference
   it exists without introducing a new dependency edge from
   `radio_transport.h` onto `wire_handler.h` — the layering table in
   `src/DESIGN.md` §1 places Transports below Wire grammar, so
   `radio_transport.h` must not `#include "wire_handler.h"`; a local
   `constexpr size_t kMaxLineBytes = 240;` with a comment noting the two
   must be kept equal (see ticket 002's drift test) is the layering-safe
   choice, matching how `SerialTransport::kMaxLineBytes` already exists
   as its own independent constant of the same value for the same
   layering reason).
2. Change `onDatagram()`'s truncate to a reject: when the declared `LEN`
   exceeds the (now 240-byte) buffer capacity, drop the frame entirely
   — do not set `rxReady_`, do not copy any prefix — exactly like an
   already-dropped MORE-flagged fragment just above it in the same
   function. Count the drop on a new diagnostic counter,
   `rxOversizeDropped_`, alongside the existing `rxFrames_`/
   `rxAccepted_` (declared in `radio_transport.h`, incremented in
   `radio_transport.cpp`).
3. Factor the accept/reject decision itself — given a fragment's
   declared length and the buffer's capacity — into a small, pure,
   `inline` free function (or `static` method) living in
   `radio_transport.h` itself. The header already includes only
   `<cstddef>`/`<cstdint>` (host-portable, per this sprint's own
   Requirements), so this needs no new file the way
   `heading_wrap.h`/`encoder_glitch_armor.h` did in sprint 006 — a host
   test can `#include "radio_transport.h"` directly and call the
   function, without linking `radio_transport.cpp` (which still requires
   `pxt.h`) at all.

## Acceptance Criteria

- [ ] `rxLine_` is 240 bytes; the accept/reject predicate is a pure,
      host-portable function declared and defined in `radio_transport.h`
      with no CODAL dependency.
- [ ] `onDatagram()` rejects (drops, does not truncate-and-accept) any
      single-fragment datagram whose declared `LEN` exceeds the buffer
      capacity, and increments `rxOversizeDropped_` when it does.
- [ ] A ≤240-byte single-fragment datagram is still accepted and
      delivered whole, unchanged from today's behavior for in-range
      input.
- [ ] A new host test file `#include`s `radio_transport.h` directly (no
      link against `radio_transport.cpp`) and exercises the predicate at
      the boundary values: 0, 1, 240, 241, and the ~247-byte physical
      MTU ceiling.
- [ ] No change to `radio_transport.cpp`'s MORE-flagged-fragment drop
      path or any other existing behavior.

## Implementation Plan

**Approach.** Minimal, additive change confined to
`src/radio_transport.h`/`.cpp`. No new module, no new cross-module
dependency (per sprint.md's Architecture, Step 4) — this ticket only
resizes an existing buffer and tightens an existing accept/reject
decision inside `RadioTransport`'s own boundary.

**Files to modify:**
- `src/radio_transport.h` — `rxLine_[64]` → `rxLine_[240]`; add the
  pure accept/reject predicate; add `rxOversizeDropped_` counter
  declaration (public, alongside `rxFrames_`/`rxAccepted_`, per this
  file's existing RX-diagnostics convention).
- `src/radio_transport.cpp` — `onDatagram()` calls the new predicate
  instead of its current inline truncate; increments the new counter on
  rejection.

**C++11 gate coverage.** `radio_transport.cpp` stays **out** of the
`-std=c++11` syntax gate (it includes `pxt.h`, per `src/DESIGN.md` §11's
four-file list: `diffdrive.cpp`, `motion_engine.cpp`, `wire_handler.cpp`,
`wire_adapter.cpp`). `radio_transport.h` is host-portable and needs no
gate registration to be host-testable (a host test can already
`#include` it directly at C++20) — registering it in the C++11 syntax
gate too, the way sprint 006 registered `heading_wrap.h` etc., is a
nice-to-have this ticket may do if low-cost, not a requirement.

**Testing plan.**
- New host test: constructs the predicate's boundary cases directly
  against the header.
- Existing suite: run the full `tests/host` suite to confirm no
  regression (this ticket touches no other file).
- Not host-testable, by construction: `onDatagram()`'s actual CODAL
  datagram-receive path (`radio_transport.cpp` requires `pxt.h`) — first
  exercised live at this sprint's bench check (sprint.md Success
  Criteria: "a real >64-byte v6 line sent over radio").

**Documentation updates.** None required beyond this ticket and the
sprint's own design overlay (`clasi/sprints/010-.../design/DESIGN.md`),
which already documents this decision.
