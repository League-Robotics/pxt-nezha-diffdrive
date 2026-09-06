---
id: "001"
title: "Comment-volume ratchet and guidelines anti-patterns 6 and 7"
status: open
use-cases: [SUC-002]
depends-on: []
github-issue: ""
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Comment-volume ratchet and guidelines anti-patterns 6 and 7

## Description

Foundation ticket. Everything after this one edits comments in `src/`,
`test/` and `tools/`; this ticket puts the measuring instrument in place
first so tickets 002-007 can watch their own work land against it, and
writes down the two anti-patterns the review named so the guidelines
describe the standard the rest of the sprint applies.

Two files, neither of which any later ticket touches:

- `tests/host/test_archaeology_marker_budget.py` — add a second,
  independent ratchet on **comment volume** (comment lines / code
  lines) per file, alongside the existing archaeology-marker ratchet.
- `docs/code-review/guidelines.md` — append anti-patterns **6** and
  **7** to the existing list of five under "Recurring anti-patterns
  (delete or rewrite on sight)".

**No behaviour change.** This ticket adds one test function and one
constant table; it edits no production source.

### The counting rule (decided at planning time — implement exactly this)

A line is a **COMMENT** line iff, stripped of leading whitespace, it
begins with `//` **and does not** begin with `//%`. Every other
non-blank line is a **CODE** line. Blank lines count as neither.

Three exclusions are load-bearing and must be stated in the module
docstring with their reasons, because a future reader cannot recover
them from the code:

1. **`//%` is code, not comment.** Those are PXT block pragmas
   (`//% block=`, `//% group=`, `//% weight=`). A ratchet that counted
   them would pressure an author into deleting required block metadata.
   There are 202 such lines across `src/blocks/*.ts` and 41 in
   `src/shims.cpp`/`src/comms/protocol.cpp`.
2. **`/** ... */` JSDoc is not counted** (it does not start with `//`,
   so the rule already excludes it, but say why): it is the
   student-facing block API documentation PXT renders into the toolbox.
   It is a deliverable, not archaeology.
3. **A trailing `// [mm]` on a line of code is not counted** — the rule
   only inspects the *start* of the stripped line. This is deliberate:
   `.claude/rules/no-units-in-identifiers.md` makes those trailing unit
   comments the house style, and the ratchet must never create pressure
   to delete one.

The vendored kernel (`src/core/diffdrive.{h,cpp}`) is excluded from the
volume ratchet exactly as it already is from the marker ratchet — reuse
`_EXCLUDED` and `_SOURCE_SUFFIXES`, do not re-declare them.

Sanity check for the implementation: this rule reproduces the
2026-09-02 review's own table closely where the file has not changed
since — `platform/nezha_port.cpp` 0.96 (exact match) and
`comms/wire_adapter.cpp` 1.31 vs the review's 1.29.

### Per-file baselines, not a blanket cap

Seed a `_RATIO_BASELINE` dict mapping repo-relative path to the
measured ratio, from the table in `sprint.md`'s "Verification pass"
section (that is today's measurement — ticket 008 re-measures and
tightens after the cleanup lands).

A blanket cap was considered and rejected at planning time; record the
reason in the docstring. A blanket 2.0 would fail
`src/core/fiber_identity.h` (7 code lines) and `src/core/heading_wrap.h`
(11 code lines) forever — a header that states a contract and a unit is
above 2.0 no matter how tight it is — while letting
`src/comms/wire_adapter.h` (5.46) sit at 1.99 unchallenged.

Design points to honour:

- **Two assertions, not one fused metric.** The marker ratchet catches
  *archaeology*; the volume ratchet catches *length*. The review's own
  finding is that the new growth cites dates and capture paths rather
  than sprint numbers, so it is invisible to the marker ratchet. A
  fused score would let one mask the other — which is how the growth
  between the 08-26 and 09-02 reviews went unnoticed.
- **Ratchets down only**, same discipline as `_BUDGET`: raising an
  entry is an explicit reviewed edit to this file, never incidental.
- **A file not in the baseline dict is not failed** — a newly added
  `src/` file has no baseline. Assert only over the files present in
  the dict, and have the test report any `src/` file missing from the
  dict as a note in the failure message (not a failure), so ticket 008
  and future sprints can see the gap.
- **The failure message must name the file, its baseline and its
  current value**, and say what to do (cut the comment, or raise the
  baseline as its own reviewed edit).

