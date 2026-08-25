---
status: in-progress
sprint: 009
tickets:
- 009-001
- 009-002
- 009-003
- 009-004
- 009-005
- 009-006
- 009-007
- 009-008
- 009-009
- 009-010
- 009-011
- 009-012
---

# Comment cleanup: apply the audited work order (135 items, with corrections)

Priority: **Low** (mechanical, but large surface) — code review 2026-08-23,
comment-hygiene dimension.

The audit (`docs/code-review/2026-08-23/raw/comment-audit.md`) classified
all ~854 comment blocks across 59 files: **11 DELETE, 123 REWRITE, 1 ADD,
~719 KEEP** (~16% noise, concentrated in the wire-layer headers:
serial_transport.h 83%, wire_adapter.h 71%, tests/host/README.md 60%).
Every item carries line numbers and replacement text.

**Mandatory protocol** (spot-verification found 8 of 16 sampled rewrites
would have lost load-bearing content — one would have baked in a wrong
calibration constant):

1. Apply the audit **together with**
   `docs/code-review/2026-08-23/raw/verify-comments.md` — its CHALLENGE
   corrections override the audit's replacement text (worst case: the
   rotationalSlip derivation, the radio/serial cap non-equality, the
   upstream repo name).
2. Any REWRITE item **not** among the 27 spot-checked gets the same check
   before applying: does the replacement preserve every invariant, unit,
   measured value, and derivation the original carried?
3. The five truncated `diffdrive.h` comments (81, 84, 90, 91, 125) are
   restored from the upstream text quoted in verify-comments.md — do not
   paraphrase them shorter.
4. tests/host/README.md's stale "does NOT cover yet" section: fix per the
   audit.
5. Scope tests to the touched modules; the change must be behavior-neutral
   (comments and doc-text only).

Follow-up in the same work: distill the audit's five anti-patterns
(ticket-archaeology headers, reviewer-justification essays, stale
cross-layer claims, diff restatement, orphaned comments) into a short
comment-standards section of `docs/code-review/guidelines.md`, so future
agents stop producing the noise this issue deletes.
