#!/usr/bin/env python3
"""Put the robot on a world point at a world heading, camera-verified.

The robot's own world frame is only as good as its seed, so this seeds
from the OVERHEAD CAMERA -- measured truth -- rather than assuming
where the robot was placed. Then it drives, then it re-measures and
repeats until the camera agrees, so the result is verified rather than
commanded.

  from reposition import Repositioner
  r = Repositioner(link, cam)
  r.go(50, 30, 180)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from field import require_clear_path, wrap


class Repositioner:
    def __init__(self, link, cam, tol_cm=3.0, tol_deg=5.0):
        self.link = link
        self.cam = cam
        self.tol_cm = tol_cm
        self.tol_deg = tol_deg

    def fix(self, samples=8):
        """Median camera pose (x_cm, y_cm, yaw_deg), or None -- delegates
        to tools/camproc.py's Cam.fix(), which already does exactly this
        median-of-N sampling (and, critically, already returns None once
        the stream has died rather than a frozen pre-death pose -- see
        camproc.py's stale-pose-invalidation contract)."""
        return self.cam.fix(n=samples)

    def _seed(self, pose):
        self.link.send(f'RUN:seedxy:{pose[0]:.1f}:{pose[1]:.1f}:{pose[2]:.1f}')
        for s in self.link.lines(8):
            if s.startswith('OCAL:seeded'):
                return True
        return False

    def check_path(self, pose, x, y):
        """Pre-flight the straight leg from the MEASURED pose to
        `(x, y)` -- raises `field.PathRefused` (naming the offending
        points) if any part of it leaves the playfield margin, and
        returns quietly otherwise.

        A method rather than an inline call so that every planner this
        class absorbs keeps the gate: `tour_run.place()` does the same
        check today and merges in here next (sprint 034 ticket 009).
        The refusal must stay AHEAD of the first byte sent -- see
        `field.require_clear_path()`.
        """
        require_clear_path([(pose[0], pose[1]), (x, y)],
                           what=f'drive to ({x:.1f}, {y:.1f})')

    def go(self, x, y, heading, tries=3, echo=True):
        """Drive to (x, y) then face `heading`. Returns the final camera
        pose, or None if the camera lost the robot.

        Raises `field.PathRefused` -- before sending anything at all --
        if the straight leg from where the camera says the robot IS to
        `(x, y)` leaves the playfield margin.
        """
        for _attempt in range(tries):
            pose = self.fix()
            if pose is None:
                return None
            derr = math.hypot(x - pose[0], y - pose[1])
            herr = wrap(heading - pose[2])
            if echo:
                print(f'    at ({pose[0]:6.1f},{pose[1]:6.1f}) '
                      f'{pose[2]:7.1f}deg  -> off {derr:5.1f} cm, '
                      f'{herr:+6.1f} deg')
            if derr <= self.tol_cm and abs(herr) <= self.tol_deg:
                return pose

            # Pre-flight the projected path BEFORE the seed: the seed
            # is already a command on the wire, and a run refused after
            # it has been sent has still changed the robot's world
            # frame (.claude/rules/playfield-testing.md).
            self.check_path(pose, x, y)

            # Seed the robot with what the camera SEES, so its own
            # world frame matches the field before it plans anything.
            self._seed(pose)

            if derr > self.tol_cm:
                self.link.send(f'RUN:goto:{x:.1f}:{y:.1f}')
                self._wait('GOTO:end', 45)
                pose = self.fix()
                if pose is None:
                    return None
                self._seed(pose)

            herr = wrap(heading - pose[2])
            if abs(herr) > self.tol_deg:
                self.link.send(f'RUN:face:{heading:.1f}')
                self._wait('FACE:end', 25)
        return self.fix()

    def _wait(self, marker, secs):
        for s in self.link.lines(secs):
            if s.startswith(marker):
                return True
        return False
