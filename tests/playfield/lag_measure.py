"""Drivetrain lag measurement for any fleet robot (design
motion-profile-unification.md S10.2, first of the three measurements).

Method (the sprint 029 ticket 007 procedure, `captures/bench-acceptance-
029-20260904d/lag_measure.py`, generalised): from rest, `TLM FULL`, then
`WHEELS_V +-v +-v <hold>`. The shaper ramps the commanded wheel velocity
0 -> v at the robot's own `accel`; each wheel's measured `vl`/`vr` is
fitted to that ramp delayed by `lag`, i.e. v_meas(t) ~= ramp(t - lag),
least squares over the first 1.4 s. Onset t0 is the last zero-duty
frame before the first nonzero-duty one. Trials alternate direction so
the robot ends where it started; the camera checks the projected path
clears the rails first and reports the travel afterwards.

Carrier/camera options are turn_calibration.py's (--robot, --host/--port,
--wifi, --radio, --tag, --heading-offset). Writes <out>/lag-trials.json
and prints the per-wheel mean; `--apply` then `SET lag <mean>` on the
robot (RAM only -- bake it in radio-robot-lib as firmware_bake.lag_s).

  uv run python tests/playfield/lag_measure.py --robot vevov --heading-offset 91.28 --out reports/<dir>
"""
import argparse
import json
import math
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import turn_calibration as tc  # noqa: E402

VCMD = 200      # [mm/s] step target per wheel
HOLD = 1500     # [ms] WHEELS_V hold
FIT_WINDOW = 1.4  # [s] after onset
LAG_GRID = [i / 1000 for i in range(0, 401, 5)]  # [s]


def parse_frames(cols, lines):
    out = []
    for t, s in lines:
        p = s.split()
        if not p or p[0] != 't' or len(p) - 1 < len(cols):
            continue
        try:
            f = {c: int(v) for c, v in zip(cols, p[1:])}
        except ValueError:
            continue
        f['t_host'] = t
        out.append(f)
    return out


