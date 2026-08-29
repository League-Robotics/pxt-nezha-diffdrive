"""Distance regression chart: commanded vs encoder vs camera vs OTOS.

Per-leg rows are summed back to a per-TRIAL total, because that is what
was commanded; a leg is a construction detail that let a 200 cm run fit
a 110 cm box.

Encoder distance is computed TWO ways and both are plotted:
  * integrated pose (x,y) as the firmware reports it
  * RE-DERIVED from raw counts, 0.5*(dL+dR)*travelCalib/10
They should agree; where they do not, the firmware's integration is
adding something the counts do not support. Having the counts is what
makes that checkable at all.
"""
import csv, math, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

CSV=sys.argv[1] if len(sys.argv)>1 else 'dist_sweep.csv'
OUT=sys.argv[2] if len(sys.argv)>2 else 'dist_sweep.png'
TRAVEL_CALIB=0.7122            # mm per shaft degree, baked
MM_PER_COUNT=TRAVEL_CALIB/10.0 # 1 count == 0.1 shaft degree

S1,S2,S3,S4='#2a78d6','#eb6834','#2e9e6b','#8b5cf6'
INK,INK2,MUTED='#0b0b0b','#52514e','#b9b7b0'

rows=list(csv.DictReader(open(CSV)))
trials={}
for r in rows:
    D=float(r['commanded_total_cm']); t=trials.setdefault(D,{'cam':0.,'enc':0.,'otos':0.,'cnt':0.,'n':0})
    t['cam']+=math.hypot(float(r['cam_x1_cm'])-float(r['cam_x0_cm']),
                         float(r['cam_y1_cm'])-float(r['cam_y0_cm']))
    t['enc']+=math.hypot(float(r['enc_x1_mm'])-float(r['enc_x0_mm']),
                         float(r['enc_y1_mm'])-float(r['enc_y0_mm']))/10.0
    t['otos']+=math.hypot(float(r['otos_x1_mm'])-float(r['otos_x0_mm']),
                          float(r['otos_y1_mm'])-float(r['otos_y0_mm']))/10.0
    dl=int(r['posl1'])-int(r['posl0']); dr=int(r['posr1'])-int(r['posr0'])
    t['cnt']+=0.5*(dl+dr)*MM_PER_COUNT/10.0
    t['n']+=1

D=sorted(trials)
cam=[trials[d]['cam'] for d in D]; enc=[trials[d]['enc'] for d in D]
otos=[trials[d]['otos'] for d in D]; cnt=[trials[d]['cnt'] for d in D]

def fit(xs,ys):
    n=len(xs); sx=sum(xs); sy=sum(ys); sxx=sum(x*x for x in xs)
    sxy=sum(x*y for x,y in zip(xs,ys))
    a=(n*sxy-sx*sy)/(n*sxx-sx*sx); c=(sy-a*sx)/n
    return a,c

fig=plt.figure(figsize=(13,5.6),facecolor='#fcfcfb')
ax=fig.add_subplot(1,2,1); ax.set_facecolor('#fcfcfb')
ax.plot(D,D,ls='--',lw=1.2,color=MUTED,label='commanded (ideal)')
for ys,col,lab in ((cam,S3,'camera (truth)'),(enc,S1,'encoder (integrated)'),
                   (otos,S2,'OTOS'),(cnt,S4,'encoder (from raw counts)')):
    ax.plot(D,ys,lw=1.7,marker='o',ms=3,color=col,label=lab)
ax.set_xlabel('commanded [cm]',color=INK2); ax.set_ylabel('measured [cm]',color=INK2)
ax.grid(True,lw=.5,color=MUTED,alpha=.5); ax.tick_params(colors=INK2)
for sp in ax.spines.values(): sp.set_color(MUTED)
ax.legend(loc='upper left',frameon=False,fontsize=9,labelcolor=INK2)
ax.set_title('Distance: measured vs commanded',color=INK,fontsize=11,loc='left')

ax2=fig.add_subplot(1,2,2); ax2.set_facecolor('#fcfcfb')
ax2.axhline(0,lw=1.2,color=MUTED)
for ys,col,lab in ((cam,S3,'camera'),(enc,S1,'encoder'),(otos,S2,'OTOS'),
                   (cnt,S4,'counts')):
    ax2.plot(D,[100*(y/d-1) for y,d in zip(ys,D)],lw=1.7,marker='o',ms=3,
             color=col,label=lab)
ax2.set_xlabel('commanded [cm]',color=INK2)
ax2.set_ylabel('error vs commanded [%]',color=INK2)
ax2.grid(True,lw=.5,color=MUTED,alpha=.5); ax2.tick_params(colors=INK2)
for sp in ax2.spines.values(): sp.set_color(MUTED)
ax2.legend(loc='lower right',frameon=False,fontsize=9,labelcolor=INK2)
ax2.set_title('Relative error',color=INK,fontsize=11,loc='left')

ac,cc=fit(D,cam); ae,ce=fit(D,enc); ao,co=fit(D,otos)
fig.suptitle(f'vevov distance regression  —  camera {100*(ac-1):+.2f}%/cm {cc:+.2f} cm,  '
             f'encoder {100*(ae-1):+.2f}%/cm {ce:+.2f} cm,  OTOS {100*(ao-1):+.2f}%/cm {co:+.2f} cm',
             color=INK,fontsize=12)
fig.tight_layout(rect=(0,0,1,0.93)); fig.savefig(OUT,dpi=160)
print(f'wrote {OUT}  ({len(D)} trials, {len(rows)} legs)')
print(f'  camera  = {ac:.5f}*cmd {cc:+.3f}  -> scale {100*(ac-1):+.2f}%, fixed {cc:+.2f} cm')
print(f'  encoder = {ae:.5f}*cmd {ce:+.3f}')
print(f'  OTOS    = {ao:.5f}*cmd {co:+.3f}')
acn,ccn=fit(D,cnt)
print(f'  counts  = {acn:.5f}*cmd {ccn:+.3f}   (re-derived from posl/posr)')
