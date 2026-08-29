"""Does the OTOS report REAL translation? Camera-truthed, on the floor.

Bench proof only got as far as "it is being sampled": oh tracked, but
ox/oy stayed 0 because the robot sat on a bench and the OTOS is an
OPTICAL FLOOR sensor. On the field it must now show travel.

Three readings of the same leg, independent:
  OTOS      telemetry ox/oy   -- optical, sees the floor
  ENCODER   telemetry x/y     -- dead reckoning, cannot see slip
  CAMERA    AprilTag 53       -- external truth

Heading is MEASURED from a probe leg rather than read off a field whose
convention just changed (the daemon now reports both `yaw` and
`heading`, and they disagree by ~29 deg here). Assuming which one is
the robot's heading is exactly the kind of thing that has bitten this
rig, so it gets measured.
"""
import math, re, subprocess, time
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

r=Robot(channel=4)
print('STATUS:', r.status())
def idle(mx=45):
    t0=time.time()
    while time.time()-t0<mx:
        m=re.search(r'active=(\d+)', r.status() or '')
        if m and m.group(1)=='0': return
        time.sleep(0.4)

# --- measure which way "forward" actually is -------------------------
p0=pose(); print(f'\nstart ({p0[0]:.2f},{p0[1]:.2f}) reported yaw {math.degrees(p0[2]):+.1f}')
r.seqd('MOVE_X 120 0 100 15000',6.0); idle()
p1=pose()
brg=math.atan2(p1[1]-p0[1], p1[0]-p0[0])
off=math.degrees(ang(brg-p0[2]))
print(f'probe leg moved {math.hypot(p1[0]-p0[0],p1[1]-p0[1]):.1f} cm, '
      f'true bearing = reported yaw {off:+.1f} deg')

# --- the real leg, with all three recorders --------------------------
r.seqd('TLM POSE',2.5); time.sleep(0.6)
p0=pose()
head=p0[2]+math.radians(off)
D=40.0
xp,yp=p0[0]+D*math.cos(head), p0[1]+D*math.sin(head)
if abs(xp)>FX-8 or abs(yp)>FY-8:
    D=-D; xp,yp=p0[0]+D*math.cos(head), p0[1]+D*math.sin(head)
print(f'\ndriving {D:+.0f} cm -> projected ({xp:.1f},{yp:.1f})')
before=frames(r.raw('',2.0))
out=r.seqd(f'MOVE_X {int(D*10)} 0 120 25000', 10.0); idle()
after=frames(out)+frames(r.raw('',2.5))
p1=pose()
r.seqd('TLM OFF',2.0); r.stop(); r.close()

if before and after and p0 and p1:
    b,a=before[-1],after[-1]
    otos=math.hypot(a[6]-b[6], a[7]-b[7])/10.0
    enc =math.hypot(a[3]-b[3], a[4]-b[4])/10.0
    camd=math.hypot(p1[0]-p0[0], p1[1]-p0[1])
    print(f'\n  commanded {abs(D):6.2f} cm')
    print(f'  CAMERA    {camd:6.2f} cm   (truth)')
    print(f'  ENCODER   {enc:6.2f} cm   ({100*(enc/camd-1):+5.1f}% vs camera)')
    print(f'  OTOS      {otos:6.2f} cm   ({100*(otos/camd-1):+5.1f}% vs camera)')
    nz=sum(1 for f in after if f[6] or f[7] or f[8])
    print(f'\n  non-zero OTOS frames {nz}/{len(after)}')
    print(f'  => {"OTOS IS TRACKING TRANSLATION" if otos>5 else "OTOS STILL FLAT"}')
    m=re.search(r'i2cf=(\d+)', r.status() or '')
