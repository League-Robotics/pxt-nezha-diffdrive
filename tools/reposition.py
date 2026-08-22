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
import time


def wrap(d):
    while d <= -180.0:
        d += 360.0
    while d > 180.0:
        d -= 360.0
    return d


class Repositioner:
    def __init__(self, link, cam, tag=53, tol_cm=3.0, tol_deg=5.0):
        self.link = link
        self.cam = cam
        self.tag = tag
        self.tol_cm = tol_cm
        self.tol_deg = tol_deg

    def fix(self, samples=8):
        """Median camera pose (x_cm, y_cm, yaw_deg), or None."""
        vals = []
        for _ in range(samples):
            r = self.cam.read(self.tag)
            if r is not None:
                vals.append(r)
            time.sleep(0.08)
        if not vals:
            return None
        med = lambda i: sorted(v[i] for v in vals)[len(vals) // 2]
        return med(1), med(2), med(0)

    def _seed(self, pose):
        self.link.send(f'RUN:seedxy:{pose[0]:.1f}:{pose[1]:.1f}:{pose[2]:.1f}')
        for s in self.link.lines(8):
            if s.startswith('OCAL:seeded'):
                return True
        return False

    def go(self, x, y, heading, tries=3, echo=True):
        """Drive to (x, y) then face `heading`. Returns the final camera
        pose, or None if the camera lost the robot."""
        for attempt in range(tries):
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
