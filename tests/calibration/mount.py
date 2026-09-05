"""Tag mount calibration: where the tag sits on the robot, and which way.

After a tag is (re)mounted, the daemon must be told the tag's position
relative to the robot's centre of rotation (mount_x forward, mount_y
left, in cm), its height (mount_z, drives the parallax correction) and
its yaw (the fixed -90 deg AprilCam convention plus the physical mount
residual). This program measures all of it from in-place pivots and one
forward probe, the 2026-09-02 method (captures/vevov-cal-20260902):

  1. register a PROVISIONAL mount: (0, 0, mount_z, -pi/2) -- the daemon
     then reports the parallax-corrected TAG position and the robot
     heading;
  2. pivot in place (+-90 deg, N times), taking a rest fix at every stop;
     the tag positions P_i and headings h_i satisfy P_i = C + R(h_i) m,
     which is linear in the centre C and the mount m -- least squares;
  3. register the solved mount and pivot again: the reported CENTRE must
     now stay put (drift per pivot well under 1 cm) -- the verification;
  4. drive forward `--probe` mm: the bearing of the centre's displacement
     minus the reported heading is the mount's yaw residual; register it.

With --write the result goes into tools/field_calibration.json (the
calibration of record) and the daemon is registered from it.

  uv run python tests/calibration/calibrate.py mount --robot vevov --wifi vevov --mount-z 12.4 --camera hd-usb-camera --field-cm 110 70 --margin 15 --write
"""
import argparse
import json
import math
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import turn_calibration as tc  # noqa: E402

CAL_FILE = pathlib.Path(__file__).resolve().parents[2] / 'tools' / 'field_calibration.json'
CAMLINK = pathlib.Path(__file__).resolve().parents[2] / 'tools' / 'camlink.py'


def register(tag, family, mx, my, mz, yaw_rad):
    # register_tag takes (TagId, MountParameters) -- the same call shape
    # tools/camlink.py uses. It once took loose mount_* keywords; that
    # signature is gone (TypeError on the installed build, 2026-09-05).
    from aprilcam.mcp.connection import ConnectionManager
    from aprilcam import types as dc
    D = ConnectionManager().resolve()
    return D.register_tag(
        dc.TagId(family=dc.TagFamily(family), number=tag),
        dc.MountParameters(size_cm=None, mount_x=mx, mount_y=my, mount_z=mz, mount_yaw_rad=yaw_rad),
    )


def solve_mount(poses):
    """poses: [(x, y, heading_deg)] of the TAG at rest under a (0,0) mount.
    Least squares for centre C and mount m (robot frame) in
    P = C + R(h) m. Returns (mx, my, cx, cy, rms_mm, per_pose_centres)."""
    import numpy as np
    A, b = [], []
    for x, y, h in poses:
        c, s = math.cos(math.radians(h)), math.sin(math.radians(h))
        A.append([1, 0, c, -s]); b.append(x)
        A.append([0, 1, s, c]); b.append(y)
    A, b = np.array(A), np.array(b)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, mx, my = (float(v) for v in sol)
    res = A @ sol - b
    rms = math.sqrt(float((res ** 2).mean())) * 10.0
    centres = []
    for x, y, h in poses:
        c, s = math.cos(math.radians(h)), math.sin(math.radians(h))
        centres.append((x - (c * mx - s * my), y - (s * mx + c * my)))
    return mx, my, cx, cy, rms, centres


def wait_done(link, tid, timeout=12.0):
    end = time.time() + timeout
    st = {}
    while time.time() < end:
        st = link.status()
        if st.get('done') == str(tid):
            return st
        time.sleep(0.3)
    return st


