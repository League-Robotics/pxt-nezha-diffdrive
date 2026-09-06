---
id: '005'
title: comms wire layer boil-down and factual fixes
status: in-progress
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# comms wire layer boil-down and factual fixes

## Description

Comment text only, in the wire-handler / wire-adapter half of
`src/comms/`. **No behaviour change.**

Second of two `comms/` tickets. **Ticket 004 owns the transports,
queues and `Protocol` — do not touch `radio_transport.*`,
`serial_transport.*`, `protocol.*`, `run_queue.h`, `emit_queue.h`,
`run_bridge.*`, `transport_sink.h` or `config_fields.h` here.**

### Files this ticket owns

- `src/comms/wire_adapter.h` (ratio **5.46**, 382/70 — the highest in
  the tree)
- `src/comms/wire_handler.h` (**2.64**, 580/220)
- `src/comms/wire_adapter.cpp` (1.31, 522/397 — and 49 archaeology
  markers, the most of any file)
- `src/comms/wire_handler.cpp` (0.86, 717/834 — 43 markers)

### Rules of engagement (binding, every item)

As ticket 002 — re-anchor by quoted content never line number; a
replacement whose premise changed is a recorded no-op never forced;
`.claude/rules/measurement-citations.md`;
`.claude/rules/no-units-in-identifiers.md` (this sprint renames
nothing; never delete a trailing `// [unit]`).

### Boil-down items (comms annex, rows 3, 6, 7, 8, 9, 11)

All verified **live** at planning time.

