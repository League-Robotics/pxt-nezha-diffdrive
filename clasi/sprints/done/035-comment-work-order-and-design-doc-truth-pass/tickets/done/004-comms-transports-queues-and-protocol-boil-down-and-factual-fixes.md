---
id: '004'
title: comms transports, queues and Protocol boil-down and factual fixes
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

- [x] Annex rows 1, 2, 4, 5, 10 and 12 are applied, re-anchored by
      quoted content; any judged a no-op is recorded with its reason.
- [x] `radio_transport.h`'s DO-NOT-REFORMAT regex warning and the lines
      `tools/make_deploy.py` matches are byte-identical to before.
- [x] `run_queue.h` and `emit_queue.h` no longer mention MessageBus.
- [x] `run_queue.h` states 400 ms, not 3 s.
- [x] The surviving `kMaxPayloadBytes` text states 240.
- [x] `protocol.h`'s leading block no longer frames the RUN bridge in
      v5-retirement terms.
- [x] The three resolved factual errors are recorded as no-ops naming
      sprint 033.
- [x] `protocol.cpp`'s 4 `//%` pragma lines are byte-identical.
- [x] Ratios recorded in the completion notes for `radio_transport.h`,
      `serial_transport.h` and `protocol.h`, all materially below their
      5.29 / 5.17 / 4.43 baselines.
- [x] No `wire_handler.*` or `wire_adapter.*` file is modified (ticket
      005 owns them).
- [x] No trailing `// [unit]` deleted, no identifier renamed, no line
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

## Completion notes

Comment text only. **No line of code changed** in any file — proved
mechanically below. Sprints 033/034 had already moved several anchors,
so every item was re-anchored by quoted content and the replacement
checked against the code as it stands today; one annex row is recorded
as a no-op for that reason.

### Annex rows (comms list)

| row | anchor | outcome |
|---|---|---|
| 1 | `protocol.cpp`'s `// ---- identity constants ---` block | **APPLIED**, 58 -> 29 comment lines. Kept the load-bearing half: `name` (read from silicon at call time) is THE board identity, `profile` is build provenance, they legitimately differ on a wrong-build board and that disagreement IS the diagnostic. Kept the scratch-copy injection mechanism and why `kVersion` is the build version rather than pxt.json's extension semver. Dropped the tovez-fleet-wide narrative and the 2026-08-27 decision essay. **Also** boiled `emitLine`'s clip archaeology (motion-and-kernel annex row 17, same block class): 16 lines -> 3, and dropped its now-FALSE claim that `kMaxPayloadBytes` is "deliberately the TIGHTER of the two transports' caps" — the four caps have been equal at 240 since sprint 010. |
| 2 | `radio_transport.h`'s name->channel derivation block | **APPLIED at the reduced scope the ticket describes.** 57 lines of surrounding rationale -> 18. The DO-NOT-REFORMAT warning and the two declarations `tools/make_deploy.py` matches are **byte-identical** (verified, below). Kept: the constants are an un-baked placeholder, BOTH are deploy-injected from the per-robot JSON, and config beats the derivation because two boards can share a five-letter name and would otherwise derive one address. Dropped the base-5 arithmetic (`derive_radio_from_name()` is the implementation and cites the normative spec) and the stale "kGroup is currently 10 fleet-wide" paragraph, which contradicted the paragraph immediately above it. |
| 4 | `serial_transport.h`'s `kRingBytes` block | **APPLIED**, 30 -> 15. Kept every CODAL hazard: the `uint8_t` ceiling of 255, 480 silently truncating to 224 (below one line), the ~15 B of slack meaning two full lines can still overflow, and the brace-init that makes >255 a compile error. |
| 5 | `radio_transport.h`'s `kMaxPayloadBytes` | **APPLIED**, value stated as **240**. The declaration's doc block went 36 -> 18 lines, and the separate 6-line "declared PUBLIC, above (sprint 008 ticket 002)" note the ticket quotes as this row's anchor was deleted outright. **The annex's literal replacement text was NOT pasted**: `tests/host/test_wire_constants_drift.py::test_radio_transport_doc_comment_states_equality_not_tighter` requires the surviving comment to contain "equal" and forbids "tighter", and the annex's sentence contains neither word. The rewrite states the four-way equality explicitly. |
| 10 | `run_queue.h` and `emit_queue.h` "WHAT THIS REPLACES" headers | **APPLIED**, 27 -> 22 and 37 -> 24. Carries factual fixes 2, 3 and 4. |
| 12 | `protocol.h`'s four public-API doc blocks written as justification | **APPLIED to three of the four** — `emitLine()` (23 -> 15), `currentRunText()` (11 -> 7), `tryTakeMotionOwnership()`/`releaseBlockOwnership()` (35 -> 22). The fourth, **`kRunDedupeMs`, is a recorded NO-OP in this file**: sprint 033 moved that constant out of `protocol.h` into `run_bridge.h` as `RunBridge::kDedupe`, whose own comment already stated 400 ms and the reason. Boiled that comment at its new home instead (9 -> 7 lines) rather than forcing a replacement onto a block that no longer exists here. |