Also in this ticket: leave `_BUDGET` alone at 388. Ticket 008 lowers
it, after the cleanup that will move the number.

### Guidelines anti-patterns 6 and 7

Append to the existing numbered list (currently 1-5, under "Recurring
anti-patterns (delete or rewrite on sight)"), in the same shape as
1-5: bolded name, what it is, why it costs a reader, and the concrete
example from this tree.

**6. Dated UPDATE paragraphs stacked on one comment.** A comment that
carries its original conclusion plus one or more later
`UPDATE <date> — ...` paragraphs correcting it. The third reader has to
reconcile all of them to learn the one fact that is true now. Rewrite
the comment to state the current truth; the history is in `git log`.
Concrete example, verified present at planning time —
`src/platform/nezha_port.cpp` carries the original fault-handler
forensics plus **two** dated updates: `UPDATE 2026-09-01 -- the "memory
corruption" above is probably not ...` and `UPDATE 2026-09-02 --
RESOLVED. The VFP-register-clobber theory above ...`. A reader has to
get to the second update to learn it was the VFP clobber, and that it
is fixed.

**7. Citations to untracked artifacts.** A `MEASURED` claim naming a
capture path, log or file that is gitignored and not force-tracked, so
a fresh clone cannot follow it. `.claude/rules/measurement-citations.md`
requires that a citation name an artifact — this anti-pattern is the
case where it names one that cannot be reached. The remedy is to
`git add -f` the artifact (`captures/` is gitignored, and 464 files
under it are already force-tracked — that is the established
precedent), or to repoint the citation at an artifact that is tracked.
State explicitly that `reports/` is **not** an option in this repo: it
is gitignored in full. Concrete examples verified at planning time:
`captures/gopiv-profile-sweep-20260901/` and
`captures/motion-profile-probe-20260901/`, both cited from
`src/DESIGN.md`, both untracked; and
`captures/tovez-wifi-20260902/`, cited from `src/DESIGN.md` and not
present on disk at all.

## Acceptance Criteria

- [ ] `tests/host/test_archaeology_marker_budget.py` contains a second
      test function asserting a per-file comment-volume ratio against a
      `_RATIO_BASELINE` dict seeded from the `sprint.md` table.
- [ ] The counting rule is implemented as specified (`//` and not
      `//%`; JSDoc uncounted; trailing comments uncounted; vendored
      kernel excluded via the existing `_EXCLUDED`).
- [ ] The module docstring states the counting rule **and** why `//%`,
      JSDoc and trailing unit comments are excluded, and why the
      baseline is per-file rather than a blanket cap.
- [ ] The new test's failure message names the file, its baseline, its
      current value, and the two legitimate responses.
- [ ] A `src/` source file absent from `_RATIO_BASELINE` does not fail
      the test but is reported in the message.
- [ ] The existing `test_archaeology_marker_count_is_within_budget`
      keeps its name, regex, exclusion set and semantics; `_BUDGET`
      stays at 388 (ticket 008 lowers it).
- [ ] `docs/code-review/guidelines.md` lists **seven** anti-patterns;
      6 and 7 match the descriptions above and carry the verified
      concrete examples.
- [ ] Both tests pass against the current tree (they must, since the
      baselines are seeded from it).
- [ ] No file under `src/`, `test/` or `tools/` is modified.

## Testing

- **Existing tests to run** (foreground, never backgrounded):

      uv run pytest tests/host/test_archaeology_marker_budget.py -v

  Then the full host directory once, since this ticket changes a file
  that other host tests share a directory with:

      uv run pytest tests/host/ -q

- **New tests to write**: the volume-ratchet test itself is the new
  test. Additionally assert the counting rule directly on a small
  inline fixture (a few lines covering `//`, `//%`, a trailing
  `// [mm]`, a JSDoc block and a blank line) so a future edit to the
  rule fails visibly rather than silently reshuffling every baseline.
- **Verification command**: `uv run pytest tests/host/ -q`

## Notes for the implementer

- Do **not** run the full repo suite for this ticket; the sprint's one
  full run happens inside `close_sprint`.
- The measurement script used at planning time is trivial to
  re-derive from the counting rule above; re-derive it rather than
  trusting a copy, and reconcile against the `sprint.md` table before
  seeding. If your numbers differ from the table, say so in the
  completion notes rather than silently seeding different values.
