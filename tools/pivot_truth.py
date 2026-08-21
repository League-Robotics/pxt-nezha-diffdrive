#!/usr/bin/env python3
"""Ground-truth pivots against the overhead camera.

Answers the question the OTOS cannot answer about itself: when a
commanded +180 produced a measured -97 earlier, was that the ROBOT
misbehaving or the SENSOR mis-reporting? The camera is independent of
both, and it is calibrated, so it also says how far the centre drifted.

Runs the same commanded pivot several times, alternating direction, and
prints camera / gyro / wheels side by side. Camera yaw is sampled
CONTINUOUSLY and unwrapped, because a single before/after pair cannot
resolve a 180 deg turn -- it lands exactly on the wrap boundary.

Run under the AprilTags venv (it has the aprilcam package):
  /Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3 \
      tools/pivot_truth.py [--reps 3]
"""
import argparse
import math
import subprocess
import sys
import threading
import time

sys.path.insert(0, '/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/tools')
from robotlink import open_link

VENV_PY = '/Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3'
CAMLINK = '/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/tools/camlink.py'


class CamStream:
    """Camera samples from a subprocess (see camlink._stream).

    aprilcam and pyserial live in different interpreters here, so the
    camera runs as its own process and streams `yaw x y` lines.
    """

    def __init__(self, tag=53, hz=20.0):
        self.p = subprocess.Popen(
            [VENV_PY, CAMLINK, '--tag', str(tag), '--hz', str(hz)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            bufsize=1)
        self.latest = None
        self.total = 0.0          # unwrapped cumulative yaw [deg]
        self._prev = None
        self._lock = threading.Lock()
        threading.Thread(target=self._pump, daemon=True).start()
        for _ in range(50):       # wait for the first sample
            if self.latest is not None:
                break
            time.sleep(0.1)

    def _pump(self):
        for line in self.p.stdout:
            try:
                yaw, x, y = (float(v) for v in line.split())
            except ValueError:
                continue
            with self._lock:
                if self._prev is not None:
                    self.total += wrap(yaw - self._prev)
                self._prev = yaw
                self.latest = (yaw, x, y)

    def mark(self):
        with self._lock:
            return self.total, self.latest

    def close(self):
        self.p.terminate()

PIVOT_VERB = {180: 4, -180: 5, 360: 2}


def wrap(d):
    while d <= -180.0:
        d += 360.0
    while d > 180.0:
        d -= 360.0
    return d


def otos_fix(link):
    for s in link.send_until('RUN:10', 'OCAL:now', tries=2, wait=5.0,
                             echo=False):
        if s.startswith('OCAL:now'):
            p = s.split(':')
            return int(p[2]) / 10.0, int(p[3]) / 10.0, int(p[4]) / 100.0
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--tag', type=int, default=53)
    a = ap.parse_args()

    cam = CamStream(a.tag)
    if cam.latest is None:
        raise SystemExit(f'camera cannot see tag {a.tag}')
    link = open_link(radio=True)

    print(f"{'cmd':>6} {'CAMERA':>8} {'gyro':>8} {'cam/cmd':>8}"
          f" {'gyro/cam':>9} {'drift cm':>9}  verdict")
    results = []
    for rep in range(a.reps):
        for commanded in (180.0, -180.0):
            t0, r0 = cam.mark()
            o0 = otos_fix(link)
            if r0 is None or o0 is None:
                print('  lost a reading -- skipping')
                continue

            link.send_until(f'RUN:{PIVOT_VERB[int(commanded)]}', 'GAP:',
                            tries=1, wait=abs(commanded) / 45.0 + 12.0,
                            echo=False)
            time.sleep(1.5)

            t1, r1 = cam.mark()
            o1 = otos_fix(link)
            if r1 is None or o1 is None:
                print('  lost a reading after the pivot -- skipping')
                continue

            camdeg = t1 - t0
            gyro = wrap(o1[2] - o0[2]) if abs(commanded) < 360 else None
            if gyro is None:
                gyro = o1[2] - o0[2]
            # A 180 deg turn sits on the wrap boundary: pick the branch
            # nearest what the camera actually saw.
            if abs(commanded) == 180.0:
                for cand in (gyro, gyro + 360.0, gyro - 360.0):
                    if abs(cand - camdeg) < abs(gyro - camdeg):
                        gyro = cand
            drift = math.hypot(r1[1] - r0[1], r1[2] - r0[2])
            ok = abs(camdeg - commanded) < 20.0
            results.append((commanded, camdeg, gyro, drift, ok))
            print(f"{commanded:6.0f} {camdeg:8.1f} {gyro:8.1f}"
                  f" {camdeg / commanded:8.3f} {gyro / camdeg:9.3f}"
                  f" {drift:9.1f}  {'ok' if ok else 'FAILED'}")

    link.close()
    cam.close()

    if results:
        good = [r for r in results if r[4]]
        bad = [r for r in results if not r[4]]
        print(f"\n{len(good)}/{len(results)} pivots landed within 20 deg "
              f"of commanded")
        for label, sel in (('+180', [r for r in results if r[0] > 0]),
                           ('-180', [r for r in results if r[0] < 0])):
            if sel:
                okn = sum(1 for r in sel if r[4])
                print(f"  {label}: {okn}/{len(sel)} ok, camera saw "
                      f"{[round(r[1]) for r in sel]}")
        gc = [r[2] / r[1] for r in results if abs(r[1]) > 30]
        if gc:
            print(f"\ngyro/camera = {sum(gc)/len(gc):.3f} over {len(gc)} "
                  f"pivots -- 1.0 means the OTOS reports the truth")
        if bad:
            print(f"drift on failed pivots: "
                  f"{[round(r[3],1) for r in bad]} cm "
                  f"(a pure pivot should hold the centre still)")


if __name__ == '__main__':
    main()
