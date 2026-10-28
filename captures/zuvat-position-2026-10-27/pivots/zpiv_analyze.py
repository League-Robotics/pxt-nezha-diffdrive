#!/usr/bin/env python3
"""Analyse the zpiv.py CSVs in this dir -> summary tables (stdout) + PNG charts. ENCODER truth only.
Run: uv run --with numpy --with matplotlib python zpiv_analyze.py"""
import math, csv, glob, statistics as S, collections
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
def load(prefix):
    runs={}; 
    for r in csv.DictReader(open(prefix+'.csv')): runs[int(r['run'])]=r
    fr=collections.defaultdict(list)
    for r in csv.DictReader(open(prefix+'_frames.csv')):
        fr[int(r['run'])].append({k:(float(v) if k=='t' else int(v)) for k,v in r.items() if k not in('kind','value')})
    return runs,fr
def wrap(d): return (d+18000)%36000-18000
sets=[('pivots_m1_c150',1,150),('pivots_m1_c250',1,250),('pivots_m0_c150',0,150),('pivots_m0_c250',0,250)]
piv=[]; skew=[]
for pre,mode,cr in sets:
    runs,fr=load(pre)
    for k,r in runs.items():
        val=float(r['value']); h0=int(r['h0']); h1=int(r['h1'])
        d=wrap(h1-h0-round(val*100)); f=fr[k]
        pk=max(max(abs(x['vl']),abs(x['vr'])) for x in f)
        piv.append(dict(mode=mode,cr=cr,val=val,err=d/100,pk=pk,i2=int(r['i2cf1'])-int(r['i2cf0']),
            dxy=((int(r['x1'])-int(r['x0']))**2+(int(r['y1'])-int(r['y0']))**2)**.5))
        i0=next(i for i,x in enumerate(f) if abs(x['vl'])>=10 or abs(x['vr'])>=10)
        a=f[i0]; lag=next((i-i0 for i in range(i0,len(f)) if abs(f[i]['vl'])>=10 and abs(f[i]['vr'])>=10),None)
        both=min(abs(a['vl']),abs(a['vr'])); mx=max(abs(a['vl']),abs(a['vr']))
        skew.append(dict(mode=mode,cr=cr,val=val,kind='pivot',lagfr=lag,ratio=both/mx if mx else 0,t0=a['t']))
print('PIVOT TABLE (ENCODER truth: odometry heading change at rest minus commanded; deg)')
print('mode cruise angle dir  n  mean_err  sd  worst|err|  peak_wheel_speed(max)  peak/cruise  lurch(>cruise)  lurch(>1.2*cruise)  mean_i2cf/run')
for mode in (1,0):
  for cr in (150,250):
    for ang in (90,180):
      for sg in (1,-1):
        g=[p for p in piv if p['mode']==mode and p['cr']==cr and p['val']==sg*ang]
        e=[p['err'] for p in g]; pk=max(p['pk'] for p in g)
        print(f"{mode} {cr} {ang} {'+' if sg>0 else '-'} {len(g)} {np.mean(e):+.2f} {np.std(e,ddof=1) if len(e)>1 else float('nan'):.2f} {max(abs(x) for x in e):.2f} {pk} {pk/cr:.2f} {'yes' if pk>cr else 'no'} {'yes' if pk>1.2*cr else 'no'} {np.mean([p['i2'] for p in g]):.1f}")
legs=[]
for mode in (1,0):
    runs,fr=load(f'legs_m{mode}_c150')
    for k,r in runs.items():
        f=fr[k]; val=float(r['value'])
        _dx=int(r['x1'])-int(r['x0']); _dy=int(r['y1'])-int(r['y0']); _h0=math.radians(int(r['h0'])/100)
        legs.append(dict(mode=mode,val=val,dx=_dx-val,dy=-_dx*math.sin(_h0)+_dy*math.cos(_h0),dyw=_dy,h0=int(r['h0'])/100,dh=wrap(int(r['h1'])-int(r['h0']))/100,
            pk=max(max(abs(x['vl']),abs(x['vr'])) for x in f),i2=int(r['i2cf1'])-int(r['i2cf0'])))
        i0=next(i for i,x in enumerate(f) if abs(x['vl'])>=10 or abs(x['vr'])>=10); a=f[i0]
        lag=next((i-i0 for i in range(i0,len(f)) if abs(f[i]['vl'])>=10 and abs(f[i]['vr'])>=10),None)
        mx=max(abs(a['vl']),abs(a['vr']))
        skew.append(dict(mode=mode,cr=150,val=val,kind='leg',lagfr=lag,ratio=min(abs(a['vl']),abs(a['vr']))/mx if mx else 0,t0=a['t']))
print('\nLEG TABLE (600 mm, cruise 150; ENCODER truth)')
print('mode dir n  mean_dh(deg) sd  mean_lateral(mm,in start-heading frame) sd  worst|lat|  mean_x_err(mm)  peak_speed  i2cf/run')
for mode in (1,0):
  for sg in (1,-1):
    g=[l for l in legs if l['mode']==mode and l['val']==sg*600]
    f=lambda key:[l[key] for l in g]
    print(f"{mode} {'fwd' if sg>0 else 'rev'} {len(g)} {np.mean(f('dh')):+.2f} {np.std(f('dh'),ddof=1):.2f} {np.mean(f('dy')):+.1f} {np.std(f('dy'),ddof=1):.1f} {max(abs(x) for x in f('dy')):.0f} {np.mean(f('dx')):+.1f} {max(f('pk'))} {np.mean(f('i2')):.1f}")
