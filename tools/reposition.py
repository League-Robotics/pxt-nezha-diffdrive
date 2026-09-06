#!/usr/bin/env python3
"""Put the robot on a world point at a world heading, camera-verified.
The ONE repositioning loop in the repo (sprint 034 ticket 009).

The robot's own world frame is only as good as its seed, so this seeds
from the OVERHEAD CAMERA -- measured truth -- rather than assuming
where the robot was placed. Then it drives, then it re-measures, so the
result is verified rather than commanded.

  from reposition import Repositioner
  r = Repositioner(link, cam)
  r.go(50, 30, 180)

Repositioning is SETUP, not driving: it runs between runs, never inside
one, and it is the only way successive practice runs start from the
same place and their scores mean the same thing.

**Ordering: POSITION first, then heading, and never the other way
round.** This is the load-bearing design decision in the file, and it
came from `tour_run.place()`, the second implementation this class
absorbed. Its comment, kept verbatim in `go()` below because it is the
evidence for the design:

    An in-place pivot walks the centre of rotation a centimetre or so,
    which is enough to push the position error back over tolerance --
    so a loop that re-checks both and picks one will answer a good
    heading with another goto and undo it. Two runs started facing
    98 and 94 degrees instead of west that way.

`Repositioner.go()` used to be exactly the loop that comment warns
about: one pass that re-checked both errors on every attempt and could
issue a fresh `RUN:goto` after the heading was already correct. The
merge kept `place()`'s two-phase ordering and `go()`'s signature.
Pinned by `tests/tools/test_reposition.py`'s "98 and 94 degrees"
regression tests, which assert on what the LINK RECEIVED.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from field import require_clear_path, wrap


class Repositioner:
    """Drive the robot onto a world pose, verifying with the camera.

    `tol_cm`/`tol_deg` are the arrival tolerances. The heading one is
    worth choosing per caller: an open-loop tour turns start-heading
    error straight into corner error (leg x sin theta), so 4 deg on a
    100 cm leg is already 7 cm -- `tour_run.make_repositioner()` asks
    for 1.5 deg for exactly that reason.
    """

    def __init__(self, link, cam, tol_cm: float = 3.0,
                 tol_deg: float = 5.0) -> None:
        self.link = link
        self.cam = cam
        self.tol_cm = tol_cm
        self.tol_deg = tol_deg

    def fix(self, samples: int = 8):
        """Median camera pose (x_cm, y_cm, yaw_deg), or None -- delegates
        to tools/camlink.py's Cam.fix(), which already does exactly this
        median-of-N sampling (and, critically, already returns None once
        the stream has died rather than a frozen pre-death pose -- see
        camlink.py's stale-pose-invalidation contract)."""
        return self.cam.fix(n=samples)

    def _seed(self, pose) -> bool:
        self.link.send(f'RUN:seedxy:{pose[0]:.1f}:{pose[1]:.1f}:{pose[2]:.1f}')
        for s in self.link.lines(8):
            if s.startswith('OCAL:seeded'):
                return True
        return False

    def check_path(self, pose, x: float, y: float) -> None:
        """Pre-flight the straight leg from the MEASURED pose to
        `(x, y)` -- raises `field.PathRefused` (naming the offending
        points) if any part of it leaves the playfield margin, and
        returns quietly otherwise.

        A method rather than an inline call so that every planner this
        class absorbs keeps the gate. `tour_run.place()` carried its own
        copy of the same check until sprint 034 ticket 009 folded that
        planner in here; the gate came with it, and it is now the only
        one. The refusal must stay AHEAD of the first byte sent -- see
        `field.require_clear_path()`.
        """
        require_clear_path([(pose[0], pose[1]), (x, y)],
                           what=f'drive to ({x:.1f}, {y:.1f})')

    def go(self, x: float, y: float, heading: float, tries: int = 3,
           echo: bool = True):
        """Drive to `(x, y)`, THEN face `heading`. Returns the final
        camera pose, or None if the camera lost the robot.

        Raises `field.PathRefused` -- before sending anything at all --
        if the straight leg from where the camera says the robot IS to
        `(x, y)` leaves the playfield margin.

        Two phases, in this order, never interleaved:

        POSITION first, then heading, and never the other way round. An
        in-place pivot walks the centre of rotation a centimetre or so,
        which is enough to push the position error back over tolerance
        -- so a loop that re-checks both and picks one will answer a
        good heading with another goto and undo it. Two runs started
        facing 98 and 94 degrees instead of west that way. (That
        measurement is the evidence for this whole structure; it came
        with `tour_run.place()` when sprint 034 ticket 009 merged it in
        and must not be separated from the code it justifies --
        `.claude/rules/measurement-citations.md`.)

        So: no `RUN:goto` is ever sent after a `RUN:face`. The position
        phase runs to completion first, and the heading phase closes
        the pose from a fresh seed with nothing after it to disturb it.
        """
        # --- phase 1: position ---------------------------------------
        pose = None
        for _attempt in range(tries):
            pose = self.fix()
            if pose is None:
                return None
            derr = math.hypot(x - pose[0], y - pose[1])
            if echo:
                print(f'    at ({pose[0]:6.1f},{pose[1]:6.1f}) '
                      f'{pose[2]:7.1f}deg  -> off {derr:5.1f} cm')
            if derr <= self.tol_cm:
                break

            # Pre-flight the projected path BEFORE the seed: the seed
            # is already a command on the wire, and a run refused after
            # it has been sent has still changed the robot's world
            # frame (.claude/rules/playfield-testing.md).
            self.check_path(pose, x, y)

            # Seed the robot with what the camera SEES, so its own
            # world frame matches the field before it plans anything.
            self._seed(pose)
            self.link.send(f'RUN:goto:{x:.1f}:{y:.1f}')
            self._wait('GOTO:end', 45)

        # --- phase 2: heading, LAST, from a fresh seed ---------------
        for _attempt in range(tries):
            pose = self.fix()
            if pose is None:
                return None
            herr = wrap(heading - pose[2])
            if echo:
                print(f'    at ({pose[0]:6.1f},{pose[1]:6.1f}) '
                      f'{pose[2]:7.1f}deg  -> off {herr:+6.1f} deg')
            if abs(herr) <= self.tol_deg:
                break
            self._seed(pose)
            self.link.send(f'RUN:face:{heading:.1f}')
            self._wait('FACE:end', 25)
        return self.fix()

    def _wait(self, marker: str, secs: float) -> bool:
        for s in self.link.lines(secs):
            if s.startswith(marker):
                return True
        return False
