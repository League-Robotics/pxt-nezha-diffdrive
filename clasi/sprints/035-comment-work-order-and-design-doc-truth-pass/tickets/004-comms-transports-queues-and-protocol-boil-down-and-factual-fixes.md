---
id: "004"
title: "comms transports, queues and Protocol boil-down and factual fixes"
status: open
use-cases: [SUC-001]
depends-on: ["001"]
github-issue: ""
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# comms transports, queues and Protocol boil-down and factual fixes

## Description

Comment text only, in the transport / queue / `Protocol` half of
`src/comms/`. **No behaviour change.** `src/comms/protocol.cpp` carries
4 `//%` pragma lines — leave them byte-identical.

This is one of two `comms/` tickets, split so no two programmers edit
the same file. **Ticket 005 owns `wire_handler.{h,cpp}` and
`wire_adapter.{h,cpp}` — do not touch those four files here.**

### Files this ticket owns

- `src/comms/radio_transport.h` (ratio **5.29**, 370/70)
- `src/comms/serial_transport.h` (**5.17**, 93/18)
- `src/comms/protocol.h` (**4.43**, 434/98)
- `src/comms/protocol.cpp` (1.28), `src/comms/radio_transport.cpp`,
  `src/comms/serial_transport.cpp`
- `src/comms/run_queue.h` (0.64 but a 27-line "WHAT THIS REPLACES"
  header), `src/comms/emit_queue.h` (1.02, 37-line header)
- `src/comms/run_bridge.{h,cpp}` (**2.47**),
  `src/comms/transport_sink.h` (**2.25**),
  `src/comms/config_fields.h` (1.71)

### Rules of engagement (binding, every item)

As ticket 002 — re-anchor by quoted content never line number; a
replacement whose premise changed is a recorded no-op never forced;
`.claude/rules/measurement-citations.md` (a boil-down never strips the
artifact path out of a `MEASURED` claim);
`.claude/rules/no-units-in-identifiers.md` (this sprint renames
nothing; never delete a trailing `// [unit]`).

Sprints 033 and 034 rewrote large parts of these files. Verify every
anchor before editing; several annex rows were verified live at
planning time but at reduced scope.

### Boil-down items (comms annex —
`docs/code-review/2026-09-02/raw/comms.md`, "Comment boil-down list")

All twelve were verified **live**. Rows 3, 6, 8, 9 and 11 target
`wire_handler.*` and belong to **ticket 005** — this ticket takes rows
1, 2, 4, 5, 7 (partly), 10 and 12. Row 7 targets `wire_adapter.cpp`
(ticket 005). So this ticket's set is **1, 2, 4, 5, 10, 12**.

