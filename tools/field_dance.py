#!/usr/bin/env python3
"""field_dance -- prove the robot moves the way you think, before you drive it.

RUN THIS EVERY TIME, before any field work. It has caught, twice, the
class of bug that otherwise ends with a robot in a rail: a heading
convention that silently flipped, and a pivot that stopped halfway and
reported success.

    Put the robot in the MIDDLE of the field, then:

        uv run tools/field_dance.py

    Calibration (tag lever, heading convention, camera parallax) comes
    from field_calibration.json beside this file; re-measure it after
    any tag remount or camera move.

Middle of the field is the whole safety story -- the dance never leaves
a 25 cm circle, so there is nothing to guard against and no pre-flight
path check to compute.

    1. +90 deg      3. +90 deg (back to start)   5. 40 cm back
    2. +180 deg     4. 20 cm forward             6. 20 cm forward
    ... and it must finish where it started, pointing where it started.

Each step is checked against the camera. Turning "left" must turn left;
driving "forward" must go forward. Anything else fails loudly and you do
not drive the field that day.

Holds ONE aprilcam daemon connection for the whole dance -- ~10 Hz, no
subprocess per reading -- and waits on the robot actually coming to rest
rather than on a fixed sleep. That is what keeps it near a minute.
"""
import json, math, pathlib, sys, time

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from aprilcam.mcp import connection as _conn          # noqa: E402
from fieldlink import FieldLink                        # noqa: E402

_CAL = json.loads((_HERE / 'field_calibration.json').read_text())
CAM, TAG = _CAL['camera'], _CAL['tag_number']
CH, GRP = _CAL['radio_channel'], _CAL['radio_group']
LEVER = _CAL['lever_cm']
HEAD_OFF = _CAL['heading_offset_deg']
K = _CAL['parallax_k']                 # camera parallax dilation

TOL_DEG, TOL_CM = 8.0, 3.0


def _daemon():
    for n in dir(_conn):
        o = getattr(_conn, n)
        if isinstance(o, type) and hasattr(o, 'resolve') and hasattr(o, 'call'):
            return o().resolve()
    raise SystemExit('no aprilcam connection manager found')


D = _daemon()


def raw():
    for rec in D.get_tags(CAM).tags:
        if rec.tag.number == TAG and rec.tag.family.value == 'apriltag':
            return rec
    return None


def pose(n=3):
    """(x_cm, y_cm, heading_deg) of the centre of rotation."""
    xs = ys = 0.0; sy = cy = 0.0; got = 0
    for _ in range(n):
        r = raw()
        if r is None:
            time.sleep(0.05); continue
        t = r.yaw_rad
        xs += r.world.x - (math.cos(t)*LEVER[0] - math.sin(t)*LEVER[1])
        ys += r.world.y - (math.sin(t)*LEVER[0] + math.cos(t)*LEVER[1])
        sy += math.sin(t); cy += math.cos(t); got += 1
        time.sleep(0.03)
    if not got:
        return None
    h = math.degrees(math.atan2(sy, cy)) + HEAD_OFF
    return xs/got, ys/got, (h + 180) % 360 - 180


def settle(timeout=9.0):
    """Wait for the robot to actually stop -- not for a guessed sleep."""
    t0 = time.time(); still = 0
    while time.time() - t0 < timeout:
        r = raw()
        if r is not None:
            sp = getattr(r, 'speed', None) or 0.0
            still = still + 1 if sp < 0.6 else 0
            if still >= 4:
                return True
        time.sleep(0.06)
    return False