for l in legs: print('leg',l)
print('\nSTART SKEW (first frame where either wheel moves)')
for mode in (1,0):
    g=[s for s in skew if s['mode']==mode]
    lags=[s['lagfr'] for s in g]; rat=[s['ratio'] for s in g]
    print(f"mode {mode}: n={len(g)} frames-until-both-wheels-moving: median {S.median(lags)} worst {max(lags)}; first-frame min/max speed ratio median {S.median(rat):.2f} worst(lowest) {min(rat):.2f} p10 {np.percentile(rat,10):.2f}; lag histogram {dict(collections.Counter(lags))}")
    for kind in ('pivot','leg'):
        gg=[s for s in g if s['kind']==kind]
        if gg: print(f"   {kind}: n={len(gg)} median lag {S.median([s['lagfr'] for s in gg])} worst {max(s['lagfr'] for s in gg)} median first-frame t after host send {S.median([s['t0'] for s in gg]):.3f}s")
import itertools
print('i2cf first/last of session:',[ (r['i2cf0'],r['i2cf1']) for r in itertools.islice(csv.DictReader(open('pivots_m1_c150.csv')),0,1)], [ (r['i2cf1']) for r in csv.DictReader(open('legs_m0_c150.csv'))][-1])
# charts
for ang in (90,180):
    fig,ax=plt.subplots(2,2,figsize=(12,7),sharex=True)
    for ci,mode in enumerate((1,0)):
        runs,fr=load(f'pivots_m{mode}_c150')
        for k,r in runs.items():
            val=float(r['value'])
            if abs(val)!=ang: continue
            f=fr[k]; t=[x['t'] for x in f]; h0=int(r['h0'])
            sg=1 if val>0 else -1
            ax[0][ci].plot(t,[sg*wrap(x['h']-h0)/100 for x in f],color='C0' if sg>0 else 'C1',alpha=.6,lw=1)
            ax[1][ci].plot(t,[sg*x['vl'] for x in f],color='C0' if sg>0 else 'C1',alpha=.5,lw=.8)
            ax[1][ci].plot(t,[-sg*x['vr'] for x in f],color='C2',alpha=.3,lw=.8)
        ax[0][ci].axhline(ang,color='k',ls=':'); ax[0][ci].set_title(f'{ang} deg pivots, position_mode {mode}, cruise 150 mm/s (ENCODER truth)')
        ax[0][ci].set_ylabel('heading change in commanded direction [deg]')
        ax[1][ci].axhline(150,color='r',ls='--',lw=.8,label='commanded 150 mm/s'); ax[1][ci].axhline(-150,color='r',ls='--',lw=.8)
        ax[1][ci].set_ylabel('wheel speed (+dir sign-normalised) [mm/s]'); ax[1][ci].set_xlabel('time since host sent MOVE_X [s]'); ax[1][ci].legend()
    fig.tight_layout(); fig.savefig(f'pivot_{ang}_c150.png',dpi=110); plt.close(fig)
fig,ax=plt.subplots(3,2,figsize=(12,9))
for ci,mode in enumerate((1,0)):
    runs,fr=load(f'legs_m{mode}_c150')
    for k,r in runs.items():
        f=fr[k]; x0=int(r['x0']); y0=int(r['y0']); h0=int(r['h0']); sg=1 if float(r['value'])>0 else -1
        t=[x['t'] for x in f]
        ax[0][ci].plot(t,[wrap(x['h']-h0)/100 for x in f],color='C0' if sg>0 else 'C1',alpha=.7)
        hh=math.radians(h0/100); ax[1][ci].plot([sg*(x['x']-x0) for x in f],[-(x['x']-x0)*math.sin(hh)+(x['y']-y0)*math.cos(hh) for x in f],color='C0' if sg>0 else 'C1',alpha=.7)
        ax[2][ci].plot(t,[sg*x['vl'] for x in f],color='C0' if sg>0 else 'C1',alpha=.5,lw=.8); ax[2][ci].plot(t,[sg*x['vr'] for x in f],color='C2',alpha=.4,lw=.8)
    ax[0][ci].set_title(f'600 mm legs, mode {mode}, 150 mm/s (blue fwd, orange rev; ENCODER)'); ax[0][ci].set_ylabel('heading change [deg]'); ax[0][ci].set_xlabel('t [s]')
    ax[1][ci].set_xlabel('distance along leg [mm]'); ax[1][ci].set_ylabel('lateral deviation, start-heading frame [mm]')
    ax[2][ci].axhline(150,color='r',ls='--',lw=.8); ax[2][ci].set_xlabel('t [s]'); ax[2][ci].set_ylabel('wheel speed [mm/s]')
fig.tight_layout(); fig.savefig('legs_c150.png',dpi=110)
