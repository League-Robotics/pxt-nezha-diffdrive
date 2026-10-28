#!/usr/bin/env python3
"""Analyse sp_run.py CSVs. Encoder truth, 0.079322 mm/count; heading from (dR-dL)/111.6 mm (zuvat.json trackwidth placeholder)."""
import csv, glob, math, statistics as st, os, sys
MM = 0.079322; TW = 111.6
def load(p):
    r = list(csv.DictReader(open(p)))
    return [{k: float(v) for k, v in x.items()} for x in r]
def wheels():
    rows = []
    for p in sorted(glob.glob("wheels_p*_*.csv")):
        n = os.path.basename(p)[:-4].split("_"); path, sp, d = int(n[1][1:]), int(n[2]), n[3]
        f = load(p)
        mv = [i for i in range(1, len(f)) if f[i]['posl'] != f[i-1]['posl'] or f[i]['posr'] != f[i-1]['posr']]
        if len(mv) < 8:
            rows.append(dict(path=path, speed=sp, dir=d, run_ms=0, nwin=0, mean_l=0.0, err_l=-sp, sd_l=0.0, stall_l=-1, mean_r=0.0, err_r=-sp, sd_r=0.0, stall_r=-1, tlm_mean_l=0.0, tlm_mean_r=0.0, i2cf=f[-1]['i2cf']-f[0]['i2cf'], note='no motion', net_l=(f[-1]['posl']-f[0]['posl'])*MM, net_r=(f[-1]['posr']-f[0]['posr'])*MM)); continue
        on = mv[0] - 1
        t_on = f[on]['t_ms']
        # STOP time: last frame before both wheels sit still for good
        last = max(i for i in range(1, len(f)) if f[i]['posl'] != f[i-1]['posl'] or f[i]['posr'] != f[i-1]['posr'])
        t_end = f[last]['t_ms']
        w0, w1 = t_on + 700, min(t_on + 1500, t_end - 400)
        win = [i for i in range(1, len(f)) if w0 <= f[i]['t_ms'] <= w1]
        out = dict(path=path, speed=sp, dir=d, run_ms=t_end - t_on, nwin=len(win))
        sgn = 1 if d == 'fwd' else -1
        for w in ('l', 'r'):
            dt = [(f[i]['t_ms'] - f[i-1]['t_ms']) / 1000 for i in win]
            v = [sgn * (f[i]['pos'+w] - f[i-1]['pos'+w]) * MM / (f[i]['t_ms'] - f[i-1]['t_ms']) * 1000 for i in win]
            mean = sgn * (f[win[-1]]['pos'+w] - f[win[0]-1]['pos'+w]) * MM / (f[win[-1]]['t_ms'] - f[win[0]-1]['t_ms']) * 1000
            vt = [sgn * f[i]['v'+w] for i in win]
            out['mean_'+w] = mean; out['err_'+w] = mean - sp
            out['sd_'+w] = st.pstdev(v); out['tlm_mean_'+w] = st.mean(vt); out['tlm_sd_'+w] = st.pstdev(vt)
            out['minv_'+w] = min(v)
            # stall: frame in [on+300, end-150] with no count change on this wheel
            out['stall_'+w] = sum(1 for i in range(1, len(f)) if t_on + 300 <= f[i]['t_ms'] <= t_end - 150 and f[i]['pos'+w] == f[i-1]['pos'+w])
        out['i2cf'] = f[-1]['i2cf'] - f[0]['i2cf']
        out['net_l'] = (f[-1]['posl']-f[0]['posl'])*MM; out['net_r'] = (f[-1]['posr']-f[0]['posr'])*MM; out['note'] = ''
        out['frames_in_run'] = len([1 for x in f if t_on <= x['t_ms'] <= t_end])
        rows.append(out)
    return rows
def legs():
    rows = []
    for p in sorted(glob.glob("leg_p*.csv")):
        n = os.path.basename(p)[:-4].split("_"); path, i, d = int(n[1][1:]), int(n[2]), n[3]
        f = load(p); sgn = 1 if d == 'fwd' else -1
        x = y = th = 0.0; thmax = 0.0; ymax = 0.0
        for a, b in zip(f, f[1:]):
            dl = (b['posl'] - a['posl']) * MM; dr = (b['posr'] - a['posr']) * MM
            dd = (dl + dr) / 2; dth = (dr - dl) / TW
            x += dd * math.cos(th + dth/2); y += dd * math.sin(th + dth/2); th += dth
            if abs(y) > abs(ymax): ymax = y
        dl = (f[-1]['posl'] - f[0]['posl']) * MM; dr = (f[-1]['posr'] - f[0]['posr']) * MM
        t_on = next(a['t_ms'] for a, b in zip(f, f[1:]) if b['posl'] != a['posl'] or b['posr'] != a['posr'])
        last = max(b['t_ms'] for a, b in zip(f, f[1:]) if b['posl'] != a['posl'] or b['posr'] != a['posr'])
        rows.append(dict(path=path, i=i, dir=d, travel_l=sgn*dl, travel_r=sgn*dr, err_l=sgn*dl-600, err_r=sgn*dr-600,
                         heading_deg=math.degrees(th), lateral_mm=y*sgn if False else y, lateral_ext=ymax,
                         time_ms=last - t_on, i2cf=f[-1]['i2cf'] - f[0]['i2cf']))
    return rows
def refresh():
    p = glob.glob("refresh_p1_120.csv")[0]; f = load(p)
    on = next(i for i in range(1, len(f)) if f[i]['posl'] != f[i-1]['posl'])
    last = max(i for i in range(1, len(f)) if f[i]['posl'] != f[i-1]['posl'])
    t_on = f[on-1]['t_ms']; t_end = f[last]['t_ms']
    seg = [(f[i]['t_ms'] - t_on, (f[i]['posl'] - f[i-1]['posl']) * MM / (f[i]['t_ms'] - f[i-1]['t_ms']) * 1000,
            (f[i]['posr'] - f[i-1]['posr']) * MM / (f[i]['t_ms'] - f[i-1]['t_ms']) * 1000, f[i]['vl'], f[i]['vr']) for i in range(on, last + 1)]
    return t_end - t_on, seg
def w_csv(name, rows):
    with open(name, 'w', newline='') as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in rows)
if __name__ == "__main__":
    W = wheels(); w_csv("wheels_summary.csv", W)
    print("path speed dir  runms | meanL errL sdL stallL | meanR errR sdR stallR | tlmL tlmR | i2cf")
    for r in W: print(f"{r['path']} {r['speed']:4d} {r['dir']} {r['run_ms']:5.0f} | {r['mean_l']:6.1f} {r['err_l']:6.1f} {r['sd_l']:5.1f} {r['stall_l']} | {r['mean_r']:6.1f} {r['err_r']:6.1f} {r['sd_r']:5.1f} {r['stall_r']} | {r['tlm_mean_l']:6.1f} {r['tlm_mean_r']:6.1f} | {r['i2cf']}")
    L = legs(); w_csv("legs_summary.csv", L)
    for r in L: print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
    dur, seg = refresh(); print("refresh run ms", dur)
    with open("refresh_p1_120_speed.csv", "w") as fh:
        fh.write("t_ms,vl_enc,vr_enc,vl_tlm,vr_tlm\n")
        for s_ in seg: fh.write(",".join(f"{x:.1f}" for x in s_) + "\n")
