---
title: "MEASURED claims and capture citations that name no reachable artifact (found by sprint 035, out of its scope)"
status: pending
created: 2026-09-06
---

# MEASURED claims without artifacts, found by sprint 035

Sprint 035 (comment work order) made every `captures/` citation from
`src/` resolve and forbade its tickets from inventing citations. These
were found on the way and left as found, because fixing them needs
either the original artifact or a re-measurement:

1. `src/comms/wire_handler.cpp` — two claims name board and date but no
   artifact, and disagree with each other: `emitHelp()`'s "MEASURED
   2026-08-27, tovez over the torture->channel-3 relay" (66-75 % per-line
   delivery) and `execGet()`'s "Measured on this rig 2026-08-27"
   (66-83 %). `tools/fieldlink.py` carries the 66-83 % figure too and
   `tools/DESIGN.md` now quotes it as UNVERIFIED (sprint 034 ticket 012).
2. `test/test.ts` — two claims with no artifact: the vevov 2026-08-25
   "58 mm of tour closure scored as 22 mm" note (~line 320) and the
   vevov 2026-08-28 "153 frames read ox=oy=oh=0 while the encoders
   logged 246 mm" note (~line 941).
3. Capture citations outside `src/` that do not resolve in a fresh
   clone: `captures/vevov-cal-20260902/` (present, untracked),
   `captures/vevov-line-20260902/deskew-clean.jpeg` (present, untracked),
   `captures/consolidation-acceptance-tigez-20260906/` (not on disk;
   cited from tests/calibration -- the program that would create it was
   never run, see
   `bench-acceptance-of-the-sprint-034-consolidated-tools.md`).
4. `src/motion/motion_engine.cpp` still carries dangling "this ticket:"
   clauses outside the block sprint 035 ticket 002 boiled down
   (guidelines anti-pattern: justification-to-reviewer); the file is at
   0.73 comment lines per code line so it was left.

Remedy per `.claude/rules/measurement-citations.md`: find the capture
or log the number came from and cite it; otherwise rewrite the claim as
UNVERIFIED and say what would settle it. For item 3, `git add -f` the
two present artifacts (the JPEG only if it is the evidence) and drop or
repoint the absent one.
