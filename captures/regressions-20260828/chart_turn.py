"""Turn regression: commanded vs encoder vs camera vs OTOS.

Camera and OTOS report ORIENTATION, which WRAPS -- a 720 deg turn looks
like 0 -- so their error is taken as wrap(final - (start + A)), exact
for any A while the error itself stays under 180 deg. The encoder's `h`
accumulates, so it also gives the unwrapped total directly; the two are
plotted together and must agree.

Directions are separated throughout. A bias fixed in the WORLD frame
shows as the two directions moving oppositely; a SCALE error shows as
both growing with |A| in the same proportional sense. That distinction
is the whole reason the sweep runs both ways.
"""
import csv, math, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

CSV=sys.argv[1] if len(sys.argv)>1 else 'turn_sweep.csv'
OUT=sys.argv[2] if len(sys.argv)>2 else 'turn_sweep.png'
S1,S2,S3,S4='#2a78d6','#eb6834','#2e9e6b','#8b5cf6'
INK,INK2,MUTED='#0b0b0b','#52514e','#b9b7b0'
def wrap(d): return (d+180.0)%360.0-180.0

rows=list(csv.DictReader(open(CSV)))
data={+1:[],-1:[]}
for r in rows:
    A=float(r['cmd_deg']); d=int(r['dir'])
    cam0=math.degrees(float(r['cam_yaw0_rad'])); cam1=math.degrees(float(r['cam_yaw1_rad']))
    cam_err=wrap(cam1-cam0-d*A)
    enc=(float(r['enc_h1_cdeg'])-float(r['enc_h0_cdeg']))/100.0
    enc_err=enc-d*A
    oto_err=wrap((float(r['otos_h1_cdeg'])-float(r['otos_h0_cdeg']))/100.0-d*A)
    dl=int(r['posl1'])-int(r['posl0']); dr=int(r['posr1'])-int(r['posr0'])
    data[d].append((A,cam_err,enc_err,oto_err,dl,dr))
for d in data: data[d].sort()

fig=plt.figure(figsize=(13,5.6),facecolor='#fcfcfb')
ax=fig.add_subplot(1,2,1); ax.set_facecolor('#fcfcfb')
ax.axhline(0,lw=1.2,color=MUTED)
for d,mk,nm in ((+1,'o','CCW (left)'),(-1,'s','CW (right)')):
    v=data[d]
    if not v: continue
    ax.plot([x[0] for x in v],[x[1] for x in v],lw=1.6,marker=mk,ms=3.5,
            color=S3 if d>0 else S2, label=f'camera {nm}')
ax.set_xlabel('commanded turn [deg]',color=INK2)
ax.set_ylabel('camera error [deg]',color=INK2)
ax.grid(True,lw=.5,color=MUTED,alpha=.5); ax.tick_params(colors=INK2)
for sp in ax.spines.values(): sp.set_color(MUTED)
ax.legend(loc='upper left',frameon=False,fontsize=9,labelcolor=INK2)
ax.set_title('Turn error vs camera truth',color=INK,fontsize=11,loc='left')

ax2=fig.add_subplot(1,2,2); ax2.set_facecolor('#fcfcfb')
ax2.axhline(0,lw=1.2,color=MUTED)
for d,mk in ((+1,'o'),(-1,'s')):
    v=data[d]
    if not v: continue
    lab='CCW' if d>0 else 'CW'
    ax2.plot([x[0] for x in v],[x[2] for x in v],lw=1.5,marker=mk,ms=3,
             color=S1,alpha=1.0 if d>0 else 0.55,label=f'encoder {lab}')
    ax2.plot([x[0] for x in v],[x[3] for x in v],lw=1.5,marker=mk,ms=3,
             color=S4,alpha=1.0 if d>0 else 0.55,label=f'OTOS {lab}')
ax2.set_xlabel('commanded turn [deg]',color=INK2)
ax2.set_ylabel('error [deg]',color=INK2)
ax2.grid(True,lw=.5,color=MUTED,alpha=.5); ax2.tick_params(colors=INK2)
for sp in ax2.spines.values(): sp.set_color(MUTED)
ax2.legend(loc='upper left',frameon=False,fontsize=8,labelcolor=INK2,ncol=2)
ax2.set_title('Encoder and OTOS error',color=INK,fontsize=11,loc='left')

def fit(v,i):
    xs=[x[0] for x in v]; ys=[x[i] for x in v]
    n=len(xs); sx=sum(xs); sy=sum(ys); sxx=sum(x*x for x in xs)
    sxy=sum(a*b for a,b in zip(xs,ys))
    a=(n*sxy-sx*sy)/(n*sxx-sx*sx); return a,(sy-a*sx)/n
bits=[]
for d,nm in ((+1,'CCW'),(-1,'CW')):
    if len(data[d])>=3:
        a,c=fit(data[d],1)
        bits.append(f'{nm} camera {100*a:+.2f}%/deg {c:+.2f} deg')
fig.suptitle('vevov turn regression  —  '+',   '.join(bits),color=INK,fontsize=12)
fig.tight_layout(rect=(0,0,1,0.93)); fig.savefig(OUT,dpi=160)
print(f'wrote {OUT}   ({len(rows)} turns)')
for d,nm in ((+1,'CCW'),(-1,'CW')):
    v=data[d]
    if len(v)<3: continue
    a,c=fit(v,1)
    print(f'  {nm}: camera err = {100*a:+.3f}%/deg * A {c:+.3f} deg  (n={len(v)})')
    ae,ce=fit(v,2); ao,co=fit(v,3)
    print(f'       encoder err = {100*ae:+.3f}%/deg {ce:+.3f}   '
          f'OTOS err = {100*ao:+.3f}%/deg {co:+.3f}')