def pivot(link, cam, deg):
    tid, ack = link.seqd(f'MOVE_X 0 {int(round(math.radians(deg) * 1000))} 0 8000', wait=3.0)
    if not ack:
        return None
    wait_done(link, tid)
    cam.settle(timeout=8.0)
    time.sleep(0.8)
    return cam.fix()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot', required=True)
    ap.add_argument('--host'); ap.add_argument('--port', type=int)
    ap.add_argument('--wifi', metavar='NAME|IP')
    ap.add_argument('--radio', action='store_true')
    ap.add_argument('--tag', type=int)
    ap.add_argument('--family', default='apriltag')
    ap.add_argument('--camera', default=None)
    ap.add_argument('--field-cm', type=float, nargs=2, metavar=('W', 'H'), default=None)
    ap.add_argument('--mount-z', type=float, required=True, help='tag height above the field [cm]')
    ap.add_argument('--pivots', type=int, default=8, help='alternating +-90 pivots for the solve')
    ap.add_argument('--probe', type=int, default=300, help='forward probe [mm] for the yaw residual (0 = skip)')
    ap.add_argument('--face', type=float, default=None, help='pivot to this heading [deg] before the probe (e.g. 0 = east, away from other robots)')
    ap.add_argument('--margin', type=float, default=tc.SAFE_MARGIN)
    ap.add_argument('--write', action='store_true', help='update tools/field_calibration.json and register from it')
    ap.add_argument('--out', default='reports/mount')
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.camera:
        tc.CAM = a.camera
    if a.field_cm:
        tc.FIELD_X, tc.FIELD_Y = a.field_cm[0] / 2.0, a.field_cm[1] / 2.0
    tag = a.tag or tc.TAGS.get(a.robot)
    if tag is None:
        raise SystemExit(f'no tag known for {a.robot}; pass --tag')
    log = {'robot': a.robot, 'tag': tag, 'mount_z': a.mount_z, 'camera': tc.CAM}

    # 1. provisional mount: tag position, robot heading
    r = register(tag, a.family, 0.0, 0.0, a.mount_z, -math.pi / 2)
    print(f'provisional mount registered (0, 0, {a.mount_z}, -90 deg): {r}')
    time.sleep(1.0)
    link, where = tc.open_link(a)
    print(f'link: {where}'); print(f'robot: {link.hello()}'); print(f'status: {link.status()}')
    tc.lights_on()
    cam = tc.Camera(tag, 0.0)
    p = cam.fix()
    if p is None:
        raise SystemExit(f'camera {tc.CAM} does not see tag {tag}')
    bad = tc.check_safe(p, a.margin)
    if bad:
        raise SystemExit(f'STOP: {bad}')
    print(f'tag at ({p[0]:.2f}, {p[1]:.2f}) heading {p[2]:.1f}')

    # 2. pivots with rest fixes
    poses = [p]
    for i in range(a.pivots):
        deg = 90 if i % 2 == 0 else -90
        tc.lights_on()
        q = pivot(link, cam, deg)
        if q is None:
            print(f'  pivot {i + 1} {deg:+d}: no fix / unacked'); continue
        poses.append(q)
        print(f'  pivot {i + 1} {deg:+d}: tag ({q[0]:.2f}, {q[1]:.2f}) heading {q[2]:.1f}')
    if len(poses) < 4:
        raise SystemExit('too few rest poses to solve')
    mx, my, cx, cy, rms, centres = solve_mount(poses)
    print(f'\nsolved mount (robot frame): x {mx:+.2f} cm forward, y {my:+.2f} cm left; centre ({cx:.2f}, {cy:.2f}); residual rms {rms:.1f} mm')
    print('implied centre per pose: ' + ' '.join(f'({c[0]:.1f},{c[1]:.1f})' for c in centres))
    log.update({'poses_provisional': poses, 'mount_x': round(mx, 3), 'mount_y': round(my, 3), 'centre': [cx, cy], 'rms_mm': round(rms, 2)})

    # 3. register the solved mount, verify the centre stays put
    register(tag, a.family, mx, my, a.mount_z, -math.pi / 2)
    time.sleep(1.0)
    v = [cam.fix()]
    for i in range(4):
        q = pivot(link, cam, 90 if i % 2 == 0 else -90)
        if q:
            v.append(q)
    drifts = [math.hypot(v[i + 1][0] - v[i][0], v[i + 1][1] - v[i][1]) for i in range(len(v) - 1)]
    print(f'verification: centre drift per pivot {" ".join(f"{d:.2f}" for d in drifts)} cm (mean {sum(drifts) / len(drifts):.2f})')
    log.update({'verify_poses': v, 'verify_drift_cm': drifts})

    # 4. yaw residual from a forward probe
    residual = 0.0
    if a.probe:
        if a.face is not None:
            for _ in range(3):
                q = cam.fix(); turn = tc.wrap(a.face - q[2])
                if abs(turn) < 2:
                    break
                pivot(link, cam, turn)
        p0 = cam.fix()
        end = (p0[0] + a.probe / 10.0 * math.cos(math.radians(p0[2])), p0[1] + a.probe / 10.0 * math.sin(math.radians(p0[2])), p0[2])
        bad = tc.check_safe(end, a.margin)
        if bad:
            print(f'probe skipped: projected end {bad}')
        else:
            tid, ack = link.seqd(f'MOVE_X {a.probe} 0 0 8000', wait=3.0)
            wait_done(link, tid); time.sleep(1.2)
            p1 = cam.fix()
            bearing = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 10.0
            residual = tc.wrap(bearing - p0[2])
            print(f'probe {a.probe} mm: travelled {dist:.1f} mm at bearing {bearing:.1f}, heading was {p0[2]:.1f} -> yaw residual {residual:+.2f} deg')
            if abs(residual) > 20:
                print('WARNING: residual beyond 20 deg -- the plate is mounted wrong or the robot drives backwards; NOT writing it')
                residual = 0.0
            else:
                register(tag, a.family, mx, my, a.mount_z, -math.pi / 2 + math.radians(residual))
            log.update({'probe_mm': a.probe, 'probe_travel_mm': round(dist, 1), 'probe_bearing_deg': round(bearing, 2), 'yaw_residual_deg': round(residual, 2)})
    getattr(a, 'link', link).close()

    (out / 'mount.json').write_text(json.dumps(log, indent=2, default=list))
    print(f'wrote {out}/mount.json')
    if a.write:
        cal = json.loads(CAL_FILE.read_text())
        e = cal['robots'].setdefault(a.robot, {'tag_family': a.family, 'tag_number': tag, 'camera': tc.CAM, 'lever_cm': [0.0, 0.0], 'parallax_k': 1.0})
        # `camera` must be updated too, not just seeded on first write: a robot
        # that already had an entry kept the OLD camera name while every number
        # beside it came from a different one (tigez 2026-09-05 -- solved on
        # hd-usb-camera, entry still claimed arducam-ov9782-usb-camera).
        e.update({'camera': tc.CAM,
                  'mount_x_cm': round(mx, 3), 'mount_y_cm': round(my, 3), 'mount_z_cm': a.mount_z,
                  'mount_yaw_residual_deg': round(residual, 2), 'lever_cm': [0.0, 0.0], 'parallax_k': 1.0})
        e['_mount_provenance'] = (f'{a.robot.upper()}-MEASURED {time.strftime("%Y-%m-%d")} by tests/calibration/mount.py on {tc.CAM}: '
                                  f'{len(poses)} rest poses over {a.pivots} +-90 pivots, residual rms {rms:.1f} mm; verification drift '
                                  f'{sum(drifts) / len(drifts):.2f} cm/pivot; yaw residual from a {a.probe} mm probe. {out}/mount.json')
        CAL_FILE.write_text(json.dumps(cal, indent=2) + '\n')
        print(f'wrote {CAL_FILE}')
        subprocess.run([sys.executable, str(CAMLINK), '--register', a.robot], check=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