### The five factual fixes

1. **`protocol.h`'s v5-retirement framing** — fixed. The leading block's
   "One exception, preserved deliberately: the OLD cleartext ... bridge"
   paragraph is now a five-line note stating the operative fact: the
   cleartext `RUN:` carve-out exists because v6's own `RUN` verb
   (`WireAdapter::onRun()`) answers `kUnknown`. No era framing survives.
2. **`run_queue.h`'s MessageBus consumer** — fixed. It now says
   occupancy is closed by `RunBridge`, which stages a payload back out
   from `Protocol::dispatchJob()` on the protocol fiber, with
   `release()` happening BEFORE the TypeScript handler is called. The
   invariant the ticket asked to keep (a slot held from `enqueue()` to
   `release()` is what stops a burst trampling an unread payload) is
   the block's opening sentence.
3. **`emit_queue.h`'s MessageBus reference** — fixed (it was in the
   "WHY DRAIN, NOT RANDOM ACCESS" paragraph's aside about `RunQueue`).
   `grep -c MessageBus` is now 0 in both files.
4. **`run_queue.h`'s "3 s" dedupe window** — fixed to **400 ms**, named
   as `RunBridge::kDedupe`, and stated as solving a DIFFERENT problem
   (duplicate execution of a retransmit) rather than as a substitute
   for occupancy.
5. **`kMaxPayloadBytes` is 240** — the surviving text states 240 and the
   four-way equality. Nothing in `radio_transport.h` says 200 any more.

### Factual errors recorded as NO-OPS (verified already resolved)

- **`Protocol::formatDiag()`** cited from `radio_transport.h` —
  **resolved by sprint 033**. `grep -rn formatDiag src/` returns
  nothing. Not reintroduced.
- **The two-fiber / TS-fiber writer model** in `serial_transport.h`,
  `radio_transport.h` and `protocol.h` — **resolved by sprint 033**. No
  "two fibers call this" / "TS fiber" writer claim survives in
  `src/comms/`. `protocol.h`'s "two fibers can never race the same
  underlying serial write" is the CORRECT single-writer invariant, not
  the retired claim, and was preserved through the `emitLine()` rewrite
  (same claim, shorter wording).
- **`protocol.cpp`'s `(wifi-link.md:373)` citation** — **resolved**. No
  occurrence in `src/comms/`.

### Further factual errors of the same class, found while re-anchoring

Not on the ticket's list; all comment-only, all in files this ticket
owns:

- `protocol.h`'s `enableRadio()` said the deploy injects "the per-robot
  channel ... **and group 10**". Both are injected:
  `make_deploy.py::_inject_radio_channel()` rewrites `kChannel` AND
  `kGroup`, and `DEFAULT_RADIO_GROUP = 10` applies only when a robot's
  config names no group. Now reads "the per-robot pair ... into
  `kChannel`/`kGroup`".
- `radio_transport.h`'s `tryReceiveLine()` cited
  `clasi/issues/radio-rx-command-plane-run-over-bridge.md` as live; that
  issue is **closed** (`clasi/issues/done/`) and the path no longer
  resolves. Citation dropped, the fact (multi-fragment inbound
  reassembly is out of scope) kept.
- `radio_transport.h`'s `setChannel()` cited
  `clasi/issues/changing-the-radio-group-mid-run-is-unverified.md`. That
  issue is **still open**, but lives at `clasi/issues/low/`. Path
  corrected rather than dropped.
- `protocol.h`'s `serialDropCount()` pointed at "protocol.h's own
  top-of-file comment on why that matters to PXT's dependency scan" —
  the top-of-file comment says no such thing, and never did. Restated
  the fact (it avoids pulling `radio_transport.h` into shims.cpp's
  include graph) directly.
- `radio_transport.cpp` cited "sprint.md Open Question 1", which does
  not resolve to anything in this tree. Dropped; the fact
  (`MICROBIT_RADIO_MAX_PACKET_SIZE` is whatever the CODAL target
  compiles with, computed locally to avoid a static-init-order
  dependency) kept.

### Write-time pass over the sprint-033 files

