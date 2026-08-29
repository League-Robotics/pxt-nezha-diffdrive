#!/usr/bin/env python3
"""Wide stripchart: per-wheel measured velocity vs commanded, tovez bench.

Run under uv (the user-level matplotlib install is broken -- same note as
tools/tour_chart.py):
  uv run --with numpy --with matplotlib python3 chart.py IN.json OUT.png

Honesty rule applied here: telemetry republishes its LAST snapshot when
the motion kernel stops stepping, so a frame whose `cyc` did not advance
is NOT a measurement. Those samples are broken out of the measured lines
(NaN) and shaded, rather than drawn as if the wheel really held that
speed.
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# dataviz reference palette, validated as a pair by scripts/validate_palette.js
# (light, surface #fcfcfb): CVD dE 21.6 protan / 34.5 tritan, normal 32.3 -- PASS.
BLUE, RED = '#2a78d6', '#e34948'
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#b9b7b0'
GRID, SURFACE = '#e1e0d9', '#fcfcfb'

LW = 1.0          # "fine lines"
MS = LW * 1.8     # marker just larger than the line -- barely discernible by design


def main():
    src, out = sys.argv[1], sys.argv[2]
    d = json.load(open(src))
    frames, events = d['frames'], d['events']

    t0 = frames[0]['host_t']
    t = [f['host_t'] - t0 for f in frames]

    # A frame is a real measurement only if the kernel stepped since the last one.
    live = [True]
    for i in range(1, len(frames)):
        live.append(frames[i]['cyc'] > frames[i - 1]['cyc'])

    vl = [f['vl'] if lv else float('nan') for f, lv in zip(frames, live)]
    vr = [f['vr'] if lv else float('nan') for f, lv in zip(frames, live)]

    # Commanded steps are keyed on t_SEND, not t_ack. MEASURED this run
    # (tovez-wheels-v2-20260828.json): leg-200 acked 1.28 s after its send
    # while every other phase acked in 0.05 s, and the measured rise tracks
    # the SEND -- i.e. the robot executed the first transmission and the ack
    # was lost on the return path. Keying on t_ack would slide that one step
    # 1.2 s right of the response it caused.
    ev = [(e['t_send'] - t0, e['left'], e['right'], e['name']) for e in events]
    cl, cr = [], []
    for ti in t:
        cur = None
        for et, l, r, _ in ev:
            if et <= ti:
                cur = (l, r)
        cl.append(cur[0] if cur else float('nan'))
        cr.append(cur[1] if cur else float('nan'))

    fig, ax = plt.subplots(figsize=(20, 6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # stale spans: kernel not stepping -> telemetry is a repeat, not a reading
    i = 0
    labelled = False
    while i < len(t):
        if not live[i]:
            j = i
            while j + 1 < len(t) and not live[j + 1]:
                j += 1
            if j > i:
                ax.axvspan(t[i], t[j], color=MUTED, alpha=0.18, lw=0,
                           label=None if labelled else 'kernel not stepping (stale telemetry)')
                labelled = True
            i = j + 1
        else:
            i += 1

    # commanded, per wheel -- reference, so muted and dashed, never a series hue
    ax.plot(t, cl, drawstyle='steps-post', color=INK2, lw=1.1, ls=(0, (5, 3)),
            label='commanded (per wheel)', zorder=2)
    ax.plot(t, cr, drawstyle='steps-post', color=INK2, lw=1.1, ls=(0, (5, 3)),
            zorder=2)

    ax.plot(t, vl, color=BLUE, lw=LW, marker='o', ms=MS, mew=0,
            label='left wheel  (measured)', zorder=3)
    ax.plot(t, vr, color=RED, lw=LW, marker='o', ms=MS, mew=0,
            label='right wheel (measured)', zorder=4)

    ax.axhline(0, color=MUTED, lw=0.8, zorder=1)

    ax.set_ylim(-330, 355)

    # phase boundaries
    for et, l, r, name in ev:
        ax.axvline(et, color=MUTED, lw=0.6, ls=':', zorder=1)
        ax.text(et + 0.05, 348, name, color=INK2, fontsize=7.5,
                va='top', ha='left', rotation=90)

    ax.set_xlabel('time (s)', color=INK2, fontsize=9)
    ax.set_ylabel('wheel velocity (mm/s)', color=INK2, fontsize=9)
    ax.set_title(
        'tovez \u2014 per-wheel velocity vs commanded  \u00b7  bench, wheels up  '
        '\u00b7  2026-08-28',
        color=INK, fontsize=12.5, loc='left', pad=24)
    ax.text(0, 1.012,
            '150 then 200 mm/s legs, then a commanded 360\u00b0 pivot  \u00b7  '
            'encoder telemetry every ~56 ms over mbrelay %s ch%d  \u00b7  '
            'commanded steps keyed on host SEND time  \u00b7  '
            'samples where the motion kernel did not step are broken out, '
            'not drawn as measurements'
            % (d['relay'], d['channel']),
            transform=ax.transAxes, color=INK2, fontsize=8.5, va='bottom')

    ax.grid(True, color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color('#c3c2b7')
    ax.tick_params(colors=INK2, labelsize=8.5)
    ax.set_xlim(ev[0][0], t[-1])

    handles, labels = ax.get_legend_handles_labels()
    leg = fig.legend(handles, labels, loc='lower center', ncol=4, frameon=False,
                     fontsize=9, bbox_to_anchor=(0.5, -0.005))
    for txt in leg.get_texts():
        txt.set_color(INK2)

    fig.tight_layout(rect=(0, 0.055, 1, 1))
    fig.savefig(out, facecolor=SURFACE)
    print('wrote', out)


if __name__ == '__main__':
    main()
