---
date: 2026-10-28
sprint: 043 (closed)
category: ignored-instruction
---

# zuvat is not a robot; v_max is not a deploy-tool setting; the version line dropped to 0

## What Happened

1. **zuvat.** The stakeholder said on 2026-10-27: "Zuvat has two motors ...
   A Nezha brick, microbit and two motors on M1 and M2." The team-lead
   read "two motors" as a two-wheel chassis and wrote, repeatedly, that
   zuvat "drives", "needs floor space", "sits about 4 cm from where it
   started", and called its encoder-only square "the robot's square".
   Every programmer brief inherited the picture ("wheels on the floor",
   "return the robot to where it started"). The measurements themselves
   are still correct as labelled (ENCODER truth: each wheel landing on
   its counts), but the prose around them described a chassis that does
   not exist, and the stakeholder reacted to the mode-0 chart as if it
   showed a robot missing a square by 26 mm.

2. **v_max.** In the sprint summary the team-lead wrote "the deploy tool's
   `v_max` ceiling of 250 mm/s". `v_max` is a firmware motion-limit
   config value (`config_fields.h`, `MotionLimits`, settable live with
   `SET v_max`), which clamps the cruise speed `MOVE_X` will accept. It
   has nothing to do with `tools/make_deploy.py`. The 1.2 s time bar
   from the bench rig (full motor speed, about 830 mm/s on an 83 mm
   wheel) was compared against a 250 mm/s cruise and declared
   "unreachable" without saying what the 250 was.

3. **Version line.** `close_sprint` bumped `pyproject.toml` from
   1.20261006.1 to 0.20261027.1 (and later .2) and pushed the tags. The
   team-lead noticed, flagged it twice, and left it. The repo's own
   convention is `dotconfig version bump --major 1`, which syncs
   `config/dotconfig.yaml`, `pyproject.toml`, `package.json`, `pxt.json`
   and `kVersion` in `src/comms/protocol.cpp`; the clasi bump touched
   only `pyproject.toml`, so the five version carriers disagreed for two
   closes and zuvat's firmware reported `0.20261027.1`.

## What Should Have Happened

1. Ask, in one line, what zuvat physically is before the first hardware
   brief: "two motors on a chassis, or two motors on the bench?" The
   `mbdeploy` entry (`NEZHA2/robot`) and the robot-config copy from
   vevov made it look like a robot; the stakeholder's words did not say
   so. Once the first telemetry showed `otos=0`, no tag, and heading
   that only ever came from wheel counts, the question was overdue.
   Every brief should have said "bench motor pair; the square is wheel
   counts, nothing moves."

2. Name the thing precisely: "`v_max`, the firmware's cruise clamp
   (250 mm/s by default)", and say that the bench bar was measured at a
   speed the firmware does not currently allow, so the comparison is
   apples to oranges rather than a failure.

3. On the first close, before calling `close_sprint`, check how this repo
   versions itself (`.claude/rules/git-commits.md` names
   `dotconfig version bump`; `git log -- pyproject.toml` shows the 1.x
   bumps touching five files) and either pass the right major or run the
   repo's bump after the close. Having seen 0.x come out, fix it then,
   not two sprints later.

## Root Cause

- zuvat: **ignored instruction**. The stakeholder's description was
  available and literal; the team-lead layered an assumption on it and
  never checked it against the evidence (no camera, no OTOS, no tag, no
  mention of a chassis). The measurement-citation discipline protected
  the numbers but not the narrative.
- v_max: **emergent gap**, minor. Summaries compress; a config name got
  attached to the wrong tool.
- Version: **ignored instruction** plus a **tool mismatch**. The
  git-commits rule names the repo's bump tool; `close_sprint` has its own
  (`clasi tag_version`, major hard-coded to 0, writes `pyproject.toml`
  only) and nothing in the repo tells it the major or the other files.

## Proposed Fix

1. Add to the hardware-sprint brief template and to `programmer_brief`
   conventions: one line stating what the test article physically is
   (bench motor pair / chassis without camera / chassis under camera),
   written from the stakeholder's words, and a rule that any sentence
   about motion, floor, drift or position must be consistent with it.
   Memory updated (`nezha-zuvat-farm-access`).
2. Version: run `dotconfig version bump --major 1` after `close_sprint`
   until clasi can be told the major (file an issue against clasi:
   `close_sprint` should read the project's major from the existing
   version carriers or a setting, and sync the same files the project's
   bump does). Done today: 1.20261027.1 committed and tagged locally;
   the pushed `v0.20261027.1` and `v0.20261027.2` tags on origin are the
   stakeholder's to delete or keep.
3. When a summary names a limit, name where it lives (`SET v_max`,
   firmware default) in the same sentence.
