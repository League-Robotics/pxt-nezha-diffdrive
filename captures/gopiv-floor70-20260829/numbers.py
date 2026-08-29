"""Per-move ending numbers for the gopiv A/B: where the wheels first came to
rest (mm short of target), whether a restart bump followed, final error, and
the time from motion onset to the last motion. Counts/mm = the firmware's
own baked tovez calib (12.76; implied 12.70-12.74 from the smoke run).

    python3 numbers.py stock.json floor70.json
"""
import json
import math
import sys

CPM, REST = 12.76, 20


def live(fr):
    out, pc = [], None
    for f in fr:
        if pc is None or f['cyc'] > pc:
            out.append(f)
        pc = f['cyc']
    return out


def decode(path):
    d = json.load(open(path))
    fr, ev = live(d['frames']), d['events']
    rows = []
    for i, e in enumerate(ev):
        if e['phase'] not in ('leg150', 'leg200', 'turn360'):
            continue
        t_next = ev[i + 1]['t_send'] if i + 1 < len(ev) else fr[-1]['host_t'] + 1
        seg = [f for f in fr if e['t_send'] - 0.3 <= f['host_t'] < t_next]
        pre = [f for f in seg if f['host_t'] < e['t_send']][-1]
        post = [f for f in seg if f['host_t'] >= e['t_send']]
        verb = e['verb'].split()
        turn = e['phase'] == 'turn360'
        if turn:
            target = None  # yaw target depends on the baked track width; report coast only
            prog = lambda f: 0.5 * ((f['posr'] - pre['posr']) - (f['posl'] - pre['posl'])) / CPM
        else:
            target = float(verb[1])
            prog = lambda f: 0.5 * ((f['posl'] - pre['posl']) + (f['posr'] - pre['posr'])) / CPM
        on = next(f for f in post if abs(f['vl']) > REST or abs(f['vr']) > REST)
        moving = [f for f in post if abs(f['vl']) > REST or abs(f['vr']) > REST]
        last = moving[-1]
        # first rest after >= 50 % of the way (legs) / after the turn's main body
        ref = target if target else prog(post[-1])
        stop = next(f for f in post if prog(f) >= 0.5 * ref and abs(f['vl']) <= REST and abs(f['vr']) <= REST)
        after = [f for f in post if f['host_t'] > stop['host_t'] and (abs(f['vl']) > REST or abs(f['vr']) > REST)]
        rows.append({'phase': e['phase'], 'run': e['run'],
                     'stop_short': (target - prog(stop)) if target else None,
                     'bump': bool(after), 'bump_mm': prog(post[-1]) - prog(stop),
                     'final_err': (prog(post[-1]) - target) if target else None,
                     'final_l': ((post[-1]['posl'] - pre['posl']) / CPM - target) if target else None,
                     'final_r': ((post[-1]['posr'] - pre['posr']) / CPM - target) if target else None,
                     'coast_after_stop': prog(post[-1]) - prog(stop),
                     't_motion': last['host_t'] - on['host_t'],
                     'turn_half_diff_mm': prog(post[-1]) if turn else None})
    return rows


def ms(v):
    v = [x for x in v if x is not None]
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)) if len(v) > 1 else 0
    return m, sd


for path in sys.argv[1:]:
    rows = decode(path)
    print(f'== {path}')
    print(' phase    run  stop_short  bump  bump_mm  final(L/R)          t_motion')
    for r in rows:
        ss = f"{r['stop_short']:6.1f}" if r['stop_short'] is not None else '   -- '
        fe = (f"{r['final_err']:5.1f} ({r['final_l']:5.1f}/{r['final_r']:5.1f})"
              if r['final_err'] is not None else f"half-diff {r['turn_half_diff_mm']:.1f} mm")
        print(f" {r['phase']:8s} {r['run']}   {ss}     {'Y' if r['bump'] else '-'}   {r['bump_mm']:5.1f}   {fe:22s} {r['t_motion']:5.2f}")
    for ph in ('leg150', 'leg200', 'turn360'):
        g = [r for r in rows if r['phase'] == ph]
        line = f' {ph:8s} mean: t_motion {ms([r["t_motion"] for r in g])[0]:.2f} ± {ms([r["t_motion"] for r in g])[1]:.2f} s; bumps {sum(r["bump"] for r in g)}/{len(g)}'
        if ph != 'turn360':
            line += f'; stop_short {ms([r["stop_short"] for r in g])[0]:.1f} ± {ms([r["stop_short"] for r in g])[1]:.1f}; final {ms([r["final_err"] for r in g])[0]:.1f} ± {ms([r["final_err"] for r in g])[1]:.1f} mm'
        else:
            line += f'; half-diff {ms([r["turn_half_diff_mm"] for r in g])[0]:.1f} ± {ms([r["turn_half_diff_mm"] for r in g])[1]:.1f} mm'
        print(line)
