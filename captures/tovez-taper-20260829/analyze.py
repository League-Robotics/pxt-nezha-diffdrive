"""Decode each MOVE_X leg's ending: where the wheels first stopped
relative to the target (stop-short), how long they sat, the size of the
restart bump, and the final error. Then regress stop-short on cruise.

    python3 analyze.py baseline.json [more.json ...]
"""
import json
import math
import sys

CPM = 12.76          # counts/mm, tovez travelCalib 0.7837 (motion_engine.h:219)
REST = 20            # mm/s, "at rest" threshold (same as the runner)


def live_frames(frames):
    out, pc = [], None
    for f in frames:
        if pc is None or f['cyc'] > pc:
            out.append(f)
        pc = f['cyc']
    return out


def decode_leg(frames, ev, t_next):
    d = ev['dist']
    sgn = 1 if d > 0 else -1
    seg = [f for f in frames if ev['t_send'] - 0.3 <= f['host_t'] < t_next]
    seg = live_frames(seg)
    pre = [f for f in seg if f['host_t'] < ev['t_send']]
    if not pre:
        return None
    p0 = pre[-1]
    def prog(f):
        pl = sgn * (f['posl'] - p0['posl']) / CPM
        pr = sgn * (f['posr'] - p0['posr']) / CPM
        return pl, pr, 0.5 * (pl + pr)
    post = [f for f in seg if f['host_t'] >= ev['t_send']]
    target = abs(d)
    # first stop: at rest after >= 50% progress
    stop_i = None
    for i, f in enumerate(post):
        if prog(f)[2] >= 0.5 * target and abs(f['vl']) <= REST and abs(f['vr']) <= REST:
            stop_i = i
            break
    if stop_i is None:
        return None
    fs = post[stop_i]
    sl, sr, sm = prog(fs)
    # bumps after the stop
    bumps = [f for f in post[stop_i + 1:] if sgn * f['vl'] > REST or sgn * f['vr'] > REST]
    fe = post[-1]
    el, er, em = prog(fe)
    peak = max([max(abs(f['vl']), abs(f['vr'])) for f in bumps], default=0)
    # duty while stopped (before the first bump)
    idle = post[stop_i:]
    if bumps:
        idle = [f for f in idle if f['host_t'] < bumps[0]['host_t']]
    return {
        'phase': ev['phase'], 'dist': d, 'cruise': ev['cruise'],
        'stop_short': target - sm, 'stop_short_l': target - sl, 'stop_short_r': target - sr,
        't_stop': fs['host_t'] - ev['t_send'],
        't_bump': (bumps[0]['host_t'] - ev['t_send']) if bumps else None,
        't_end': fe['host_t'] - ev['t_send'],
        'dead': (bumps[0]['host_t'] - fs['host_t']) if bumps else None,
        'bump': em - sm, 'bump_peak': peak, 'n_bump_frames': len(bumps),
        'final_err': em - target, 'final_err_l': el - target, 'final_err_r': er - target,
        'idle_frames': len(idle),
        'idle_duty_l': [f['dutl'] for f in idle][:6], 'idle_duty_r': [f['dutr'] for f in idle][:6],
    }


def load(path):
    d = json.load(open(path))
    fr, ev = d['frames'], d['events']
    rows = []
    for i, e in enumerate(ev):
        if 'dist' not in e:
            continue
        t_next = ev[i + 1]['t_send'] if i + 1 < len(ev) else fr[-1]['host_t'] + 1
        r = decode_leg(fr, e, t_next)
        if r:
            r['file'] = path
            rows.append(r)
    return rows


def stats(v):
    v = [x for x in v if x is not None]
    if not v:
        return (float('nan'), float('nan'), 0)
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)) if len(v) > 1 else 0.0
    return (m, sd, len(v))


def linfit(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    ss_res = sum(r * r for r in res)
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else float('nan')
    sd = math.sqrt(ss_res / (n - 2)) if n > 2 else float('nan')
    return a, b, r2, sd


def main():
    rows = []
    for p in sys.argv[1:]:
        rows += load(p)
    print(f'{len(rows)} legs decoded\n')
    print('phase        dist cruise | stop_short(L/R)     t_stop  dead   bump  peak | final_err (L/R)   t_bump')
    for r in rows:
        dead = f'{r["dead"]:.2f}' if r['dead'] is not None else '  -- '
        print(f'{r["phase"]:12s} {r["dist"]:5d} {r["cruise"]:4d} | '
              f'{r["stop_short"]:5.1f} ({r["stop_short_l"]:5.1f}/{r["stop_short_r"]:5.1f}) '
              f'{r["t_stop"]:5.2f}  {dead}  {r["bump"]:5.1f}  {r["bump_peak"]:4d} | '
              f'{r["final_err"]:5.1f} ({r["final_err_l"]:5.1f}/{r["final_err_r"]:5.1f})  '
              + (f'{r["t_bump"]:.2f}' if r['t_bump'] else '--'))

    print('\n== by phase / cruise / direction  (mean ± sd, n) ==')
    keys = sorted({(r['phase'], r['cruise'], r['dist'] > 0) for r in rows},
                  key=lambda k: (k[0], k[1], not k[2]))
    print('phase        cruise dir | stop_short      dead          bump          final_err')
    for ph, c, fwd in keys:
        g = [r for r in rows if r['phase'] == ph and r['cruise'] == c and (r['dist'] > 0) == fwd]
        ss, dd, bb, fe = (stats([r[k] for r in g]) for k in ('stop_short', 'dead', 'bump', 'final_err'))
        print(f'{ph:12s} {c:5d} {"fwd" if fwd else "rev"} | '
              f'{ss[0]:5.1f} ± {ss[1]:3.1f}   {dd[0]:4.2f} ± {dd[1]:4.2f}   '
              f'{bb[0]:5.1f} ± {bb[1]:3.1f}   {fe[0]:5.1f} ± {fe[1]:3.1f}  (n={ss[2]})')

    print('\n== regression: stop_short ~ cruise (baseline phases only, |dist|=300) ==')
    for label, sel in (('all', lambda r: True), ('fwd', lambda r: r['dist'] > 0),
                       ('rev', lambda r: r['dist'] < 0)):
        g = [r for r in rows if r['phase'] == 'baseline' and abs(r['dist']) == 300 and sel(r)]
        if len(g) < 3:
            continue
        xs = [r['cruise'] for r in g]
        for what in ('stop_short', 'stop_short_l', 'stop_short_r'):
            ys = [r[what] for r in g]
            a, b, r2, sd = linfit(xs, ys)
            m, s, n = stats(ys)
            print(f'{label:3s} {what:13s}: raw {m:5.1f} ± {s:3.1f} mm | '
                  f'fit {a:6.2f} + {b:7.4f}·cruise  R²={r2:5.2f}  resid sd={sd:3.1f} mm  (n={n})')
    base = [r for r in rows if r['phase'] == 'baseline']
    if base:
        print('\nbaseline final_err overall: %.1f ± %.1f mm (n=%d)' % stats([r['final_err'] for r in base]))


if __name__ == '__main__':
    main()
