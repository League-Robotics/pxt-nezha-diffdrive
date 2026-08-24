---
status: pending
sprint: 009
---

# Upstream re-diff of the vendored kernel: five truncated comments and a repo name that does not resolve

Priority: **Low** — code review 2026-08-23, R-28 (comment verifier, with
upstream fetched and compared).

Vendoring `diffdrive.{h,cpp}` from the upstream robot kernel was lossy in
two ways, and the vendoring comments now misdirect the next person who
tries to re-sync.

## 1. Five comments are truncated mid-sentence, not terse

Each ends at a semicolon or dash where upstream continues. Two of the
five carry contracts this very code review tripped over:

- `diffdrive.h:90-91` — `maxDuty`. Upstream: `[%] authority rail (lambda
  scales to this); 0 = ALL modes refused`. The truncation drops the
  0-sentinel meaning, which is exactly the declaration-site statement
  that an unset `maxDuty` refuses every command
  (`checkCommandable`: `maxDuty <= 0 → kRefusedUnconfigured`).
- `diffdrive.h:91` (the fifth truncation, which the comment audit itself
  missed) — `fullDutyVelocity`. Upstream continues:
  `0 = uncalibrated → VELOCITY refused`. This is the contract R-11
  (`cruise == 0` resolving to a full-duty lunge) was reasoning against
  without being able to read it.
- `diffdrive.h:81-82` (`kRefusedNotBegun`), `:84` (`kCadencePreserved`),
  `:125` (`cycleOverrunCount`) — the audit's proposed completions for
  these three were verified faithful to upstream.

## 2. The vendoring provenance names a repo that does not exist

`League-Robotics/radio-robot-elite` does not resolve on GitHub. The
public upstream is `League-Robotics/radio-robot`, and inside it the
kernel has **moved**: it now lives at `src/firm/diffdrive/`, while
`src/firm/control/differential_drive.h` is a thin forwarding-adapter
header. Both this repo's vendoring comments and two of the comment
audit's proposed replacements name the unresolvable repo and the stale
path. `nezha_port.h`'s own comment already says `radio-robot` (correct),
so the tree is internally inconsistent about it too.

If `-elite` is a real private or local checkout, the provenance line
should say so explicitly rather than reading as a public repo name.

## What to do

1. Re-diff the vendored pair (`src/diffdrive.h`, `src/diffdrive.cpp`)
   against upstream `radio-robot` `src/firm/diffdrive/` **before**
   editing either file, so the comment cleanup and this restoration are
   one pass, not two.
2. Restore the five truncated comments from the upstream text quoted in
   `docs/code-review/2026-08-23/raw/verify-comments.md` §3.
3. Document the real upstream repo and current path in `src/DESIGN.md`'s
   provenance section — one authoritative statement the per-file headers
   can point at instead of each restating a path that goes stale.
4. Record whether the vendored copy has diverged from upstream in any way
   other than comments. If it has, that divergence is the thing future
   re-syncs most need written down.

## Related

- Runs in the same sprint as the comment cleanup work order
  (`comment-cleanup-work-order.md`) and must precede or accompany it —
  the audit's `diffdrive.h` REWRITE items are the same lines this issue
  restores from upstream, and applying them without upstream in hand is
  how the truncations became permanent the first time.
