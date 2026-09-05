"""Distance calibration: camera-truthed straights, out and back, at several
lengths, fitted to `measured = gain * commanded + offset`.

The gain is the travel scale error the encoders cannot see (wheel radius,
`travel_calib`); the offset is a per-move end-of-leg residual (braking /
`lag` / `stop_distance` territory, NOT a scale). Both are reported; only
the gain becomes a `travel_calib` suggestion:

    travel_calib_new = travel_calib_now / gain

`travel_calib` is a bake-only constant (no wire field), so the suggestion
goes into radio-robot-lib `geometry.firmware_bake.travel_calib` and needs
a flash; pass `--travel-calib-now` with the value the robot was built with
(the build log or the robot's config) or the suggestion is printed as a
ratio only.

Safety: the robot is faced along the field's long axis (east or west,
whichever has more room), every leg's end pose is projected from a fresh
camera fix and must clear the margin, and the legs alternate out/back so
the robot ends near where it started. The tag mount must be registered
with the daemon (`tools/camlink.py --register <robot>`) so the camera
reports the centre of rotation with parallax corrected -- a raw tag reads
12 cm-high displacements ~12 % long.

  uv run python tests/calibration/distance.py --robot tigez --radio --camera hd-usb-camera --field-cm 110 70 --margin 15 --out reports/<dir>
"""
import argparse
import csv
import json
import math
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import turn_calibration as tc  # noqa: E402


def wait_done(link, tid, timeout=12.0):
    end = time.time() + timeout
    st = {}
    while time.time() < end:
        st = link.status()
        if st.get('done') == str(tid):
            return st
        time.sleep(0.3)
    return st


