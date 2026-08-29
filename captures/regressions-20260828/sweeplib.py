"""Shared rig for the distance and turn regressions.

Driven over GAUTI USB, not the radio. Measured 2026-08-28: a foreign
transmitter is issuing commands on channel 4 (`MOVE_X 950 0 120 60000
#2` arrived interleaved with our own STOP reply, and vevov was found
running away at 5.4 cm/s). A competing command mid-sweep would corrupt
trials silently, and gauti's USB link is point-to-point. Gauti rides ON
the robot, so it adds no drag.

Telemetry is TLM FULL (20 fields), not POSE (12): FULL is the only mode
carrying `posl`/`posr`, the RAW ENCODER COUNTS, so encoder position can
be recomputed offline from counts rather than trusted as integrated.

  thdr seq now flags x y h ox oy oh vl vr i2cf cyc posl posr dutl dutr
       lexc wrng cycovr
    0   1    2   3 4 5  6  7  8  9 10   11  12   13   14   15   16
"""
import math, re, subprocess, time
from vevov import Robot as _R

CAM='arducam-ov9782-usb-camera'
FX,FY=67.15,44.65          # true field half-extents [cm]
MARGIN=7.0                 # keep the CENTRE this far off the wall
NE=(50.0,30.0)             # the north-east orange dot
PERIM=[100.0,60.0,100.0,60.0]   # NE->NW->SW->SE->NE

I={'seq':0,'now':1,'flags':2,'x':3,'y':4,'h':5,'ox':6,'oy':7,'oh':8,
   'vl':9,'vr':10,'i2cf':11,'cyc':12,'posl':13,'posr':14}

def ang(a): return (a+math.pi)%(2*math.pi)-math.pi

def cam_once():
    try:
        out=subprocess.run(['aprilcam','camera','tags',CAM],
                           capture_output=True,text=True,timeout=10).stdout
    except Exception: return None
    m=re.search(r'apriltag 53\s+world=\(\s*(-?[\d.]+),\s*(-?[\d.]+)\)\s+yaw=(-?[\d.]+)',out)
    return (float(m.group(1)),float(m.group(2)),float(m.group(3))) if m else None

def cam(tries=8):
    """A camera fix, retried. Returns None only if the tag is really gone
    -- which on this rig usually means the room lights went out."""
    for _ in range(tries):
        p=cam_once()
        if p: return p
        time.sleep(0.4)
    return None

def parse(lines):
    out=[]
    for t in lines:
        p=t.split()
        if len(p)==21 and p[0]=='t':
            try: out.append([int(v) for v in p[1:]])
            except ValueError: pass
    return out

class Rig:
    def __init__(self):
        self.r=_R()
        self.r.seqd('STOP',2.0)
        self.r.seqd('TLM FULL',3.0)
        time.sleep(0.8)
        self.buf=[]
    def drain(self,sec=1.0):
        f=parse(self.r.raw('',sec))
        if f: self.buf=f
        return f
    def frame(self,tries=6):
        """Latest telemetry frame; retried because a busy link can miss."""
        for _ in range(tries):
            f=self.drain(1.0)
            if f: return f[-1]
        return self.buf[-1] if self.buf else None
    def status(self): return self.r.status()
    def idle(self,maxwait=90.0):
        t0=time.time()
        while time.time()-t0<maxwait:
            m=re.search(r'active=(\d+)', self.r.status() or '')
            if m and m.group(1)=='0': return True
            time.sleep(0.5)
        return False
    def move(self,dist_mm,rot_mrad,cruise=120,timeout=45000):
        self.r.seqd(f'MOVE_X {int(dist_mm)} {int(rot_mrad)} {cruise} {timeout}', 6.0)
        return self.idle()
    def drive(self,cm,cruise=120):
        return self.move(round(cm*10),0,cruise,max(20000,int(abs(cm)*250)))
    def turn(self,deg,cruise=110):
        if abs(deg)<0.5: return True
        return self.move(0,round(math.radians(deg)*1000),cruise,
                         max(15000,int(abs(deg)*200)))
    def snap(self):
        """One synchronised reading of all three instruments + counts."""
        c=cam(); f=self.frame()
        return {'cam':c,'f':f}
    def close(self):
        try:
            self.r.seqd('TLM OFF',2.0); self.r.stop()
        except Exception: pass
        self.r.close()

def safe(x,y): return abs(x)<=FX-MARGIN and abs(y)<=FY-MARGIN

def heading_offset(rig):
    """MEASURE which way the reported yaw points, rather than assume.
    The daemon reports both `yaw` and `heading` for a mounted tag and
    they differ by ~29 deg here; `yaw` measured +0.74 deg off travel
    bearing on 2026-08-28, but that is re-checked every run."""
    p0=cam()
    if not p0: return None
    rig.drive(12)
    p1=cam()
    if not p1 or math.hypot(p1[0]-p0[0],p1[1]-p0[1])<3: return None
    return math.degrees(ang(math.atan2(p1[1]-p0[1],p1[0]-p0[0])-p0[2]))

def park(rig,tx,ty,off,tol=2.5,tries=6):
    """Drive to (tx,ty). `off` is the measured yaw->travel offset."""
    for _ in range(tries):
        p=cam()
        if not p: return None
        if math.hypot(tx-p[0],ty-p[1])<tol: return p
        head=p[2]+math.radians(off)
        rig.turn(math.degrees(ang(math.atan2(ty-p[1],tx-p[0])-head)))
        p=cam()
        if not p: return None
        head=p[2]+math.radians(off)
        d=min(math.hypot(tx-p[0],ty-p[1]),30.0)
        nx,ny=p[0]+d*math.cos(head),p[1]+d*math.sin(head)
        if not safe(nx,ny): return p
        rig.drive(d)
    return cam()

def face(rig,deg,off,tol=2.0):
    """Point the robot at world bearing `deg`."""
    for _ in range(4):
        p=cam()
        if not p: return None
        head=p[2]+math.radians(off)
        e=math.degrees(ang(math.radians(deg)-head))
        if abs(e)<tol: return p
        rig.turn(e)
    return cam()

def legs_for(total):
    """Split `total` cm into straight legs along the orange-dots
    rectangle, so a 200 cm run fits a 110 cm box. Turns BETWEEN legs are
    not measured -- only the straight segments are."""
    out=[]; i=0; left=total
    while left>1e-6:
        seg=min(PERIM[i%4],left)
        out.append(seg); left-=seg; i+=1
    return out
