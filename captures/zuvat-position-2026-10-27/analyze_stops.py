#!/usr/bin/env python3
"""Stop-timing analysis for the zuvat captures in this directory.
Frames: t seq now flags x y h ox oy oh vl vr i2cf (mm, cdeg, mm/s). x/y/h are the kernel's
wheel-encoder odometry (ENCODER truth; no camera, no OTOS on zuvat).
Command time in robot clock = host send time - min(host_rx - now) over the frames of the run
(assumes zero uplink latency, so it is EARLY by the real uplink delay, ~10-30 ms; time-to-rest is
therefore an UPPER bound)."""
import csv, re, sys
cases = [  # name, file, speed label, reference kind, ref offset after send [s] (0 = the send itself)
 ('STOP 30%',  'stop_30_run1.log',  '75 mm/s',  'cmd', 0.0, 'MOVE_X 600 @75'),
 ('STOP 100%', 'stop_100_run1.log', '250 mm/s', 'cmd', 0.0, 'MOVE_X 600 @250'),
 ('ESTOP 30%', 'estop_30_run1.log', '75 mm/s',  'cmd', 0.0, 'MOVE_X 600 @75'),
 ('ESTOP 100%','estop_100_run1.log','250 mm/s', 'cmd', 0.0, 'MOVE_X 600 @250'),
 ('deadline 30%', 'deadline_30.log', '75 mm/s', 'dl', 2.0, 'MOVE_X 600 @75 timeout 2000'),
 ('deadline 100%','deadline_100.log','250 mm/s','dl', 1.0, 'MOVE_X 600 @250 timeout 1000'),
 ('lease 30% (WHEELS_V)', 'watchdog_lease_30.log', '75 mm/s', 'dl', 1.5, 'WHEELS_V 75 75 1500'),
 ('lease 100% (WHEELS_V)','watchdog_lease_100.log','250 mm/s','dl', 1.0, 'WHEELS_V 250 250 1000'),
]
def load(fn):
    fr=[]; sends=[]
    for l in open(fn):
        m=re.match(r'([\d.]+) < t (.*)',l)
        if m:
            p=m.group(2).split()
            if len(p)==12:
                fr.append(dict(h=float(m.group(1)),seq=int(p[0]),now=int(p[1]),x=int(p[3]),y=int(p[4]),vl=int(p[9]),vr=int(p[10]),i2cf=int(p[11])))
        m=re.match(r'([\d.]+) > (STOP|ESTOP|MOVE_X|WHEELS_V)',l)
        if m: sends.append((float(m.group(1)),m.group(2)))
    return fr,sends
rows=[]
for name,fn,spd,kind,off,cmd in cases:
    fr,sends=load(fn)
    mot=[s for s in sends if s[1] in('MOVE_X','WHEELS_V')][0]
    ref=[s for s in sends if s[1] in('STOP','ESTOP')]
    t_ref=(ref[0][0] if kind=='cmd' and ref else mot[0]+off)
    offset=min(f['h']-f['now']/1000 for f in fr)
    t_ref_robot=(t_ref-offset)*1000   # ms robot clock
    pre=[f for f in fr if f['now']<=t_ref_robot]
    post=[f for f in fr if f['now']>t_ref_robot]
    a,b=pre[-1],post[0]
    xc=a['x']+(b['x']-a['x'])*(t_ref_robot-a['now'])/max(1,(b['now']-a['now'])) if a['vl']!=0 or a['vr']!=0 else a['x']
    zero=next((f for f in post if f['vl']==0 and f['vr']==0),None)
    xf=fr[-1]['x']
    if zero is None:   # ESTOP: kernel latched, telemetry frozen with stale vl/vr; use the first frozen-x frame
        zero=next(f for f in post if f['x']==fr[-1]['x'])
        xf={'ESTOP 30%':252,'ESTOP 100%':315}[name]   # first x read after SET estop_clear (estop_30_after2.log, estop_100_clear.log)
    dropout=zero['now']-a['now']
    peak=max(max(abs(f['vl']),abs(f['vr'])) for f in fr)
    rows.append(dict(case=name,speed=spd,command=cmd,capture=fn,
        ref_kind='host send of command' if kind=='cmd' else 'send+deadline/lease',
        x_at_ref_mm=round(xc,1), x_final_mm_telemetry=xf,
        travel_after_mm_telemetry=round(xf-xc,1),
        t_ref_to_first_zero_frame_ms=round(zero['now']-t_ref_robot),
        last_moving_frame_to_first_zero_ms=zero['now']-a['now'],
        last_moving_vl_vr=f"{a['vl']}/{a['vr']}", first_zero_vl_vr=f"{zero['vl']}/{zero['vr']}",
        peak_vel_mms=peak, i2cf_first=fr[0]['i2cf'], i2cf_last=fr[-1]['i2cf']))
w=csv.DictWriter(open('stop_timing.csv','w',newline=''),fieldnames=list(rows[0]))
w.writeheader(); w.writerows(rows)
for r in rows: print(r)