def fit_lag(frames, sign, accel):
    """Least-squares lag [s] per wheel against the accel ramp; None when
    the onset cannot be found."""
    idx = next((i for i, f in enumerate(frames) if f.get('dutl', 0) != 0 or f.get('dutr', 0) != 0), None)
    if idx is None or idx == 0:
        return None
    t0 = frames[idx - 1]['now']
    res = {'t0': t0}
    for w in ('vl', 'vr'):
        best = None
        for lag in LAG_GRID:
            sse, n = 0.0, 0
            for f in frames[idx - 1:]:
                t = (f['now'] - t0) / 1000.0
                if t > FIT_WINDOW:
                    break
                cmd = sign * min(VCMD, max(0.0, accel * (t - lag)))
                v = tc.speed(f, w)
                sse += (v - cmd) ** 2
                n += 1
            if best is None or sse < best[1]:
                best = (lag, sse, n)
        res[w] = {'lag': best[0], 'rms': round(math.sqrt(best[1] / max(1, best[2])), 1), 'n': best[2]}
    steady = [f for f in frames[idx - 1:] if 0.8 <= (f['now'] - t0) / 1000 <= FIT_WINDOW]
    res['steady'] = {w: round(sum(tc.speed(f, w) for f in steady) / max(1, len(steady)), 1) for w in ('vl', 'vr')}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot', default='tigez')
    ap.add_argument('--host'); ap.add_argument('--port', type=int)
    ap.add_argument('--wifi', metavar='NAME|IP')
    ap.add_argument('--radio', action='store_true')
    ap.add_argument('--tag', type=int)
    ap.add_argument('--camera', default=None)
    ap.add_argument('--field-cm', type=float, nargs=2, metavar=('W', 'H'), default=None)
    ap.add_argument('--heading-offset', type=float, default=0.0)
    ap.add_argument('--trials', type=int, default=4)
    ap.add_argument('--margin', type=float, default=tc.SAFE_MARGIN)
    ap.add_argument('--apply', action='store_true', help='SET lag <mean of both wheels> afterwards')
    ap.add_argument('--out', default='reports/lag')
    a = ap.parse_args()
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
    print(f'status: {link.status()}')

    def get(field):
        tid, ack = link.seqd(f'GET {field}', wait=2.0)
        for _, s in link.since(time.time() - 2.5, f'get {field} '):
            return float(s.split()[2])
        return None
    accel = get('accel')
    lag_before = get('lag')
    print(f'accel={accel} lag={lag_before} (live)')
    if not accel:
        raise SystemExit('GET accel returned nothing -- pre-029 firmware? lag only exists on the 029 engine')

    tc.lights_on()
    cam = tc.Camera(tag, a.heading_offset)
    pose = cam.fix()
    if pose is None:
        raise SystemExit(f'camera does not see tag {tag}')
    print(f'camera: tag {tag} at ({pose[0]:.1f}, {pose[1]:.1f}) cm heading {pose[2]:.1f} deg')
    # a 200 mm/s step held 1.5 s travels ~25 cm; both directions must clear
    reach = 32.0
    for sgn in (1, -1):
        end = (pose[0] + sgn * reach * math.cos(math.radians(pose[2])),
               pose[1] + sgn * reach * math.sin(math.radians(pose[2])), pose[2])
        bad = tc.check_safe(end, a.margin)
        if bad:
            raise SystemExit(f'STOP: projected {"forward" if sgn > 0 else "backward"} end {bad}')
    bad = tc.check_safe(pose, a.margin)
    if bad:
        raise SystemExit(f'STOP: {bad}')

    # telemetry columns
    tid, ack = link.seqd('TLM FULL', wait=3.0)
    hdr = link.wait_for(r'^thdr ', time.time() - 3.5, 6.0)
    link.seqd('TLM OFF', wait=2.0)
    if not hdr:
        raise SystemExit('no thdr after TLM FULL')
    cols = hdr.split()[1:]
    print(f'telemetry columns: {cols}')

    # warm-up, net zero (cold first move yaws; see memory)
    link.seqd('MOVE_X 30 0 100 4000', wait=1.0); time.sleep(2.0)
    link.seqd('MOVE_X -30 0 100 4000', wait=1.0); time.sleep(2.0)

    trials = []
    for k in range(a.trials):
        sign = 1 if k % 2 == 0 else -1
        tc.lights_on()
        pre = cam.fix()
        link.seqd('TLM FULL', wait=1.0)
        t_send = time.time()
        tid, ack = link.seqd(f'WHEELS_V {sign * VCMD} {sign * VCMD} {HOLD}', wait=1.0)
        time.sleep(HOLD / 1000.0 + 1.2)
        link.seqd('TLM OFF', wait=1.0)
        frames = parse_frames(cols, link.since(t_send - 0.2, 't '))
        fit = fit_lag(frames, sign, accel)
        post = cam.fix()
        travel = (math.hypot(post[0] - pre[0], post[1] - pre[1]) if pre and post else None)
        print(f'trial {k + 1} sign {sign:+d}: {len(frames)} frames, ack {ack}, '
              f'fit {fit and {w: fit[w] for w in ("vl", "vr")}}, steady {fit and fit["steady"]}, '
              f'camera travel {travel if travel is None else round(travel, 1)} cm')
        trials.append({'sign': sign, 'pre': pre, 'post': post, 'travel_cm': travel,
                       'ack': ack, 'fit': fit, 'frames': frames})
        time.sleep(1.0)

    lags = {w: [t['fit'][w]['lag'] for t in trials if t['fit']] for w in ('vl', 'vr')}
    summary = {'robot': a.robot, 'link': where, 'accel': accel, 'lag_before': lag_before,
               'vcmd': VCMD, 'hold_ms': HOLD, 'per_trial': lags}
    for w in lags:
        if lags[w]:
            summary[w] = {'mean': round(sum(lags[w]) / len(lags[w]), 3), 'min': min(lags[w]), 'max': max(lags[w])}
    both = lags['vl'] + lags['vr']
    summary['lag_s'] = round(sum(both) / len(both), 3) if both else None
    print(f'LAG per trial: {lags}')
    for w in ('vl', 'vr'):
        if w in summary:
            print(f'{w}: mean {summary[w]["mean"]:.3f} s  min {summary[w]["min"]:.3f}  max {summary[w]["max"]:.3f}')
    print(f'lag_s (both wheels): {summary["lag_s"]}')
    if a.apply and summary['lag_s'] is not None:
        tid, ack = link.seqd(f'SET lag {summary["lag_s"]}', wait=2.0)
        print(f'SET lag {summary["lag_s"]} -> {ack}; GET lag -> {get("lag")}')
        summary['applied'] = True
    (out / 'lag-trials.json').write_text(json.dumps({'summary': summary, 'trials': trials}, indent=1))
    print(f'wrote {out}/lag-trials.json')
    link.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