`run_bridge.h`, `transport_sink.h` and `config_fields.h` carried
sprint-033 narration rather than annex items. Contract, ownership rule
and every hazard kept; the narration cut. In `config_fields.h` the
per-row `// ConfigField.<Name>: "<label>"` lines were **not touched** —
they are `tools/gen_config_field_enum.py`'s input, and the header now
says so explicitly instead of calling them a "comment line".
`uv run python tools/gen_config_field_enum.py --check` reports
`src/blocks/motion.ts is up to date.`

### Ratios (counting rule: `//` and not `//%`, per the ratchet)

| file | before | after |
|---|---|---|
| `comms/radio_transport.h` | 5.29 (370/70) | **3.69** (258/70) |
| `comms/serial_transport.h` | 5.17 (93/18) | **3.89** (70/18) |
| `comms/protocol.h` | 4.43 (434/98) | **3.58** (351/98) |
| `comms/run_bridge.h` | 2.47 (84/34) | **2.32** (79/34) |
| `comms/transport_sink.h` | 2.25 (54/24) | **1.92** (46/24) |
| `comms/config_fields.h` | 1.71 (101/59) | **1.61** (95/59) |
| `comms/protocol.cpp` | 1.28 (431/338) | **1.15** (389/338) |
| `comms/emit_queue.h` | 1.02 (50/49) | **0.80** (39/49) |
| `comms/run_queue.h` | 0.64 (39/61) | **0.59** (36/61) |
| `comms/radio_transport.cpp` | 0.58 (65/112) | **0.57** (64/112) |

Every file moves DOWN, so ticket 001's per-file ratchet
(`_RATIO_BASELINE`, untouched by this ticket) passes on all ten. The
archaeology-marker count is **292** against `_BUDGET = 388`.

### Comment-only proof (these files are not host-compiled)

`protocol.{h,cpp}`, `radio_transport.{h,cpp}` and `serial_transport.h`
reach `pxt.h`, so the host suite cannot compile them. Proved
mechanically instead, over `git diff` against the pre-ticket tree:

- **Every single `+`/`-` line in the diff is a `//` comment line or a
  blank line.** Non-comment diff lines: **0**. No `/* */` block comment
  was opened, closed or edited anywhere in this ticket, so there is no
  block-comment interior to account for.
- **Per-file code-line comparison**: strip blank lines and `//`
  (non-`//%`) lines from HEAD's copy and from the working copy, then
  compare the survivors line by line. All ten files: **identical**,
  same count (config_fields.h 59, emit_queue.h 49, protocol.cpp 338,
  protocol.h 98, radio_transport.cpp 112, radio_transport.h 70,
  run_bridge.h 34, run_queue.h 61, serial_transport.h 18,
  transport_sink.h 24).
- **`protocol.cpp`'s four `//%` pragma lines**: `diff` of `grep -A 3
  '^//%'` between HEAD and the working copy is empty — the pragmas and
  the three lines following each are byte-identical. (The four moved
  from lines 812/825/835/840 to 770/783/793/798 because comment lines
  above them were removed; their text did not change.)
- **`radio_transport.h`'s regex block**: `diff` of the DO-NOT-REFORMAT
  warning through `static constexpr int kChannel = 4;` between HEAD and
  the working copy is **empty**, and `kGroup` is now the line
  immediately after it (both declarations byte-identical). Re-running
  `make_deploy.py`'s own four injection regexes over the edited files
  gives **exactly one match each**: `_K_CHANNEL_RE` 1, `_K_GROUP_RE` 1,
  `_K_PROFILE_RE` 1, `_K_VERSION_RE` 1 — which is what
  `_inject_radio_channel()`/`_inject_profile()`/`_inject_version()`
  require or they exit the build.
- **No `wire_handler.*` or `wire_adapter.*` file is in the diff**
  (ticket 005 owns them).
- No trailing `// [unit]` was deleted; no identifier was renamed.

### Tests (foreground, this turn)

    uv run pytest tests/host/test_archaeology_marker_budget.py \
                  tests/host/test_wire_constants_drift.py \
                  tests/host/test_cxx11_syntax_gate.py -q   -> 58 passed
    uv run pytest tests/host/ -k source_pin -q               -> 85 passed
    uv run python tools/gen_config_field_enum.py --check      -> up to date
    uv run pytest tests/host/test_config_surface_single_source.py \
                  tests/tools/test_gen_config_field_enum.py \
                  tests/tools/test_make_deploy_robot_channel.py \
                  tests/tools/test_make_deploy_radio_link.py -q -> 121 passed
    uv run pytest tests/host -q                              -> 1167 passed

The desk firmware build remains the team-lead's gate for the
`pxt.h`-bound translation units, per the sprint's Test Strategy.
