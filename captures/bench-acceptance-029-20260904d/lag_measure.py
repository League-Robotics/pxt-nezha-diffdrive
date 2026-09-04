"""Drivetrain lag measurement (design motion-profile-unification.md S6.3 /
S10.2, first measurement) on tovez over the zilch serial daemon.

Method: from rest, `TLM FULL`, then `WHEELS_V +-200 +-200 1500`. The
shaper ramps the commanded wheel velocity 0 -> 200 mm/s at `accel`
(400 mm/s^2, i.e. 0.5 s). Each wheel's measured `vl`/`vr` (mm/s) is
fitted to that ramp delayed by `lag`: v_meas(t) ~= ramp(t - lag).
Onset t0 = the `now` of the last frame with zero duty before the first
nonzero-duty frame (the staged command lands one tick after it is
issued). Trials alternate direction so the robot stays put.

Usage: uv run python captures/.../lag_measure.py zilch.local:43671
"""
import sys, time, json, math, pathlib
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam

OUT = pathlib.Path(__file__).parent
ACCEL = 400.0   # [mm/s^2]
VCMD = 200.0    # [mm/s]
HOLD = 1500     # [ms]
LIMX, LIMY = 55.0, 32.6   # [cm] field limit minus 12 cm margin

cam = Cam()
def pose(n=4):
    xs = ys = sy = cy = 0.0; k = 0; end = time.time() + 3
    while k < n and time.time() < end:
        for t in cam.d.get_tags(cam.cam).tags:
            if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
                xs += t.world.x; ys += t.world.y; sy += math.sin(t.yaw_rad); cy += math.cos(t.yaw_rad); k += 1
        time.sleep(0.1)
    return (xs/k, ys/k, math.degrees(math.atan2(sy, cy))) if k else None

def frames_from(lines):
    out = []
    for l in lines:
        p = l.split()
        if p and p[0] == 't' and len(p) >= 18:
            out.append({'seq': int(p[1]), 'now': int(p[2]), 'x': int(p[4]), 'y': int(p[5]),
                        'h': int(p[6]), 'vl': int(p[10]), 'vr': int(p[11]),
                        'dutl': int(p[16]), 'dutr': int(p[17])})
    return out

def fit_lag(fr, sign):
    """Least-squares lag [s] per wheel against the accel ramp."""
    # onset: last zero-duty frame before first nonzero duty
    idx = next((i for i, f in enumerate(fr) if f['dutl'] != 0 or f['dutr'] != 0), None)
    if idx is None or idx == 0:
        return None
    t0 = fr[idx-1]['now']
    res = {}
    for w in ('vl', 'vr'):
        best = None
        for lag in [i/1000 for i in range(0, 401, 5)]:
            sse = 0.0; n = 0
            for f in fr[idx-1:]:
                t = (f['now'] - t0)/1000.0
                if t > 1.4: break
                cmd = sign*min(VCMD, max(0.0, ACCEL*(t - lag)))
                sse += (f[w] - cmd)**2; n += 1
            if best is None or sse < best[1]:
                best = (lag, sse, n)
        res[w] = {'lag': best[0], 'rms': math.sqrt(best[1]/best[2]), 'n': best[2]}
    res['t0'] = t0
    res['steady'] = {w: sum(f[w] for f in fr[idx-1:] if 0.8 <= (f['now']-t0)/1000 <= 1.4) /
                     max(1, sum(1 for f in fr[idx-1:] if 0.8 <= (f['now']-t0)/1000 <= 1.4))
                     for w in ('vl', 'vr')}
    return res

def main(hostport):
    L = TcpLink(hostport)
    log = []
    def ask(cmd, sec=1.0):
        r = [l for l in L.ask(cmd, sec) if not l.startswith('DBG:')]
        log.append((cmd, r)); print(cmd, '->', r[:3]); return r
    ask('HELLO'); ask('RUN:clearestop'); ask('STATUS')
    p = pose(); print('pose', p)
    if p is None: raise SystemExit('no camera fix')
    # projected 30 cm forward and back must clear the margin
    ex, ey = p[0] + 32*math.cos(math.radians(p[2])), p[1] + 32*math.sin(math.radians(p[2]))
    bx, by = p[0] - 32*math.cos(math.radians(p[2])), p[1] - 32*math.sin(math.radians(p[2]))
    print(f'projected fwd end ({ex:.1f},{ey:.1f}) back end ({bx:.1f},{by:.1f})')
    if abs(ex) > LIMX or abs(ey) > LIMY or abs(bx) > LIMX or abs(by) > LIMY:
        raise SystemExit('projected path leaves the margin -- reposition first')
    sid = 1
    ask(f'SET accel 400 #{sid}'); sid += 1
    ask(f'SET decel 400 #{sid}'); sid += 1
    ask(f'GET lag #{sid}'); sid += 1
    # warm-up, net zero
    ask(f'MOVE_X 30 0 100 4000 #{sid}', 2.5); sid += 1
    ask(f'MOVE_X -30 0 100 4000 #{sid}', 2.5); sid += 1
    time.sleep(0.5)
    trials = []
    for k, sign in enumerate((1, -1, 1, -1)):
        pre = pose()
        ask(f'TLM FULL #{sid}', 0.6); sid += 1
        L.s.sendall(f'WHEELS_V {sign*200} {sign*200} {HOLD} #{sid}\n'.encode()); sid += 1
        t_send = time.time()
        lines = L.read(2.8)
        ask(f'TLM OFF #{sid}', 0.6); sid += 1
        L.read(0.4)
        fr = frames_from(lines)
        fit = fit_lag(fr, sign)
        post = pose()
        d = math.hypot(post[0]-pre[0], post[1]-pre[1]) if pre and post else None
        print(f'trial {k} sign {sign:+d}: {len(fr)} frames, fit {fit and {w: fit[w] for w in ("vl","vr")}}, '
              f'steady {fit and fit["steady"]}, camera travel {d and round(d,1)} cm')
        trials.append({'sign': sign, 'pre': pre, 'post': post, 'frames': fr, 'fit': fit,
                       'acks': [l for l in lines if l.startswith('ack')]})
        time.sleep(1.0)
    ask('STATUS')
    L.close()
    (OUT/'lag-trials.json').write_text(json.dumps({'trials': trials, 'log': log}, indent=1))
    lags = {w: [t['fit'][w]['lag'] for t in trials if t['fit']] for w in ('vl', 'vr')}
    print('LAG per trial:', lags)
    for w in lags:
        if lags[w]:
            print(f'{w}: mean {sum(lags[w])/len(lags[w]):.3f} s  min {min(lags[w]):.3f}  max {max(lags[w]):.3f}')

if __name__ == '__main__':
    main(sys.argv[1])
