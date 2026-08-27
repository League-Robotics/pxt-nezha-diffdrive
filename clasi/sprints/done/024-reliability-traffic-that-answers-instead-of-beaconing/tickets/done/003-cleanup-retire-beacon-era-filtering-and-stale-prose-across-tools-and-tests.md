---
id: '003'
title: 'Cleanup: retire beacon-era filtering and stale prose across tools/ and tests/'
status: done
use-cases:
- SUC-001
depends-on:
- '001'
- '002'
github-issue: ''
issue: reliability-line-free-runs-at-20-hz-on-the-radio-with-no-host.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Cleanup: retire beacon-era filtering and stale prose across tools/ and tests/

## Description

Tickets 001 and 002 remove the free-running reliability beacon and fix
the host's reconnect path. Several places in `tools/` and `tests/`
describe the beacon as current, expected behavior — either as a comment
explaining a workaround built around it, or as prose describing
`protocol.cpp`'s periodic emission as unconditional. Once the beacon is
gone, these become misleading to a future reader (or, worse, an
invitation to "fix" the new silence by restoring it). This ticket is a
documentation/comment sweep — **no logic or assertion changes** are
expected anywhere in this ticket's scope, because `WireHandler`'s own
tested behavior (what `tests/host/`'s ctypes-shim tests actually assert
on) does not change in this sprint; only `Protocol`'s calling policy
changed, in ticket 001.

