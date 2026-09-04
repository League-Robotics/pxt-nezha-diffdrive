---
status: pending
sprint: '034'
---

# Comment work order: 53 boil-downs, 16 factual fixes, track or relocate the untracked capture citations, ratchet volume

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: CH-01, CH-02, CH-03 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)),
CM-10 ([comms](../../../docs/code-review/2026-09-02/raw/comms.md)), BT-16..BT-19 ([blocks-and-test](../../../docs/code-review/2026-09-02/raw/blocks-and-test.md)),
TL-16 ([tools-and-tests](../../../docs/code-review/2026-09-02/raw/tools-and-tests.md)). Triage #14.

## Description

Project-owned `src/` is back at ~1.4 comment lines per code line
(`radio_transport.h` 7.3, `motion_engine.h` 4.3, `protocol.h` 3.7; the
kernel runs 0.03), and every file sprints 026-028 touched grew. Two new
anti-patterns: dated UPDATE paragraphs stacked on a comment, and MEASURED
citations to six `captures/` directories that are gitignored and
untracked. Sixteen comments are factually wrong (file names, ordinals,
"not consulted by anything yet", "handlers run on their own fiber", the
retired radio channels, `formatDiag()`), listed in the review section 5.

## Remedy

- Apply the three annexes' boil-down lists (18 + 12 + 10 + 13 blocks)
  with the guidelines' safety rules: re-anchor by content, treat every
  item as a possible no-op, check each replacement against the current
  code before landing it.
- Fix the sixteen factual errors.
- `git add -f` the six cited capture directories (small JSON/py) or move
  the numbers into a tracked `reports/*.md` and cite that.
- Extend `test_archaeology_marker_budget.py` to also ratchet comment
  volume per file (comment lines / code lines), so the cleanup holds.
- Add anti-patterns 6 and 7 to `docs/code-review/guidelines.md`.

## Acceptance

- The per-file ratio table in the review section 5 re-measured: no
  project-owned file above 2.0.
- Every `captures/` path cited from `src/` resolves in a fresh clone.