def face(link, cam, target_deg, tol=2.0):
    """Pivot until the camera heading is within tol of target_deg."""
    for _ in range(3):
        p = cam.fix()
        if p is None:
            return None
        turn = tc.wrap(target_deg - p[2])
        if abs(turn) < tol:
            return p
        tid, ack = link.seqd(f'MOVE_X 0 {int(round(math.radians(turn) * 1000))} 0 6000', wait=3.0)
        if ack:
            wait_done(link, tid)
        time.sleep(1.0)
    return cam.fix()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot', default='tigez')
    ap.add_argument('--host'); ap.add_argument('--port', type=int)
    ap.add_argument('--wifi', metavar='NAME|IP')
    ap.add_argument('--radio', action='store_true')
    ap.add_argument('--tag', type=int)
    ap.add_argument('--camera', default=None)
    ap.add_argument('--field-cm', type=float, nargs=2, metavar=('W', 'H'), default=None)
    ap.add_argument('--heading-offset', type=float, default=0.0)
    ap.add_argument('--lengths', type=int, nargs='+', default=[200, 300, 400], help='leg lengths [mm]')
    ap.add_argument('--reps', type=int, default=2, help='out-and-back pairs per length')
    ap.add_argument('--cruise', type=int, default=0, help='[mm/s], 0 = firmware default')
    ap.add_argument('--margin', type=float, default=tc.SAFE_MARGIN)
    ap.add_argument('--set', nargs='*', default=[], metavar='FIELD=VALUE')
    ap.add_argument('--travel-calib-now', type=float, default=None, help='the travel_calib the robot was built with')
    ap.add_argument('--out', default='reports/distance')
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.camera:
        tc.CAM = a.camera
    if a.field_cm:
        tc.FIELD_X, tc.FIELD_Y = a.field_cm[0] / 2.0, a.field_cm[1] / 2.0
    tag = a.tag or tc.TAGS.get(a.robot)
    if tag is None:
        raise SystemExit(f'no tag known for {a.robot}; pass --tag')

    link, where = tc.open_link(a)
    print(f'link: {where}')
    print(f'robot: {link.hello()}')
    st = link.status(); print(f'status: {st}')
    for kv in a.set:
        k, v = kv.split('=', 1)
        tid, ack = link.seqd(f'SET {k} {v}', wait=2.0)
        print(f'SET {k} {v} -> {ack}')

    tc.lights_on()
    cam = tc.Camera(tag, a.heading_offset)
    p = cam.fix()
    if p is None:
        raise SystemExit(f'camera {tc.CAM} does not see tag {tag}')
    print(f'camera: {tc.CAM}, field +-{tc.FIELD_X} x +-{tc.FIELD_Y} cm, margin {a.margin}; robot at ({p[0]:.1f}, {p[1]:.1f}) heading {p[2]:.1f}')
    bad = tc.check_safe(p, a.margin)
    if bad:
        raise SystemExit(f'STOP: {bad}')
    # face whichever way along x has more room for the longest leg
    longest = max(a.lengths) / 10.0
    room_e, room_w = (tc.FIELD_X - a.margin) - p[0], p[0] + (tc.FIELD_X - a.margin)
    target = 0.0 if room_e >= room_w else 180.0
    if max(room_e, room_w) < longest + 2:
        raise SystemExit(f'STOP: only {max(room_e, room_w):.0f} cm of room along x; the longest leg is {longest:.0f} cm -- move the robot toward the middle')
    p = face(link, cam, target)
    print(f'facing {"east" if target == 0 else "west"}: ({p[0]:.1f}, {p[1]:.1f}) h {p[2]:.1f}')

    rows = []
    plan = [L for L in a.lengths for _ in range(a.reps)]
    for i, L in enumerate(plan, 1):
        for sign in (1, -1):
            mm = sign * L
            tc.lights_on()
            p0 = face(link, cam, target)   # re-aim before every leg: reverse legs yaw a few degrees
            if p0 is None:
                print(f'{i:3d} {mm:+5d}  -- no camera fix'); break
            end = (p0[0] + mm / 10.0 * math.cos(math.radians(p0[2])),
                   p0[1] + mm / 10.0 * math.sin(math.radians(p0[2])), p0[2])
            bad = tc.check_safe(end, a.margin)
            if bad:
                print(f'STOP (projected end): {bad}'); break
            tid, ack = link.seqd(f'MOVE_X {mm} 0 {a.cruise} 8000', wait=3.0)
            if not ack or not ack.startswith('ack'):
                print(f'{i:3d} {mm:+5d}  -- MOVE_X not accepted: {ack}'); continue
            st = wait_done(link, tid)
            time.sleep(1.2)
            p1 = cam.fix()
            if p1 is None:
                print(f'{i:3d} {mm:+5d}  -- no camera fix after'); continue
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            along = (dx * math.cos(math.radians(p0[2])) + dy * math.sin(math.radians(p0[2]))) * 10.0
            cross = (-dx * math.sin(math.radians(p0[2])) + dy * math.cos(math.radians(p0[2]))) * 10.0
            row = {'leg': len(rows) + 1, 'commanded_mm': mm, 'camera_mm': round(along, 1), 'error_mm': round(along - mm, 1),
                   'cross_mm': round(cross, 1), 'heading_change_deg': round(tc.wrap(p1[2] - p0[2]), 2),
                   'x0': round(p0[0], 2), 'y0': round(p0[1], 2), 'x1': round(p1[0], 2), 'y1': round(p1[1], 2),
                   'reason': st.get('reason')}
            rows.append(row)
            print(f"{row['leg']:3d} {mm:+5d} -> camera {along:+7.1f} mm  err {along - mm:+6.1f}  cross {cross:+5.1f}  dh {row['heading_change_deg']:+5.1f} deg  {row['reason']}")
            with open(out / 'legs.csv', 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        else:
            continue
        break

    # fit |measured| = gain * |commanded| + offset over both directions
    summary = {'robot': a.robot, 'link': where, 'camera': tc.CAM, 'cruise': a.cruise, 'n_legs': len(rows), 'lengths': a.lengths}
    if len(rows) >= 2:
        xs = [abs(r['commanded_mm']) for r in rows]; ys = [abs(r['camera_mm']) for r in rows]
        n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        gain = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx > 0 else None
        offset = (my - gain * mx) if gain is not None else None
        fwd = [r['error_mm'] for r in rows if r['commanded_mm'] > 0]
        back = [r['error_mm'] for r in rows if r['commanded_mm'] < 0]
        summary.update({
            'fit_gain': None if gain is None else round(gain, 5),
            'fit_offset_mm': None if offset is None else round(offset, 2),
            'mean_err_forward_mm': round(sum(fwd) / len(fwd), 2) if fwd else None,
            'mean_err_reverse_mm': round(sum(back) / len(back), 2) if back else None,
            'mean_abs_err_mm': round(sum(abs(r['error_mm']) for r in rows) / n, 2),
            'mean_abs_cross_mm': round(sum(abs(r['cross_mm']) for r in rows) / n, 2),
            'mean_heading_change_deg': round(sum(r['heading_change_deg'] for r in rows) / n, 2),
        })
        if gain:
            summary['suggested'] = {'travel_calib_ratio': round(1.0 / gain, 5),
                                    'model': 'travel_calib_new = travel_calib_now / gain; the offset is not a scale -- leave it to lag/stop_distance'}
            if a.travel_calib_now:
                summary['suggested']['travel_calib'] = round(a.travel_calib_now / gain, 5)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f'wrote {out}/legs.csv, summary.json')
    getattr(a, 'link', link).close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
