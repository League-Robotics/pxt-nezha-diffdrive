#!/usr/bin/env python3
"""Four-panel comparison: WHEELS_V step vs kp vs iMax vs MOVE_X ramp.

  uv run --with numpy --with matplotlib python3 chart_abc.py OUT.png
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BLUE, RED = '#2a78d6', '#e34948'   # validated pair (see chart.py)
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#b9b7b0'
GRID, SURFACE = '#e1e0d9', '#fcfcfb'
LW, MS = 1.0, 1.8

abc = json.load(open('tovez-kp-abc-20260828.json'))
drun = json.load(open('tovez-imax-d-20260828.json'))

panels = [
    (abc['runs'][0], 'A — WHEELS_V step, stock gains (kp=0, ki=6, iMax=60 mm/s)'),
    (abc['runs'][1], 'B — WHEELS_V step, pid_kp=0.5 — first-sample kick got WORSE'),
    (drun,           'D — WHEELS_V step, pid_i_max halved to 30 mm/s — peak unchanged'),
    (abc['runs'][2], 'C — MOVE_X 800 mm @ 200 (400 ms ramp + end taper + closed-loop distance)'),
]

fig, axes = plt.subplots(4, 1, figsize=(20, 11), dpi=100, sharex=True)
fig.patch.set_facecolor(SURFACE)

for ax, (run, title) in zip(axes, panels):
    ax.set_facecolor(SURFACE)
    f = run['frames']
    t0 = f[0]['host_t']
    ev = [e for e in run['events'] if ' 200' in e['verb']][0]
    st = ev['t_send'] - run['events'][0]['t_send']
    live = [True] + [f[i]['cyc'] > f[i-1]['cyc'] for i in range(1, len(f))]
    t = [r['host_t'] - t0 - st for r in f]
    vl = [r['vl'] if lv else float('nan') for r, lv in zip(f, live)]
    vr = [r['vr'] if lv else float('nan') for r, lv in zip(f, live)]

    movex = 'MOVE_X' in ev['verb']
    if movex:
        # nominal profile: 400 ms ramp (motion_engine.h rampMs_), cruise,
        # taper observed starting ~4.05 s -- labelled nominal, not the
        # engine's internal reference
        px = [0, 0.4, 4.05, 4.35, 6.0]
        py = [0, 200, 200, 0, 0]
        ax.plot(px, py, color=INK2, lw=1.1, ls=(0, (5, 3)), zorder=2,
                label='nominal profile')
    else:
        ax.plot([-1, 0, 0, 4.0, 4.0, 6.0], [0, 0, 200, 200, 0, 0],
                color=INK2, lw=1.1, ls=(0, (5, 3)), zorder=2,
                label='commanded')

    ax.plot(t, vl, color=BLUE, lw=LW, marker='o', ms=MS, mew=0, zorder=3,
            label='left wheel')
    ax.plot(t, vr, color=RED, lw=LW, marker='o', ms=MS, mew=0, zorder=4,
            label='right wheel')
    ax.axhline(0, color=MUTED, lw=0.8, zorder=1)
    ax.set_xlim(-0.8, 6.0)
    ax.set_ylim(-60, 355)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color('#c3c2b7')
    ax.tick_params(colors=INK2, labelsize=8.5)
    ax.set_title(title, color=INK, fontsize=10, loc='left', pad=4)
    ax.set_ylabel('mm/s', color=INK2, fontsize=9)

axes[-1].set_xlabel('time from leg command (s)', color=INK2, fontsize=9)
handles, labels = axes[0].get_legend_handles_labels()
leg = fig.legend(handles, labels, loc='lower center', ncol=3, frameon=False,
                 fontsize=9, bbox_to_anchor=(0.5, -0.002))
for txt in leg.get_texts():
    txt.set_color(INK2)
fig.suptitle('tovez — one 200 mm/s leg, four ways · bench, wheels up · 2026-08-28',
             color=INK, fontsize=13, x=0.065, ha='left')
fig.tight_layout(rect=(0, 0.03, 1, 0.975))
fig.savefig(sys.argv[1], facecolor=SURFACE)
print('wrote', sys.argv[1])
