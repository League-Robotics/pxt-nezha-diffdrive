---
id: '005'
title: comms wire layer boil-down and factual fixes
status: done
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

- [x] Annex rows 3, 6, 7, 8, 9 and 11 are applied, re-anchored by
      quoted content; any judged a no-op is recorded with its reason.
- [x] `wire_handler.h` no longer both declares `gapOutstanding_` and
      says it was deleted; the surviving comment states what the field
      does today. The field itself is unchanged.
- [x] `wire_handler.cpp` no longer says `kVersion` is `"1.0.10"` or
      that it is drift-tested against `pxt.json`; the replacement
      matches what `test_wire_constants_drift.py` actually asserts.
- [x] `wire_adapter.h` no longer mentions MessageBus or `runSlots_`.
- [x] The mechanical marker pass has run across all four files; the
      before/after marker count for each is in the completion notes.
- [x] Ratios for `wire_adapter.h` and `wire_handler.h` recorded, both
      materially below their 5.46 / 2.64 baselines.
- [x] No file owned by ticket 004 is modified.
- [x] Every surviving `MEASURED` claim names board, date and artifact
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

## Completion notes

Comment text only, in the four files this ticket owns. **No line of code
changed.**

### Comment-only proof (mechanical)

- `git diff -U0` over the four files yields **0** non-blank diff lines
  that are not `//` comment lines -- so no `/* */` interior was touched
  either, and none needed accounting for.
- Code-line counts (counting rule per
  `tests/host/test_archaeology_marker_budget.py`) are unchanged in every
  file: 220 / 834 / 70 / 397.
- Stronger check: with blank and `//` lines stripped, each file's
  remaining text is **byte-identical** to its `HEAD` version. That also
  settles the two standing prohibitions -- no identifier was renamed and
  no trailing `// [unit]` comment was deleted (they sit on code lines:
  12 / 0 / 3 / 17, unchanged).
- `MEASURED` claim counts unchanged (1 / 3 / 0 / 0); no artifact path was
  stripped from any of them.
- No file owned by ticket 004 was modified. `git status` shows exactly
  `src/comms/wire_{handler,adapter}.{h,cpp}`.

### Ratios and marker counts

| file | ratio before | ratio after | markers before | markers after |
|---|---|---|---|---|
| `comms/wire_adapter.h` | 5.46 (382/70) | **3.74** (262/70) | 33 | 6 |
| `comms/wire_handler.h` | 2.64 (580/220) | **2.07** (455/220) | 48 | 22 |
| `comms/wire_adapter.cpp` | 1.31 (522/397) | 1.19 (474/397) | 49 | 11 |
| `comms/wire_handler.cpp` | 0.86 (717/834) | 0.68 (565/834) | 43 | 24 |