| annex # | anchor (quoted content) | notes |
|---|---|---|
| 3 | `wire_handler.cpp`'s three dispatch essays — why `ID`/`VER`/`STATUS` are unsequenced, why a missing id nacks, why `#0` nacks (they contain quoted stakeholder dialogue) | LIVE. One block replaces three; annex supplies the text. **Keep** the operative rule verbatim in substance: unsequenced iff position-independent; `GET` stays sequenced because `SET` orders it; a recognised verb with a missing or `#0` id gets `nack <expectedNext_>` so the operator is never answered with silence; unknown verbs stay silent on a shared channel. That rule is the wire contract and `.claude/rules/playfield-testing.md` depends on it. |
| 6 | the `kMaxMotionTimeoutMs` and `kGetValueCeiling` "sibling not reuse" layering essays — anchor on `(\`kGetValueCeiling * kDivisor\` == 1e12) comfortably inside \`double\`'s` and `kGetValueCeiling's own comment above for why that pairing (a bounded` | LIVE. Annex supplies one line each. Keep the numeric reasons (the signed-difference half-range; exact representability in `double`). |
| 7 | `wire_adapter.cpp`'s `onEstop()` block with its three numbered hazards — anchor on `return (void, per wire_handler.h's own Adapter::onEstop() contract)` and `see onEstop()'s identical comment above.` | LIVE. Annex replacement. Keep the ordering invariant (commit `kEstop` unconditionally, because the estopped diag flag is not published until the next `step()`), which is the whole point. |
| 8 | `wire_handler.cpp`'s `execStatus()` buffer-sizing block — two rounds of worst-case width arithmetic, anchor on `Buffer bumped 96 -> 128 and re-verified against the worst case,` | LIVE. Annex replacement. **This block also carries factual fix 2 below** — do both in one edit. |
| 9 | `wire_handler.h`'s `Column`/`Snapshot` C++11 essay — anchor on `the NSDMIs (dropping them would leave every default-constructed` and `Shares Column's exact NSDMI shape immediately above, and is therefore` | LIVE. Annex replacement (one sentence about why the explicit constructor exists under `-std=c++11`). |
| 11 | `wire_handler.cpp`'s `emitReminderIfStalled()` block and `wire_handler.h`'s `gapOutstanding_` block | LIVE. Annex replacement — reply predicate only, never periodic, an idle link is silent. **This block also carries factual fix 1 below**, which is the more important half. |

Additionally: `wire_adapter.cpp` holds **49** archaeology markers and
`wire_handler.h` **48**, the two largest concentrations in the tree
(`grep -cE 'sprint [0-9]{3}|ticket [0-9]{3}|WIRE-[0-9]|R-[0-9]{2}'`).
The comms annex flags this as "worth a mechanical pass, not
individually listed". Do that pass across these four files: a marker
that is a live spec citation (`motion-api.md §3.6`) stays; a marker
that narrates when a change landed goes into `git log`, where it
already is. Ticket 008 lowers `_BUDGET` from 388 to whatever this pass
plus tickets 002-004 and 006 achieve, so the number you leave behind
matters.

### Factual fixes

1. **`wire_handler.h` contradicts itself about `gapOutstanding_` — the
   worst defect in this ticket.** Two comment blocks assert the field
   is gone:

       // gapOutstanding_ is GONE, 2026-08-26, S8.5: its only reader was the
       // gapOutstanding_ was DELETED 2026-08-26 (S8.5) along with the

   while the same file declares `bool gapOutstanding_ = false;` further
   down, and `wire_handler.cpp` calls `emitReminderIfStalled()`. A
   reader cannot tell which is true without reading the whole file.

   **Fix the comments, not the field.** Determine what
   `gapOutstanding_` actually does today by reading its writers and
   readers, and state that. Removing the field would be a behaviour
   change and is out of scope for this sprint — if you conclude the
   field is genuinely dead code, **do not delete it**: record the
   finding in the completion notes so it can be triaged as its own
   issue. (This defect was found during sprint-035 planning; it is not
   in the review's sixteen.)

2. **`wire_handler.cpp` misquotes `kVersion` and what the drift test
   asserts.** The text reads:

       // that. `version` (kVersion) is currently "1.0.10" (6 chars),
       // drift-tested against pxt.json; budgeted to 24.

   Both halves are wrong. `protocol.cpp` declares
   `constexpr const char* kVersion = "unbaked";` (injected at deploy by
   `tools/make_deploy.py`), and the drift test asserts it is **not**
   pxt.json's version — see
   `tests/host/test_wire_constants_drift.py`'s
   `test_k_version_is_the_uninjected_placeholder`. Read that test
   before writing the replacement and state what it actually asserts.

   The **budget arithmetic** around it (24 chars for `version`) is a
   separate question: check it against the injected form
   `1.YYYYMMDD.n` rather than against `"1.0.10"`, and say in the
   completion notes whether 24 still holds. Do not change the constant
   either way — that would be a behaviour change; report it.

3. **`wire_adapter.h` says the RUN bridge is a MessageBus bridge with
   `runSlots_`.** Anchor:

       // is protocol.cpp's own MessageBus RUN bridge (runSlots_/handleRun()),

   There is no MessageBus and no `runSlots_`: it is `runQueue_` plus
   `RunBridge`/`dispatchJob()` on the same fiber (sprint 033). Rewrite
   to state that. (`run_queue.h`'s and `emit_queue.h`'s copies of this
   error belong to **ticket 004**; `src/DESIGN.md`'s to **ticket 008**.
   Do not touch those files.)

## Acceptance Criteria

- [ ] Annex rows 3, 6, 7, 8, 9 and 11 are applied, re-anchored by
      quoted content; any judged a no-op is recorded with its reason.
- [ ] `wire_handler.h` no longer both declares `gapOutstanding_` and
      says it was deleted; the surviving comment states what the field
      does today. The field itself is unchanged.
- [ ] `wire_handler.cpp` no longer says `kVersion` is `"1.0.10"` or
      that it is drift-tested against `pxt.json`; the replacement
      matches what `test_wire_constants_drift.py` actually asserts.
- [ ] `wire_adapter.h` no longer mentions MessageBus or `runSlots_`.
- [ ] The mechanical marker pass has run across all four files; the
      before/after marker count for each is in the completion notes.
- [ ] Ratios for `wire_adapter.h` and `wire_handler.h` recorded, both
      materially below their 5.46 / 2.64 baselines.
- [ ] No file owned by ticket 004 is modified.
- [ ] Every surviving `MEASURED` claim names board, date and artifact
      path. No trailing `// [unit]` deleted, no identifier renamed, no
      line of code changed.

## Testing

Foreground only.

- **Existing tests to run**:

      uv run pytest tests/host/test_wire_constants_drift.py \
                    tests/host/test_archaeology_marker_budget.py \
                    tests/host/test_cxx11_syntax_gate.py -q
      uv run pytest tests/host/ -k source_pin -q
      uv run pytest tests/host/ -q

  `test_wire_constants_drift.py` is the primary gate for this ticket —
  factual fix 2 is directly about what it asserts. Read it before
  editing, not after it fails.

- **New tests to write**: none.
- **Verification command**: `uv run pytest tests/host/ -q`

## Notes for the implementer

- Replacement text source:
  `docs/code-review/2026-09-02/raw/comms.md`, "Comment boil-down list"
  rows 3, 6, 7, 8, 9, 11; and its "CM-10" table.
- Read `sprint.md`'s "Verification pass" section first — it records the
  `gapOutstanding_` contradiction as a finding of the planning pass,
  not of the review.
- Do not run the full repo suite.
