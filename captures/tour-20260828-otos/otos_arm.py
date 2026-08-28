"""Re-measure vevov's OTOS lever arm on the REBUILT chassis.

The baked arm (x -38.2 mm) was measured 2026-08-21, before the front
caster came off and the drive wheels moved forward. That moved the
centre of rotation, so the arm is stale -- and a stale arm is worse than
none: it silently mis-corrects every world-frame reading.

Right now applyArm() has NOT run (it only ever fired from worldReady()
inside a RUN handler, the context that hangs), so the OTOS is reporting
the SENSOR's own path. That is exactly what makes the arm measurable:
pivot in place and the sensor traces a circle of radius |arm| about the
centre of rotation. Same least-squares fit used for the camera tag:

    otos_i = C + R(theta_i) . arm

Turns are MOVE_X (0.75 deg accurate) and the robot is centred first so
the pivots cannot walk it into a rail.
"""
import math, re, statistics as st, subprocess, time
from vradio import Robot

CAM='arducam-ov9782-usb-camera'
FX,FY=67.15,44.65
def ang(a): return (a+math.pi)%(2*math.pi)-math.pi
def cam():
    out=subprocess.run(['aprilcam','camera','tags',CAM],capture_output=True,
                       text=True,timeout=10).stdout
    m=re.search(r'apriltag 53\s+world=\(\s*(-?[\d.]+),\s*(-?[\d.]+)\)\s+yaw=(-?[\d.]+)',out)
    return (float(m.group(1)),float(m.group(2)),float(m.group(3))) if m else None
def pose(n=6):
    for _ in range(n):
        p=cam()
        if p: return p
        time.sleep(0.3)
    return None
def frames(ls):
    o=[]
    for t in ls:
        p=t.split()
        if len(p)==13 and p[0]=='t':
            try: o.append([int(v) for v in p[1:]])
            except ValueError: pass
    return o
def solve(rd):
    A,b=[],[]
    for (x,y,th) in rd:
        c,s=math.cos(th),math.sin(th)
        A.append([1,0,c,-s]); b.append(x)
        A.append([0,1,s, c]); b.append(y)
    n=4
    M=[[sum(A[k][i]*A[k][j] for k in range(len(A))) for j in range(n)] for i in range(n)]
    v=[sum(A[k][i]*b[k] for k in range(len(A))) for i in range(n)]
    for i in range(n):
        p=max(range(i,n),key=lambda q:abs(M[q][i]))
        M[i],M[p]=M[p],M[i]; v[i],v[p]=v[p],v[i]
        for q in range(i+1,n):
            f=M[q][i]/M[i][i]
            for c2 in range(i,n): M[q][c2]-=f*M[i][c2]
            v[q]-=f*v[i]
    o=[0.0]*n
    for i in reversed(range(n)):
        o[i]=(v[i]-sum(M[i][j]*o[j] for j in range(i+1,n)))/M[i][i]
    res=[math.hypot(o[0]+o[2]*math.cos(th)-o[3]*math.sin(th)-x,
                    o[1]+o[2]*math.sin(th)+o[3]*math.cos(th)-y) for (x,y,th) in rd]
    return o,res

r=Robot(channel=4)
print('STATUS:', r.status())
def idle(mx=45):
    t0=time.time()
    while time.time()-t0<mx:
        m=re.search(r'active=(\d+)', r.status() or '')
        if m and m.group(1)=='0': return
        time.sleep(0.4)
def turn(deg):
    r.seqd(f'MOVE_X 0 {int(round(math.radians(deg)*1000))} 100 25000', 8.0); idle()
def drive(cm):
    r.seqd(f'MOVE_X {int(cm*10)} 0 110 30000', 10.0); idle()

# centre it so 8 pivots cannot reach a rail
p=pose()
print(f'at ({p[0]:.1f},{p[1]:.1f})')
if math.hypot(p[0],p[1])>12:
    # probe heading, then aim at the origin
    p0=pose(); drive(10); p1=pose()
    off=math.degrees(ang(math.atan2(p1[1]-p0[1],p1[0]-p0[0])-p0[2]))
    for _ in range(3):
        p=pose()
        if math.hypot(p[0],p[1])<10: break
        head=p[2]+math.radians(off)
        turn(math.degrees(ang(math.atan2(-p[1],-p[0])-head)))
        p=pose(); drive(min(math.hypot(p[0],p[1]),28))
    print(f'centred at ({pose()[0]:.1f},{pose()[1]:.1f})')

r.seqd('TLM POSE',2.5); time.sleep(0.6)
print('\n--- 8 pivots of 45 deg, reading the OTOS ---')
rd=[]
for i in range(9):
    time.sleep(0.8)
    f=frames(r.raw('',1.5))
    if f:
        a=f[-1]
        rd.append((a[6]/10.0, a[7]/10.0, math.radians(a[8]/100.0)))
        print(f'  {i}: otos ({a[6]/10.0:7.2f},{a[7]/10.0:7.2f}) cm  '
              f'oh {a[8]/100.0:+7.2f} deg', flush=True)
    if i<8: turn(45.0)
r.seqd('TLM OFF',2.0); r.stop(); r.close()

if len(rd)>=4:
    (cx,cy,ox,oy),res=solve(rd)
    print(f'\n  centre of rotation, OTOS frame: ({cx:.2f}, {cy:.2f}) cm')
    print(f'  LEVER ARM: x {ox*10:+.1f} mm   y {oy*10:+.1f} mm   '
          f'|arm| {math.hypot(ox,oy)*10:.1f} mm')
    print(f'  residuals: max {max(res)*10:.1f} mm  median {st.median(res)*10:.1f} mm '
          f'(n={len(rd)})')
    print(f'\n  baked armX/armY today: -38.2 / -0.7 mm (2026-08-21, PRE-rebuild)')
    print(f'  fit quality {"GOOD -- trustworthy" if st.median(res)*10<5 else "POOR -- do not bake"}')
