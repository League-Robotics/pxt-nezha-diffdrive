"""Stock vs speed-floor-70: the averaged mean-wheel-speed profiles overlaid,
plus zooms on the two leg endings where the stall-and-bump lived.

    python3 chart_compare.py stock.json floor70.json out.png
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import chart_runs as cr

SURF, INK, INK2, GRID = cr.SURF, cr.INK, cr.INK2, cr.GRID
STOCK, FIX = '#2a78d6', '#eb6834'


def averaged(path):
    """{phase: (t_grid, mean-wheel-speed averaged over runs, offset)}"""
    d = json.load(open(path))
    runs = sorted({e['run'] for e in d['events'] if e['run'] > 0})
    per = {r: cr.phase_segments(d, r) for r in runs}
    out = {}
    for ph in cr.PHASES:
        grids, offs = [], []
        for r in runs:
            segs = per[r]
            t, vl, vr, on = segs[ph]
            v = 0.5 * (vl + vr) if ph != 'turn360' else 0.5 * (vr - vl)
            ok = ~np.isnan(v)
            tt = t - on
            g = np.arange(-0.2, tt.max(), cr.GRID_DT)
            grids.append(np.interp(g, tt[ok], v[ok]))
            offs.append(on - segs['leg150'][3])
        n = min(len(g) for g in grids)
        out[ph] = (np.arange(-0.2, -0.2 + n * cr.GRID_DT, cr.GRID_DT)[:n],
                   np.mean([g[:n] for g in grids], axis=0), float(np.mean(offs)))
    return out


def main():
    a, b, out = averaged(sys.argv[1]), averaged(sys.argv[2]), sys.argv[3]
    fig = plt.figure(figsize=(14, 8), facecolor=SURF)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.2, 1])
    top = fig.add_subplot(gs[0, :])
    for prof, col, label in ((a, STOCK, 'stock, floor 20 mm/s'), (b, FIX, 'exp/speed-floor-70, floor 70 mm/s')):
        first = True
        for ph in cr.PHASES:
            g, v, off = prof[ph]
            top.plot(g + off, v, color=col, linewidth=2, label=label if first else None)
            first = False
    cr.style(top, 'Averaged profile of three runs — mean wheel speed (turn shown as half-differential)')
    top.set_ylim(-20, 260)
    top.legend(loc='upper right', fontsize=9, frameon=False, labelcolor=INK)
    for ph, off in (('leg150', a['leg150'][2]), ('leg200', a['leg200'][2]), ('turn360', a['turn360'][2])):
        top.annotate(ph.replace('leg', 'leg ').replace('turn360', '360° turn'), (off, 245),
                     xytext=(2, 0), textcoords='offset points', fontsize=8.5, color=INK2, va='top')
    top.set_xlabel('time since first leg onset [s]', color=INK2, fontsize=9)
    zooms = (('leg150', 'end of leg 150 (zoom)'), ('leg200', 'end of leg 200 (zoom)'), ('turn360', 'end of 360° turn (zoom)'))
    for k, (ph, title) in enumerate(zooms):
        ax = fig.add_subplot(gs[1, k])
        for prof, col, label in ((a, STOCK, 'stock'), (b, FIX, 'floor 70')):
            g, v, off = prof[ph]
            # window: last 1.6 s of commanded motion + 0.6 s after
            moving = np.where(np.abs(v) > 20)[0]
            t_end = g[moving[-1]] if len(moving) else g[-1]
            sel = (g >= t_end - 1.6) & (g <= t_end + 0.7)
            ax.plot(g[sel] - t_end, v[sel], color=col, linewidth=2, label=label)
        cr.style(ax, title)
        ax.set_ylim(-30, 230)
        ax.set_xlabel('time relative to last motion [s]', color=INK2, fontsize=9)
        ax.legend(loc='upper right', fontsize=8.5, frameon=False, labelcolor=INK)
    fig.suptitle('gopiv (bare-motor bench rig), 2026-08-29 — stock vs speed floor 70 mm/s, same branch, same sequence',
                 x=0.01, ha='left', fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out, dpi=130, facecolor=SURF)
    print('wrote', out)


if __name__ == '__main__':
    main()
