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

Run under the project's own venv (not the AprilTags one -- the camera
runs as its own subprocess via tools/camproc.py, so this file only
ever needs pyserial):
  python3 tools/pivot_truth.py [--reps 3]
"""
import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robotlink import open_link
from camproc import Cam
from field import turn_total, wrap

# Below this, the camera saw no rotation at all and `gyro / camera` is
# not merely noisy but undefined -- see gyro_over_camera().
NO_ROTATION = 0.5   # [deg]


def gyro_over_camera(gyro: float, camera: float) -> float | None:
    """`gyro / camera` for one pivot, or `None` when the camera saw no
    rotation (`abs(camera) < NO_ROTATION`). Both arguments are total
    unwrapped turns [deg].

    The `None` case is not a rounding curiosity. "The camera saw no
    rotation while the robot reported a turn" is exactly the
    robot-is-switched-OFF signature `.claude/rules/playfield-testing.md`
    says to check FIRST ("The robot is OFF -- check this first"):
    odometry integrates encoder deltas and happily reports the full
    commanded turn on a robot with no motor power, and only an external
    instrument -- this camera -- can contradict it. Dividing by it used
    to raise `ZeroDivisionError` and lose the whole run's report at the
    exact moment the run had the most to say.
    """
    if abs(camera) < NO_ROTATION:
        return None
    return gyro / camera


def _yaw_mark(cam):
    """(total unwrapped yaw turned so far, latest (x, y, yaw) pose) --
    computed fresh from `cam`'s own recorded samples each call (cheap
    enough for a session's worth of pivot samples), mirroring the old
    CamStream.mark()'s shape so the rest of this file needs no other
    change. `cam` is a tools/camproc.py Cam; its samples are already
    `(t, x_cm, y_cm, yaw_deg)`.
    """
    with cam.lock:
        samples = list(cam.samples)
    total, prev = 0.0, None
    for _, _, _, yaw in samples:
        if prev is not None:
            total += wrap(yaw - prev)
        prev = yaw
    return total, cam.latest


def otos_fix(link):
    for s in link.send_until('RUN:fix', 'OCAL:now', tries=2, wait=5.0,
                             echo=False):
        if s.startswith('OCAL:now'):
            p = s.split(':')
            return int(p[2]) / 10.0, int(p[3]) / 10.0, int(p[4]) / 100.0
    return None


def send_pivot(link, deg):
    """Command a relative pivot of `deg` and wait for it to finish.

    RUN:pivot:<deg> takes an arbitrary signed degree value directly --
    unlike the old dead numeric PIVOT_VERB table, there is no fixed set
    of supported angles to look up.
    """
    return link.send_until(f'RUN:pivot:{int(deg)}', 'GAP:', tries=1,
                           wait=abs(deg) / 45.0 + 12.0, echo=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help="drive the robot over its WiFi TCP server instead of the "
             "radio relay (the default carrier since 2026-09-02)")
    ap.add_argument('--robot', default='vevov',
        help="board name -- resolves the zavaz relay's channel/group "
             "(field_calibration.json's override, else derived from the "
             "name) when driving over --radio; ignored for --wifi")
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--tag', type=int, default=53)
    a = ap.parse_args()

    cam = Cam(tag=a.tag)
    if cam.latest is None:
        raise SystemExit(f'camera cannot see tag {a.tag}')
    link = open_link(radio=not a.wifi, wifi=a.wifi, robot=a.robot)

    print(f"{'cmd':>6} {'CAMERA':>8} {'gyro':>8} {'cam/cmd':>8}"
          f" {'gyro/cam':>9} {'drift cm':>9}  verdict")
    results = []
    for _rep in range(a.reps):
        for commanded in (180.0, -180.0):
            t0, r0 = _yaw_mark(cam)
            o0 = otos_fix(link)
            if r0 is None or o0 is None:
                print('  lost a reading -- skipping')
                continue

            send_pivot(link, commanded)
            time.sleep(1.5)

            t1, r1 = _yaw_mark(cam)
            o1 = otos_fix(link)
            if r1 is None or o1 is None:
                print('  lost a reading after the pivot -- skipping')
                continue

            camera = t1 - t0    # [deg] total unwrapped camera yaw
            # field.turn_total() unwraps the OTOS delta onto the
            # revolution the command names, uniformly for every angle --
            # so the +/-180 wrap-boundary special case that used to sit
            # here (pick whichever of gyro, gyro +/- 360 lands nearest
            # the camera) is gone, along with its dependence on the
            # camera being trustworthy to disambiguate the gyro.
            gyro = turn_total(commanded, o1[2] - o0[2])     # [deg]
            # r0/r1 are camproc.Cam's (x_cm, y_cm, yaw_deg) -- x, y are
            # indices 0, 1 (NOT 1, 2 -- that was the old CamStream's
            # (yaw, x, y) order this file used to read).
            drift = math.hypot(r1[0] - r0[0], r1[1] - r0[1])
            ok = abs(camera - commanded) < 20.0
            results.append((commanded, camera, gyro, drift, ok))
            ratio = gyro_over_camera(gyro, camera)
            if ratio is None:
                ratio_text, verdict = '      n/a', 'camera saw no rotation'
            else:
                ratio_text, verdict = f'{ratio:9.3f}', 'ok' if ok else 'FAILED'
            print(f"{commanded:6.0f} {camera:8.1f} {gyro:8.1f}"
                  f" {camera / commanded:8.3f} {ratio_text}"
                  f" {drift:9.1f}  {verdict}")

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
        still = [r for r in results
                 if gyro_over_camera(r[2], r[1]) is None]
        if still:
            print(f"\n{len(still)}/{len(results)} pivots: THE CAMERA SAW NO "
                  f"ROTATION while the gyro reported "
                  f"{[round(r[2], 1) for r in still]} deg.")
            print("Check the ROBOT IS SWITCHED ON before suspecting slip, "
                  "stiction or the OTOS -- odometry integrates encoder "
                  "deltas and reports the full commanded turn on a robot "
                  "with no motor power, and only an external instrument "
                  "can tell. See .claude/rules/playfield-testing.md, "
                  "'The robot is OFF -- check this first'.")
        if bad:
            print(f"drift on failed pivots: "
                  f"{[round(r[3],1) for r in bad]} cm "
                  f"(a pure pivot should hold the centre still)")


if __name__ == '__main__':
    main()
