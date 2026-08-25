---
status: in-progress
sprint: '005'
tickets:
- 005-003
---

# Tools: stale venvs, swallowed camera errors, and seven copied Cam scaffolds

Priority: **Medium** — code review 2026-08-23, R-24 + R-26 (PY-02 + PY-04 +
PY-05 + MOD-02; CONFIRMED, import probe re-run during verification).

Aligns with sprint 005 (bench retrofit): the planned `tlm.py`
consolidation covers the telemetry stream but none of this.

1. **Stale venv (R-24)**: six spawn sites hardcode the AprilTags/.venv
   interpreter, where `import aprilcam` now fails (the pipx interpreter
   works; `tour_run.py` alone has the correct one — a 2-way fork). Every
   spawn uses `stderr=DEVNULL`; `tour_watch.py:180-182` checks `cam.err`
   once at +1.5 s. Net: camera-less sessions recorded silently as "robot
   invisible".
2. **Swallowed errors + stale pose (R-26a)**: `tour_run.py:64` discards
   camlink's `ERR` lines (camlink.py:112 emits them; the class has no
   `err` field); `latest` is never invalidated and `fix()` ignores
   timestamps, so a mid-session stream death lets `place()` re-seed the
   robot's world frame from a frozen pose via `RUN:seedxy`.
3. **Scaffold copying (R-26b)**: 7 copied `Cam` wrappers — bypassing the
   shared `Cam` already in `camlink.py:48` — with two incompatible
   `latest` tuple orders (`tour_run.py:71` `(x,y,yaw)` vs
   `tour_practice.py:84` `(yaw,x,y)`); 8 `wrap()`s; 6 playfield-constant
   blocks; 4 corner scorers whose outputs already disagree (console
   "SW 31.3cm" vs chart "SW=unobserved" for the same run).

## What to do

- `tools/camproc.py` (spawn + venv resolution + ERR surfacing + staleness)
  and `tools/field.py` (playfield constants, wrap, scoring) beside the
  planned `tlm.py`; route all tools through robotlink/camlink.
- Resolve the interpreter once (env var or config), never hardcoded.
- Also sweep in the tool Minors: `make_deploy.py`'s `endswith('test.ts')`
  filter silently excluding testrig.ts (PY-06), unguarded rotation divides
  (PY-08).