Specific known sites, found during sprint planning (confirm each is
still accurate against tickets 001/002's landed code before editing —
don't blind-edit from this list without checking):

1. **`tools/arc_capture.py:161`** — the firmware-identity check's
   comment currently reads: `ack `/`nack ` keepalive lines stream
   continuously regardless of this command ... they are not a reply to
   the bogus verb and must be filtered out." That's no longer true: a
   reply can only ever follow a request. Correct the comment to state the
   filter is now defensive/vestigial (kept because some other reply —
   `STATUS`, `GET`, etc., sharing the same link — could still overlap the
   read window, not because a beacon is expected). Do not remove the
   filter itself unless review shows it is truly dead code with zero
   remaining purpose — the issue that names this site
   (`reliability-line-free-runs-at-20-hz-on-the-radio-with-no-host.md`,
   "The stream has no consumers") only asks that the workaround be
   *revisited*, not blindly deleted.
2. **`tools/tlm.py`** — the module docstring (~lines 54-61: "The
   reliability keepalive (`ack <n> <lastDone> <reason>`, streamed
   continuously at 50 ms)...") and `TlmStream.orphan_frames`'s docstring
   (~line 122: "a late-attaching consumer misses the firmware's periodic
   re-emit window") both describe the old cadence. Correct both to
   describe the reliability line as a per-line reply, still filtered out
   of `feed()` the same way it always was (that filtering logic itself —
   `feed()` only recognizing `thdr`/`t` — needs no change).
3. **`tools/tour_capture.py`** — checked during planning; no beacon-cadence
   assumption was found, but confirm this against the actual file rather
   than trusting the planning-time read. If a similar assumption exists,
   correct it the same way; if not, no change needed — say so explicitly
   rather than leaving it unaddressed silently.
4. **`tests/host/test_wire_grammar.py`** (~lines 274-276),
   **`test_wire_reliability.py`** (module docstring, ~line 20, citing
   "S8.5 (periodic emission piggybacked on telemetry, still no timer)"),
   **`test_wire_motion_verbs.py`** (~line 654, "exactly as protocol.cpp's
   periodic-emission block does in production") — these describe
   `protocol.cpp`'s call pattern, not `WireHandler`'s own behavior (which
   is what these tests actually exercise and assert on). Correct the
   *prose* only: `emitReliability()`/`emitTelemetry()` still do exactly
   what these files describe when *called*; what changed is that
   `protocol.cpp` no longer calls `emitReliability()` unconditionally.
   `test_wire_telemetry_frame.py`'s own reliability-piggyback comments
   (~lines 90-121) describe `WireHandler`-level behavior that is genuinely
   unchanged — review them but expect no edit unless one specifically
   claims the call happens "regardless of subscription" or similar.
5. **`tests/tools/test_tlm.py`** (~lines 54-61 module docstring, ~101-105
   `ACK_LINE`/`NACK_LINE` section comment) — same "streams continuously at
   50 ms" claim. Correct the prose. The `ACK_LINE = 'ack 0 0 none'` /
   `NACK_LINE = 'nack 5 0 none'` constants themselves, and
   `test_ack_and_nack_lines_are_not_telemetry`, describe the *shape* of a
   reliability line, not its cadence — leave these unchanged; they remain
   correct fixtures.
6. **`tests/tools/test_run_verbs.py`** — checked per the sprint's explicit
   instruction to review it. It tests `RUN:` string-keyed dispatch,
   unrelated to the reliability plane; planning-time review found no
   beacon dependency. Confirm this against the actual file; document the
   confirmation (no change expected) rather than skipping the check.

## Acceptance Criteria

- [x] `arc_capture.py:161`'s comment no longer claims the keepalive
      "stream[s] continuously ... regardless of this command"; states
      that the filter is now defensive/vestigial and why it's kept.
- [x] `tools/tlm.py`'s module docstring and `TlmStream.orphan_frames`
      docstring no longer describe the keepalive as streaming
      continuously at 50 ms; corrected to describe it as a per-line
      reply, still filtered by `feed()` unchanged.
- [x] `tools/tour_capture.py` reviewed; either corrected or explicitly
      confirmed clean, with the finding stated in this ticket's own
      notes.
- [x] Stale prose in `tests/host/test_wire_grammar.py`,
      `test_wire_reliability.py`, `test_wire_motion_verbs.py` corrected
      wherever it describes `protocol.cpp`'s periodic emission as
      unconditional/continuous current production behavior.
      `test_wire_telemetry_frame.py` reviewed; edited only if it makes
      the same claim (expected: no change needed there).
- [x] `tests/tools/test_tlm.py`'s "streams continuously at 50 ms" comment
      corrected; `ACK_LINE`/`NACK_LINE` fixtures and
      `test_ack_and_nack_lines_are_not_telemetry` left unchanged (confirmed
      still correct as literal wire-format fixtures).
- [x] `tests/tools/test_run_verbs.py` reviewed; confirmed to have no
      beacon-cadence dependency (documented; no change expected).
- [x] No assertion or logic changes anywhere in this ticket's diff — a
      diff review confirms every hunk is a comment/docstring edit.
- [x] `uv run pytest tests/host/ tests/tools/` passes — this ticket is
      the sprint's final full-suite regression gate for the affected
      areas.
- [x] `uvx ruff check tools tests` is clean.

## Implementation Notes

**Grep-driven sweep, as the Implementation Plan describes**: searched
all nine files named in the Description for `continuously`,
`free-running`, `beacon`, `50 ?ms`, `periodic`, `keepalive` (case
insensitive), then read each hit's surrounding code and checked it
against tickets 001/002's actual landed diffs (`git show 75ba0aa`,
`git show b622410`) before deciding whether it was genuinely stale.
Several of the ticket's own quoted line numbers had drifted from
current file content (expected — the ticket says to confirm, not
trust, the list); the actual current locations are cited below.

**1. `tools/arc_capture.py`** — two sites, one named, one found by the
sweep:
- The firmware-identity-check comment (now at line ~155, not 161)
  rewritten: no longer claims the keepalive "stream[s] continuously
  ... regardless of this command"; now states the filter is
  defensive/vestigial, kept in case some OTHER reply sharing the link
  (STATUS, GET, etc.) lands in the same read window, not because a
  beacon is expected. The filter code itself (`reply = [s for s in
  seen if not s.startswith(('ack ', 'nack '))]`) is untouched — it has
  a real, if narrower, remaining purpose, so it was not deleted.
- `_parse_trajectory()`'s catch-all comment (~line 103) said "already
  apply to this same keepalive stream" — reworded to drop the
  "stream" framing (no longer an unsolicited stream since ticket 001)
  while keeping the same behavioral claim (unrecognized lines are
  silently ignored).

**2. `tools/tlm.py`** — module docstring (~line 54) corrected: the
keepalive is now described as a per-line reply, not a periodic
broadcast, with `feed()`'s filtering logic called out as explicitly
unchanged. A third site the sweep found, `require_stream()`'s docstring
(~line 326, "streamed continuously"), was corrected the same way —
not named in the ticket's list but the same stale claim.
**`TlmStream.orphan_frames`'s docstring reviewed and deliberately left
unchanged**: its "a late-attaching consumer misses the firmware's
periodic re-emit window" is about `thdr`'s own periodic re-emission
(`kHeaderRefreshFrames` = 20 frames, ~1 Hz — `wire_handler.cpp:1224`,
also documented earlier in this same module's docstring), which is a
completely different mechanism from the ack/nack reliability keepalive
and is untouched by ticket 001 (ticket 001 only removed
`protocol.cpp`'s non-subscribed-transport `emitReliability()`-only
branch; the telemetry-on `thdr`/`t` emission path, including its
header-refresh cadence, was never touched). The ticket's Description
bundled this docstring in with the module docstring's genuinely-stale
claim under one sentence ("both describe the old cadence"), but they
describe two different cadences, only one of which changed. This is
exactly the kind of item the ticket's own instruction ("confirm each is
still accurate ... before editing") was for — reported here rather
than blind-edited.

**3. `tools/tour_capture.py`** — reviewed (full-file grep for `ack`,
`nack`, `reliability`, `keepalive`, `beacon`, `periodic`,
`continuously`: zero hits beyond an unrelated "GAP line"/"round trip"
comment). Confirmed clean — no change made.

**4. `tests/host/` reliability-plane tests**:
- `test_wire_grammar.py`'s `emit_reliability()` docstring (~line 274)
  reworded: dropped "own periodic emission" (ambiguous now that
  `protocol.cpp`'s non-subscribed periodic call is gone) in favor of
  "own emission primitive", plus an explicit note that WHEN production
  calls it is `protocol.cpp`'s business, not `WireHandler`'s, and what
  that calling policy is today.
- `test_wire_reliability.py`'s module docstring citation of S8.5
  (~line 20) **reviewed and confirmed accurate, left unchanged**: it
  cites `radio-robot-lib`'s own canonical `protocol.md` spec text
  (explicitly marked in this same docstring as "read-only, a different
  repo — this project conforms to its grammar, it does not vendor its
  C++"), which sprint.md's own Migration Concerns section confirms is
  unaffected by this sprint (S8.5's own wording is "piggybacked on
  telemetry", which this repo's narrowed conformance is consistent
  with). This is not the same claim as "`protocol.cpp` calls
  `emitReliability()` unconditionally" and needed no correction. A
  separate site in the same file, `test_emit_reliability_reacks_
  highest_accepted_id_when_no_gap_is_open`'s docstring (~line 302,
  "via this same periodic call"), WAS stale and was corrected — found
  by the sweep, not named in the ticket's list.
- `test_wire_motion_verbs.py`'s `emit_telemetry()` docstring (~line
  654) reworded to specifically scope "protocol.cpp's periodic-emission
  block" to its still-unchanged telemetry-subscribed branch, and to
  name the deleted sibling branch explicitly, so a future reader can't
  misread the surviving claim as covering the removed one.
- `test_wire_telemetry_frame.py` (~lines 90-121) reviewed: no claim of
  "regardless of subscription" or equivalent found. Confirmed clean —
  no change made, as the ticket expected.

**5. `tests/tools/test_tlm.py`** — the `ACK_LINE`/`NACK_LINE` section
comment (~line 101) corrected: no longer claims "streams continuously
at 50 ms"; now states it is a per-line reply, not a periodic broadcast.
`ACK_LINE`/`NACK_LINE` themselves and
`test_ack_and_nack_lines_are_not_telemetry` (~line 246) left unchanged,
as directed. The module docstring (ticket's estimate: ~lines 54-61) was
swept and does NOT actually contain a "streams continuously"/"50 ms"
claim anywhere in current content — the only such claim in this file
is the one at ~line 101 that was corrected; the ticket's line-range
estimate for the docstring appears to have been imprecise at planning
time. `test_tlm.py`'s other `keepalive` mentions (~lines 42, 247)
describe filtering behavior, not cadence, and were left alone.

**6. `tests/tools/test_run_verbs.py`** — reviewed (full-file grep:
zero hits for `beacon`, `keepalive`, `continuously`, `periodic`,
`reliability`, `ack`/`nack`). Confirmed clean, as the ticket expected —
no change made.

**No follow-ups found.** Every review turned up either a straightforward
stale-cadence claim (corrected) or code/prose that was already accurate
(left alone, with the reasoning recorded above). No behavioral gap
requiring a separate ticket was surfaced.

**Verification**: `uv run pytest tests/host/ tests/tools/` — 754
passed. `uvx ruff check tools tests` — all checks passed. `git diff`
reviewed hunk-by-hunk: every changed line is inside a `#`/`"""` comment
or docstring; no assertion, condition, or runtime statement was
touched.

## Implementation Plan

**Approach**: A grep-driven sweep for the specific stale phrases
identified during sprint planning ("streams continuously", "50 ms" /
"50ms", "free-running", "periodic" as applied to the now-removed
`protocol.cpp` branch, "beacon", "keepalive") across the files listed in
the Description, confirming each hit against tickets 001/002's actual
landed code before editing. Prose/comment edits only.

**Files to modify**: `tools/arc_capture.py`, `tools/tlm.py`,
`tools/tour_capture.py` (if review finds something), `tests/host/
test_wire_grammar.py`, `test_wire_reliability.py`,
`test_wire_motion_verbs.py`, `test_wire_telemetry_frame.py` (if review
finds something), `tests/tools/test_tlm.py`.

**Files to create**: none.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/ tests/tools/` —
  the full suite for every module this sprint touched, since this is the
  sprint's closing ticket and its own regression gate.
- **New tests to write**: none required — this is a prose-only ticket. If
  review of `tour_capture.py` or `test_run_verbs.py` surfaces an actual
  behavioral gap (not just stale prose), do not silently expand scope to
  fix it — note it in this ticket's own notes and flag it to team-lead as
  a follow-up.
- **Verification command**: `uv run pytest tests/host/ tests/tools/`;
  `uvx ruff check tools tests`.