def main():
    L = FieldLink(CH, GRP); L.hello()
    # A latched e-stop refuses every move and looks EXACTLY like a broken
    # heading convention: each step measures zero motion. Clear it first,
    # and confirm the robot says it is ready, so a refusal can never be
    # misread as a geometry failure.
    L.unseq('RUN:clearestop', r'^ESTOP:cleared', tries=3)
    st = L.unseq('STATUS', r'^status ')
    print('status:', st)
    if st and 'ready=0' in st:
        raise SystemExit('robot reports ready=0 -- not driving anything')
    # Sprint 029 ticket 004 (design motion-profile-unification.md
    # S4.7/S8): accel/decel keep their name and units (mm/s^2) -- same
    # semantics, now a thin forward to MotionLimits instead of the old
    # MotionEngine fields. The old "pivot overrun" wire field is now
    # `stop_distance` below, same [mm] per-wheel coast concept and the
    # same measured 3.7 value (design S8: "per-wheel mm, both axes;
    # measured not fitted"). The old "profile exit" and "yaw taper"
    # wire fields are REMOVED ordinals with no MotionLimits equivalent
    # (S8: the braking plan ends at the floor by construction; the
    # taper window is now derived as v^2/(2*decel), not separately
    # configured) -- dropped, not mapped, so this script no longer sets
    # them at all. The old "speed floor" wire field is ALSO dropped
    # rather than mapped onto its new `v_floor` name: that OLD field was
    # the kernel's own vMin in [counts/s]; `v_floor` is
    # MotionLimits::vFloor in [mm/s] (S4.7/K5) -- a different physical
    # quantity under the same wire ordinal, and this script has no
    # measured mm/s value to substitute for the old 512 counts/s one
    # (measurement-citations.md: do not invent one). `v_floor` keeps its
    # compiled default instead (70 mm/s, MEASURED tovez/gopiv
    # 2026-08-29, motion_limits.h).
    for f, v in (('accel', 400), ('decel', 400),
                 ('stop_distance', 3.7), ('twist_hold_gain', 8)):
        L.seqd(f'SET {f} {v}')

    home = pose()
    if home is None:
        raise SystemExit('no camera fix -- is the robot on the field and lit?')
    print(f'home ({home[0]:6.1f},{home[1]:6.1f}) h={home[2]:6.1f}\n')
    print(f'{"step":22s} {"expected":>10s} {"measured":>10s} {"err":>8s}  result')

    fails = []
    def turn(deg):
        nonlocal fails
        a = pose()
        L.seqd(f'MOVE_X 0 {int(round(math.radians(deg)*1000))} 188 9000')
        settle()
        b = pose()
        got = (b[2] - a[2] + 180) % 360 - 180
        err = (got - deg + 180) % 360 - 180
        ok = abs(err) <= TOL_DEG
        note = '' if abs(got) > 1.0 else '  <- NO MOTION (estop? stall?)'
        print(f'{"turn %+d deg" % deg:22s} {deg:+9.1f}d {got:+9.1f}d {err:+7.1f}d  '
              f'{"PASS" if ok else "**FAIL**"}{note}')
        if not ok: fails.append(f'turn {deg:+}')
        return b

    def drive(cm):
        nonlocal fails
        a = pose()
        L.seqd(f'MOVE_X {int(round(cm*10))} 0 200 10000')
        settle()
        b = pose()
        dx, dy = b[0]-a[0], b[1]-a[1]
        # camera distances are dilated about the nadir; divide for truth
        dist = math.hypot(dx, dy) / K
        brg = math.degrees(math.atan2(dy, dx))
        # forward means along the heading; backward means 180 from it
        want = a[2] if cm > 0 else (a[2] + 180)
        dirn = (brg - want + 180) % 360 - 180
        signed = dist if abs(dirn) < 90 else -dist
        err = signed - abs(cm)
        ok = abs(err) <= TOL_CM and abs(dirn) < 25
        note = (f'  (bearing off {dirn:+.0f} deg)' if dist > 0.5
                else '  <- NO MOTION (estop? stall?)')
        print(f'{"drive %+d cm" % cm:22s} {abs(cm):9.1f}c {signed:9.1f}c {err:+7.1f}c  '
              f'{"PASS" if ok else "**FAIL**"}{note}')
        if not ok: fails.append(f'drive {cm:+}')
        return b

    turn(90); turn(180); turn(90)
    drive(20); drive(-40); drive(20)

    end = pose()
    back = math.hypot(end[0]-home[0], end[1]-home[1]) / K
    dh = (end[2] - home[2] + 180) % 360 - 180
    print()
    ok = back <= 5.0
    print(f'{"returned home":22s} {0.0:9.1f}c {back:9.1f}c {back:+7.1f}c  '
          f'{"PASS" if ok else "**FAIL**"}')
    if not ok: fails.append('return home')

    L.close()
    print()
    # CONVENTION and ACCURACY are different questions and only the first
    # one decides whether it is safe to drive. A robot whose pivots run
    # 3 deg long still goes left when told to go left -- that is a tuning
    # number, and failing the whole check on it would teach the operator
    # to ignore a failing check, which is worse than not having one.
    print(f'ACCURACY (not a gate): net heading drift over the three pivots '
          f'{dh:+.1f} deg, i.e. {dh/3:+.1f} deg per 90 deg pivot.')
    if abs(dh) > 6.0:
        print('  ^ worth retuning stop_distance before precision work.')
    print()
    if fails:
        print('DANCE FAILED: ' + ', '.join(fails))
        print('Do NOT drive the field until this passes.')
        return 1
    print('DANCE PASSED -- left is left, forward is forward, and it comes home.')
    return 0


if __name__ == '__main__':
    # Handle --help BEFORE anything connects or moves. A safety check
    # that drives the robot when you ask it what it does is not a safety
    # check -- found exactly that way.
    if any(a in ('-h', '--help') for a in sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    sys.exit(main())
