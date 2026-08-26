---
date: 2026-08-26
sprint: none (the mis-numbered sprint is void)
category: ignored-instruction
---

# Worktree session allocated a colliding sprint number from its stale DB

## What Happened

Working from the `blocks-local-codeserver-test-bf93c6` worktree, I
dispatched the sprint-planner in Roadmap Mode for a blocks-usability
sprint. The planner called `create_sprint`, which self-numbered from
the worktree's CLASI DB snapshot and produced "sprint 013". I
presented "sprint 013 is planned and awaiting approval" to Eric as
fact. In the authoritative main checkout, 013 (source-tree
reorganization) was already DONE, 014 was executing under another
session holding the execution lock, and 015 was parked at roadmap —
the next free number was 016. Eric caught it: "I don't see a sprint
13. What I see is a sprint 14 … who's doing sprint 14?"

A second, compounding error: the worktree is pinned at 447135a, which
predates the 013 source-tree reorg, so the sprint's tickets referenced
moved paths (`src/sim.ts` instead of `src/blocks/sim.ts`) and its arc
ticket overlapped sprint 015's core goal without knowing 015 existed.

## What Should Have Happened

Before creating any sprint from a worktree session: reconcile against
the main checkout — read its `clasi/sprints/` + DB (or ask the
main-checkout session via SendMessage) for the real sprint list, the
lock holder, and any parked roadmap sprints whose scope might overlap.
Only then dispatch the sprint-planner, passing the authoritative next
number and the overlap constraints explicitly.

## Root Cause

**Ignored instruction** (memory-level, not rules-level): my memory
index contains two entries — "Worktree CLASI status is stale" and
"Worktree CLASI DB is stale: never trust a worktree session's CLASI
status for coordination; the main-checkout DB is authoritative." I
applied that memory to robot ownership the same evening but did not
apply it at the sprint-creation step. The check existed; it was not
wired into the workflow step where it mattered. Contributing factor:
no written rule in `.claude/rules/` covers sprint creation from
worktrees, so the guard lived only in session memory.

## Proposed Fix

1. Personal memory updated (done, same session): the worktree-staleness
   memory now names sprint numbering explicitly as the failure mode,
   with this incident as the example.
2. Process fix worth adopting in CLASI itself: `create_sprint` (or the
   sprint-planner roadmap instructions) should detect that it is
   running inside a worktree (`git rev-parse --git-common-dir` differs
   from `--git-dir`) and either refuse to self-number or first consult
   the main checkout's DB. Filed as a candidate `/report` item for the
   CLASI repo rather than a local hack.
3. The void sprint (`clasi/sprints/013-makecode-blocks-usability-and-
   correctness/` on this branch only) must not merge as-is: re-create
   against the main DB as 016+ after sprint 014 closes, with tickets
   re-pathed to the post-reorg tree and the arc ticket resolved
   against sprint 015's scope.