Markers across the four files: **173 -> 63**. The repo-wide `src/`
marker total (the number ticket 008's `_BUDGET` ratchets against) went
**292 -> 182** on this ticket alone. Every marker left in these four
files is a live spec citation (`protocol.md`, `motion-api.md`,
`src/DESIGN.md`, `SUC-003`); every "which sprint added this" marker is
gone.

### Annex items -- all six APPLIED, no no-ops

- **Row 3** (three dispatch essays with quoted dialogue). One block at
  the query-verb section now carries the whole rule: sequenced iff
  position-dependent, ID/VER/STATUS answer session constants, `GET`
  stays sequenced *because `SET` orders it* (with the `SET kp 500 #7` /
  `GET kp #8` example kept). The missing-id and `#0` branches keep short
  comments stating the operative wire contract -- a recognised verb with
  a missing or `#0` id gets `nack <expectedNext_>` and is never answered
  with silence; an unrecognised verb stays silent on a shared channel;
  neither touches the sequence or sets `gapOutstanding_`. That is the
  rule `.claude/rules/playfield-testing.md` depends on, still stated.
  `test_wire_constants_drift.py` parses this region: the
  `everything else is on the sequenced plane` marker comment and the
  seven `strcmp(verb, "X")` early returns above it are untouched.
- **Row 6** (`kMaxMotionTimeout`, `kGetValueCeiling`). Both layering
  essays boiled to the annex's one-liners plus one sentence of the
  sibling-not-reuse reason. Both numeric reasons kept verbatim in
  substance: 2^31-1 is the signed-difference half-range so `now+timeout`
  cannot wrap past `now`; 1e6 keeps `magnitude * 1e6` (== 1e12) exactly
  representable in `double` (2^53). `formatConfigValue()`'s echo of the
  same argument was trimmed to match.
- **Row 7** (`onEstop()`'s three numbered hazards). Replaced. The
  ordering invariant survives explicitly: commit `kEstop`
  unconditionally, because the estopped diag flag is not published until
  the next `step()` and `estopAll()` has already ended the engine move,
  so `resolvePendingReason()` would misread it as `kStop`; clear
  `motionObligationActive_` **after** that commit.
- **Row 8** (buffer sizing). The ticket's anchor
  (`Buffer bumped 96 -> 128 and re-verified against the worst case,`) is
  `execId()`'s block and the annex's replacement text (`"status " + 8
  bools + ...`) is `execStatus()`'s, so **both** were done in one pass:
  `execStatus()` now states the ~160 B worst case and why 200 leaves
  margin; `execId()` states the ~94 B worst case with its per-field
  budgets, and carries factual fix 2.
- **Row 9** (`Column`/`Snapshot` C++11 essay). Replaced with the annex
  sentence, plus one clause for why the NSDMIs stay (dropping them would
  leave `Column columns_[...]` indeterminate) and one for why `Snapshot`
  needs no constructor (nothing brace-initializes one).
  `test_cxx11_syntax_gate.py` still passes.
- **Row 11** (`emitReminderIfStalled()` + `gapOutstanding_`). Replaced.
  Reply predicate only, never periodic, an idle link is silent, and
  S8.5's anti-beacon rule is untouched. Carries factual fix 1.

### Factual fix 1 -- `gapOutstanding_` is LIVE, not dead

The two comments asserting the field was deleted (`wire_handler.h`'s
file header and its own declaration block) are gone; both now describe
what it does. **The field is unchanged, and it is not dead code** -- no
follow-up issue is needed. What it actually does today:

- **Written true** at `dispatch()`'s numeric-gap branch
  (`id > expectedNext_`) and in `handleDecodeFailure()`.
- **Written false** on an accepted in-order line (right before
  `replyAck(id)`) and in `handleHello()`.
- **Read** in exactly one place, `emitReminderIfStalled()`, which is
  called at the end of PING / HELP / ID / VER / STATUS -- i.e. it gates
  whether an *unsequenced* verb's reply also carries
  `nack <expectedNext_>`.
- Deliberately NOT set by the missing-id or `#0` branches: those are
  malformed lines, not evidence that a numbered command was lost.

It cannot be derived from `expectedNext_` alone, which is why it exists:
that counter cannot tell "clean, waiting for #5" from "stalled,
discarded #6, still want #5".

### Factual fix 2 -- `kVersion`, and the 24-char budget

The old text ("`version` (kVersion) is currently "1.0.10" (6 chars),
drift-tested against pxt.json") was wrong in both halves and is gone.
The replacement states what
`tests/host/test_wire_constants_drift.py::test_k_version_is_the_uninjected_placeholder`
actually asserts: the checked-in literal in `protocol.cpp` must stay the
placeholder `"unbaked"`, injected at deploy by `tools/make_deploy.py`'s
`_inject_version()` from `pyproject.toml` -- that test explicitly
**replaces** `test_k_version_matches_pxt_json_version`, so `kVersion` is
asserted *not* to be pxt.json's extension semver.

**Budget verdict: 24 still holds, comfortably. Not changed** (that would
be a behaviour change). The injected form is `1.YYYYMMDD.n`, today
`1.20260906.2` -- **12 characters**, half the budget. It would take a
13-digit build ordinal `n` to reach 24. `execId()`'s worst case is
restated as ~94 B against a 128 B buffer.

### Factual fix 3 -- the RUN bridge

`wire_adapter.h`'s `onRun()` comment no longer mentions MessageBus or
`runSlots_`. It now names what is actually there: protocol.cpp's
cleartext `RUN:` bridge is `RunBridge` plus `dispatchJob()`, running the
job on the protocol fiber itself. Verified against `protocol.h`
(`RunBridge runBridge_;`, `void dispatchJob();`) and `protocol.cpp`
(`runBridge_.offer(...)`, `dispatchJob()`) -- there is no `runSlots_`
anywhere in the tree and no MessageBus in this path.

### Incidental correction

`wire_handler.h`'s `emitTelemetry()` doc said it emits "THREE separate
Sink::write() calls" and then listed two (the third was the ack
piggyback S8.5 deleted). Corrected to TWO while that block was being
boiled down.

### Finding for triage (not fixed here -- out of this ticket's scope)

Two pre-existing `MEASURED`/`Measured` claims in `wire_handler.cpp`
(`emitHelp()`'s "MEASURED 2026-08-27, tovez over the
torture->channel-3 relay" and `execGet()`'s "Measured on this rig
2026-08-27") name a board and a date but **no artifact path**, which
`.claude/rules/measurement-citations.md` requires. They also disagree
with each other and with `emitReminderIfStalled()`'s figure on the same
measurement: 66-75% vs 66-83% per-line delivery. Neither was introduced
by this ticket and no path was stripped from either; inventing one is
forbidden, so both were left exactly as found. Worth an issue if the
capture can be located.

### Tests (foreground, this turn)

    uv run pytest tests/host/test_wire_constants_drift.py \
                  tests/host/test_archaeology_marker_budget.py \
                  tests/host/test_cxx11_syntax_gate.py -q
    58 passed in 1.01s

    uv run pytest tests/host/ -k source_pin -q
    85 passed, 1082 deselected in 0.27s

    uv run pytest tests/host/ -q
    1167 passed in 28.70s

The host suite compiles `wire_handler.cpp` and `wire_adapter.cpp`
through the harness shims, so it is a real compile check for these
files, not just a text check.