| annex # | anchor (quoted content) | notes |
|---|---|---|
| 1 | `protocol.cpp`'s identity-constants block, from `// ---- identity constants ---` through the `kProfile`/`kVersion` history and the tovez fleet-wide episode | LIVE. Use the annex's four-line replacement. **Keep** the point that `name` (silicon) is identity and `profile` is build provenance, and that they legitimately differ on a wrong-build board — that is a diagnostic a reader needs and `.claude/rules/`'s own `identity-comes-from-hardware-not-config` memory depends on it. Also boil `protocol.cpp`'s `emitLine` clip archaeology (`Sprint 008 ticket 002 (WIRE-05/R-21): this clip now names`) to one line — annex row 17 of the motion-and-kernel list covers the same block; do it once, here. |
| 2 | `radio_transport.h`'s name→channel derivation block, ending near `` (`tools/make_deploy.py`'s `derive_radio_from_name()` is the`` | LIVE, reduced — 034 already fixed the retired-channel claim in this file. **Keep the DO-NOT-REFORMAT regex warning verbatim**: `tools/make_deploy.py` matches this file's text with a regex to inject the per-robot channel, and reformatting it silently breaks every deploy. Replace only the surrounding rationale. |
| 4 | `serial_transport.h`'s `kRingBytes` block containing `kRingBytes (ticket 006; previously a flat 128 B tuned for v5's` | LIVE. Use the annex's replacement. Keep the `uint8_t` ceiling fact (255, and 480 silently truncating to 224) — that is a CODAL API hazard nothing else records. |
| 5 | `radio_transport.h`'s `kMaxPayloadBytes` block containing `kMaxPayloadBytes itself is declared PUBLIC, above (sprint 008` | LIVE. Annex replacement, **with the value corrected**: the constant is `240`, not the annex's implied 200-era text. See factual fix 4 below. |
| 10 | `run_queue.h`'s `// WHAT THIS REPLACES.` header and `emit_queue.h`'s equivalent | LIVE. Annex replacements. This also carries factual fixes 2 and 3 below — the same blocks contain both. |
| 12 | `protocol.h`'s four public-API doc blocks written as justification — `emitLine`, `kRunDedupeMs`, and the two around them | LIVE. Annex replacements. |

Additionally in scope for this ticket, not on any annex list but the
same defect class and high-ratio: `run_bridge.h` (2.47) and
`transport_sink.h` (2.25) are **new files from sprint 033** whose
headers already carry sprint-033 narration. Apply the guidelines'
write-time standard: keep the contract, the ownership rule and any
hazard; cut the narration. `config_fields.h` likewise.

### Factual fixes

1. **`protocol.h`'s v5-retirement paragraph.** The leading block's
   opening (near `"RUN:<name>[:<arg>...]" bridge (handleRun()/dispatchJob()/the`)
   still frames the cleartext RUN bridge in terms of the "v5 retirement"
   era. The operative fact — v6's `RUN` is `kUnknown`, which is why the
   cleartext bridge exists — is true; fold it into a three-line note and
   drop the era framing.

2. **`run_queue.h` says its consumer is a MessageBus listener.** The
   text reads `The consumer is a` / `MessageBus listener that receives an
   integer and reads the text back` / `by that integer; it never says
   "done".` There is no MessageBus: the consumer is `dispatchJob()` on
   the same fiber, via `RunBridge` (sprint 033). Rewrite to state what
   closes occupancy today. The *reason* a slot is held from `enqueue()`
   to `release()` is still worth one sentence — it is the invariant
   that stops a burst trampling a payload a handler has not read.

3. **`emit_queue.h` says the same thing** — `hands a MessageBus listener
   a slot number to read later`. Same fix.

4. **`run_queue.h` says the dedupe window is 3 s.** The text reads
   `The 3 s same-text suppression that sat` / `in front of it was a
   workaround for exactly this`. It is **400 ms** (`kRunDedupeMs`,
   `protocol.h`; `run_bridge.h`'s `kDedupe`). `src/DESIGN.md`'s copy of
   this error was already fixed — this is the surviving instance.

5. **`radio_transport.h`'s `kMaxPayloadBytes` is 240, not 200.** The
   constant reads `static constexpr size_t kMaxPayloadBytes = 240;`.
   While boiling row 5 down, make sure the surviving text states 240.
   (`src/DESIGN.md` still says "still 200" in one place and 240
   correctly in another — that contradiction is **ticket 008**'s.)

### Factual errors to record as no-ops (verified already resolved)

Name the sprint in the completion notes; do not re-introduce:

- `Protocol::formatDiag()` cited from `radio_transport.h` — **resolved
  (033)**; no occurrence anywhere in `src/`.
- The two-fiber / TS-fiber writer model in `serial_transport.h`,
  `radio_transport.h` and `protocol.h` — **resolved (033)**. Note that
  `protocol.h` does still contain `writes either transport, so two
  fibers can never race the same`, which is a **correct** statement of
  the single-writer invariant, not the retired claim. Leave it.
- `protocol.cpp`'s `(wifi-link.md:373)` citation — **resolved**; no
  occurrence.

## Acceptance Criteria

- [ ] Annex rows 1, 2, 4, 5, 10 and 12 are applied, re-anchored by
      quoted content; any judged a no-op is recorded with its reason.
- [ ] `radio_transport.h`'s DO-NOT-REFORMAT regex warning and the lines
      `tools/make_deploy.py` matches are byte-identical to before.
- [ ] `run_queue.h` and `emit_queue.h` no longer mention MessageBus.
- [ ] `run_queue.h` states 400 ms, not 3 s.
- [ ] The surviving `kMaxPayloadBytes` text states 240.
- [ ] `protocol.h`'s leading block no longer frames the RUN bridge in
      v5-retirement terms.
- [ ] The three resolved factual errors are recorded as no-ops naming
      sprint 033.
- [ ] `protocol.cpp`'s 4 `//%` pragma lines are byte-identical.
- [ ] Ratios recorded in the completion notes for `radio_transport.h`,
      `serial_transport.h` and `protocol.h`, all materially below their
      5.29 / 5.17 / 4.43 baselines.
- [ ] No `wire_handler.*` or `wire_adapter.*` file is modified (ticket
      005 owns them).
- [ ] No trailing `// [unit]` deleted, no identifier renamed, no line
      of code changed.

## Testing

Foreground only.

- **Existing tests to run**:

      uv run pytest tests/host/test_archaeology_marker_budget.py \
                    tests/host/test_wire_constants_drift.py \
                    tests/host/test_cxx11_syntax_gate.py -q
      uv run pytest tests/host/ -k source_pin -q
      uv run pytest tests/host/ -q

  `test_wire_constants_drift.py` is the one to watch: it reads
  constants and their surrounding text out of these exact files.
  `test_protocol_stack_canary_source_pin.py` and
  `test_boot_banner_source_pin.py` also match text here.

- **New tests to write**: none.
- **Verification command**: `uv run pytest tests/host/ -q`

## Notes for the implementer

- Replacement text source:
  `docs/code-review/2026-09-02/raw/comms.md`, "Comment boil-down list"
  rows 1, 2, 4, 5, 10, 12; and its "CM-10" table.
- Read `sprint.md`'s "Verification pass" section first.
- Do not run the full repo suite.
