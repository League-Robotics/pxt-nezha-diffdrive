#!/usr/bin/env python3
"""Analyse kd_run.py leg CSVs (cwd = this dir). ENCODER truth, heading = (dR-dL)/111.6 (zuvat.json placeholder trackwidth)."""
import csv, glob, math, os, statistics as st, sys
MM = 0.079322; TW = 111.6
def load(p): return [{k: float(v) for k, v in x.items()} for x in csv.DictReader(open(p))]
rows = []
for p in sorted(set(glob.glob("[abc]*_*_*_*.csv")) | set(glob.glob("after*_*.csv"))):
    if p.endswith("summary.csv"): continue
    n = os.path.basename(p)[:-4].split("_"); exp, setting, i, d = n[0], "_".join(n[1:-2]), int(n[-2]), n[-1]
    f = load(p); sgn = 1 if d == 'fwd' else -1
    x = y = th = ymax = 0.0
    for a, b in zip(f, f[1:]):
        dl = (b['posl']-a['posl'])*MM; dr = (b['posr']-a['posr'])*MM
        dd = (dl+dr)/2; dth = (dr-dl)/TW
        x += dd*math.cos(th+dth/2); y += dd*math.sin(th+dth/2); th += dth
        if abs(y) > abs(ymax): ymax = y
    dl = (f[-1]['posl']-f[0]['posl'])*MM; dr = (f[-1]['posr']-f[0]['posr'])*MM
    mv = [b['t_ms'] for a, b in zip(f, f[1:]) if b['posl'] != a['posl'] or b['posr'] != a['posr']]
    rows.append(dict(exp=exp, setting=setting, i=i, dir=d, err_l=sgn*dl-600, err_r=sgn*dr-600,
        heading_deg=math.degrees(th)*sgn, lateral_mm=y*sgn, lateral_ext=ymax*sgn,
        time_ms=mv[-1]-mv[0], i2cf=f[-1]['i2cf']-f[0]['i2cf'],
        peak_v=max(max(abs(a['vl']), abs(a['vr'])) for a in f)))
if not rows: sys.exit("no rows")
with open("kd_summary.csv", "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader()
    wr.writerows({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in rows)
print("exp setting n | worst|errL| worst|errR| mean errL errR | mean|head| mean|lat| worst|lat| | time_ms | i2cf mean | peak_v")
for exp in sorted({r['exp'] for r in rows}):
    for sset in dict.fromkeys(r['setting'] for r in rows if r['exp'] == exp):
        R = [r for r in rows if r['exp'] == exp and r['setting'] == sset]
        m = lambda k: st.mean(r[k] for r in R)
        ma = lambda k: st.mean(abs(r[k]) for r in R)
        print(f"{exp} {sset} {len(R)} | {max(abs(r['err_l']) for r in R):.2f} {max(abs(r['err_r']) for r in R):.2f} | {m('err_l'):+.2f} {m('err_r'):+.2f} | {ma('heading_deg'):.2f} {ma('lateral_mm'):.1f} {max(abs(r['lateral_mm']) for r in R):.1f} | {m('time_ms'):.0f} | {m('i2cf'):.1f} | {m('peak_v'):.0f}")
