"""Three-panel chart of the end-of-leg stall and its fixes.

    python3 chart.py out.png

A: mean wheel speed through the end of one 300 mm / 150 mm/s leg per config.
B: where the wheels first stop, mm short of target, vs cruise.
C: final error after the move ends, vs cruise.
Palette: dataviz reference categorical slots 1-4 (validated light mode).
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import analyze

CPM = 12.76
SURF, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
SERIES = [  # (label, file, phase, colour)
    ('baseline (floor 20 mm/s)', 'baseline.json', 'baseline', '#2a78d6'),
    ('speed_floor 70 mm/s', 'variants.json', 'floor70', '#eb6834'),
    ('pid_i_max 30 mm/s', 'variants.json', 'imax30', '#1baf7a'),
    ('aim long +8.6, end at stall', 'predict.json', 'aimlong150', '#eda100'),
]
TRACE = [  # panel A: one 150 mm/s forward leg each
    ('baseline', 'baseline.json', 'baseline', '#2a78d6'),
    ('speed_floor 70', 'variants.json', 'floor70', '#eb6834'),
    ('I-term off', 'ffcal.json', 'ff_cal', '#1baf7a'),
    ('aim long +8.6', 'predict.json', 'aimlong150', '#eda100'),
]


def leg_trace(path, phase, intended, pick=0):
    """(t since motion onset, mm remaining to the INTENDED target) for one
    clean (first-transmission) 150 mm/s forward leg of this phase."""
    d = json.load(open(path))
    fr, ev = d['frames'], d['events']
    hits = 0
    for i, e in enumerate(ev):
        if e.get('phase') == phase and e.get('cruise') == 150 and e['dist'] > 0 \
                and e['attempts'] == 1:
            hits += 1
            if hits - 1 != pick:
                continue
            t_next = ev[i + 1]['t_send'] if i + 1 < len(ev) else fr[-1]['host_t'] + 1
            seg = analyze.live_frames([f for f in fr if e['t_send'] - 0.3 <= f['host_t'] < t_next])
            pre = [f for f in seg if f['host_t'] < e['t_send']][-1]
            def prog(f):
                return 0.5 * ((f['posl'] - pre['posl']) + (f['posr'] - pre['posr'])) / CPM
            post = [f for f in seg if f['host_t'] >= e['t_send']]
            on = next(f for f in post if prog(f) > 1.0)
            t = [f['host_t'] - on['host_t'] for f in post]
            rem = [intended - prog(f) for f in post]
            return t, rem
    raise RuntimeError(f'no clean 150 fwd leg for {phase} in {path}')


def style(ax, title, ylabel):
    ax.set_facecolor(SURF)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.set_title(title, loc='left', fontsize=11, color=INK, pad=8)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)


def main():
    out = sys.argv[1]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(15, 4.6), facecolor=SURF,
                                  gridspec_kw={'width_ratios': [1.35, 1, 1]})
    # A: distance remaining vs time, one leg per config
    for label, path, phase, col in TRACE:
        intended = 309 - 8.6 if phase == 'aimlong150' else 300.0
        t, rem = leg_trace(path, phase, intended, pick=1 if phase == 'baseline' else 0)
        a.plot(t, rem, color=col, linewidth=2, solid_capstyle='round', label=label,
               marker='o', markersize=3.5, markeredgecolor=SURF, markeredgewidth=0.8)
    a.set_xlim(1.4, 3.0)
    a.set_ylim(-3, 24)
    a.axhline(0, color=INK2, linewidth=0.8)
    style(a, 'End of a 300 mm leg at 150 mm/s — distance still to go', 'mm to target')
    a.set_xlabel('time since motion onset [s]', color=INK2, fontsize=9)
    a.annotate('baseline: near-stop ~8.6 mm out,\ncreep, then one 3-7 mm jump',
               (2.2, 8.6), xytext=(1.45, 4.5), textcoords='data', fontsize=8.5,
               color=INK, arrowprops={'arrowstyle': '-', 'color': INK2, 'lw': 0.8})
    a.legend(loc='upper right', fontsize=8, frameon=False, labelcolor=INK)

    # B, C: per-leg points vs cruise
    rows = {}
    for label, path, phase, col in SERIES:
        rows[label] = [r for r in analyze.load(path) if r['phase'] == phase and abs(r['dist']) in (300, 309)]
    offs = [-9, -3, 3, 9]
    for (label, path, phase, col), dx in zip(SERIES, offs):
        rs = rows[label]
        xs = [r['cruise'] + dx for r in rs]
        b.scatter(xs, [r['stop_short'] for r in rs], s=46, color=col, edgecolor=SURF,
                  linewidth=1.5, label=label, zorder=3)
        # aim-long is scored against the INTENDED distance (309 - 8.6)
        fe = [r['final_err'] + (8.6 if phase == 'aimlong150' else 0.0) for r in rs]
        c.scatter(xs, fe, s=46, color=col, edgecolor=SURF, linewidth=1.5, label=label, zorder=3)
    for ax in (b, c):
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_xticks([100, 150, 200, 250, 300])
        ax.set_xlim(80, 320)
        ax.set_xlabel('cruise [mm/s]', color=INK2, fontsize=9)
    style(b, 'Where the wheels first stop — mm short of target', 'mm short')
    style(c, 'Final error after the move ends', 'mm (+ = long)')
    b.set_ylim(-6, 17)
    c.set_ylim(-6, 6)
    leg = c.legend(loc='upper right', fontsize=8, frameon=False, labelcolor=INK)
    fig.suptitle('tovez, wheels-up bench, 2026-08-29 — the post-leg bump is a stall at the taper floor; '
                 'a 70 mm/s speed floor removes it', x=0.01, ha='left', fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out, dpi=150, facecolor=SURF)
    print('wrote', out)


if __name__ == '__main__':
    main()
