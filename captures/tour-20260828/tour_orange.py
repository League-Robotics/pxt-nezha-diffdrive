"""Orange-dots square tour, with three independent paths recorded.

Dots measured off the camera frame at (+-49.6, +-29.9) -- the 100x60 cm
rectangle CLAUDE.md names. Route NE -> NW -> SW -> SE -> NE, counter-
clockwise, turning left at each corner.

Driven with MOVE_X, not WHEELS_X: measured 2026-08-27, MOVE_X turns
90 deg to within 0.75 while WHEELS_X runs ~8 deg long. A tour is four
turns, so that is ~32 deg of avoidable error. NOTE the sign difference
that goes with it -- MOVE_X positive rotation INCREASES yaw, where a
WHEELS_X +d/-d pair decreases it, so no negation belongs here.

Three recorders, deliberately independent:
  ENCODERS  telemetry x/y/h     -- the robot's own dead reckoning
  OTOS      telemetry ox/oy/oh  -- the sensor is fitted but has never
            been initialised: otosBegin() hangs the board hard enough
            to need a reflash (twice today), so it cannot be switched
            on safely. Recorded regardless so the chart can SAY that,
            rather than quietly dropping a series that was asked for.
  CAMERA    overhead AprilTag 53 -- external truth; the only one of the
            three that cannot be fooled by a wheel that slipped
plus vl/vr wheel speeds from the same frame (already mm/s).

A reader THREAD owns the socket: telemetry runs continuously at ~20 Hz
and a request/response drain would drop frames or stall the drive.
Camera sampling gets its own thread for the same reason -- each read is
a ~0.3 s subprocess and must not gate the tour.

Every leg is projected against the field BEFORE it is commanded, from a
camera fix taken immediately beforehand -- never from a remembered pose.
"""
import json, math, re, socket, subprocess, sys, threading, time

CAM='arducam-ov9782-usb-camera'
RELAY=('192.168.1.12',8760); CHANNEL,GROUP=4,10
DOTS=[(50.0,30.0),(-50.0,30.0),(-50.0,-30.0),(50.0,-30.0)]
FX,FY=67.15,44.65
OUT=sys.argv[1] if len(sys.argv)>1 else 'tour'

def ang(a): return (a+math.pi)%(2*math.pi)-math.pi
def cam_read():
    try:
        out=subprocess.run(['aprilcam','camera','tags',CAM],
                           capture_output=True,text=True,timeout=8).stdout
    except Exception: return None
    m=re.search(r'apriltag 53\s+world=\(\s*(-?[\d.]+),\s*(-?[\d.]+)\)\s+yaw=(-?[\d.]+)',out)
    return (float(m.group(1)),float(m.group(2)),float(m.group(3))) if m else None
def pose(tries=6):
    for _ in range(tries):
        p=cam_read()
        if p: return p
        time.sleep(0.3)
    return None

class Link:
    def __init__(self):
        self.s=socket.create_connection(RELAY,timeout=10); self.s.settimeout(0.3)
        self.lines=[]; self.lock=threading.Lock(); self.run=True; self._raw=b''
        self._setup()
        threading.Thread(target=self._reader,daemon=True).start()
        self.seq=1
    def _pump(self,sec):
        e=time.time()+sec; got=[]
        while time.time()<e:
            try: c=self.s.recv(8192)
            except socket.timeout: continue
            except OSError: break
            if not c: break
            self._raw+=c
            while b'\n' in self._raw:
                r,self._raw=self._raw.split(b'\n',1)
                t=r.decode('ascii','replace').strip()
                if t: got.append((time.time(),t))
        return got
    def _setup(self):
        self._pump(1.5)
        for _ in range(3):
            self.s.sendall(b'!CG %d %d\n'%(CHANNEL,GROUP)); self._pump(1.0)
            self.s.sendall(b'!GO\n'); self._pump(1.0)
            self.s.sendall(b'PING\n')
            if any(t.startswith('pong') for _,t in self._pump(2.0)): break
        else: raise RuntimeError('radio: no PONG -- robot off or relay wedged')
        self.s.sendall(b'HELLO\n')
        for _,t in self._pump(2.5):
            if 'device' in t.lower(): print('  link ->',t)
    def _reader(self):
        while self.run:
            for item in self._pump(0.2):
                with self.lock: self.lines.append(item)
    def since(self,mark):
        with self.lock: return [x for x in self.lines if x[0]>=mark]
    def send(self,line): self.s.sendall((line+'\n').encode())
    def seqd(self,verb,wait=8.0):
        for _ in range(3):
            mark=time.time(); self.send(f'{verb} #{self.seq}')
            e=time.time()+wait; nxt=None; ok=False
            while time.time()<e and not ok:
                for _,t in self.since(mark):
                    m=re.match(r'^ack (\d+)',t)
                    if m:
                        nxt=int(m.group(1))+1
                        ok = ok or t.startswith(f'ack {self.seq} ')
                    m=re.match(r'^nack (\d+)',t)
                    if m: nxt=int(m.group(1))
                time.sleep(0.1)
            if nxt is not None: self.seq=nxt
            if ok: return True
        return False
    def status(self):
        mark=time.time(); self.send('STATUS'); e=time.time()+3.0
        while time.time()<e:
            for _,t in self.since(mark):
                if t.startswith('status '): return t
            time.sleep(0.1)
        return ''
    def idle(self,maxwait=45.0):
        t0=time.time()
        while time.time()-t0<maxwait:
            m=re.search(r'active=(\d+)',self.status())
            if m and m.group(1)=='0': return
            time.sleep(0.4)
    def close(self):
        self.run=False; time.sleep(0.4)
        try: self.s.close()
        except Exception: pass

L=Link(); print('STATUS:', L.status())
def drive(cm): L.seqd(f'MOVE_X {int(round(cm*10))} 0 120 40000'); L.idle()
def turn(deg):
    if abs(deg)<1.5: return
    L.seqd(f'MOVE_X 0 {int(round(math.radians(deg)*1000))} 120 25000'); L.idle()
def safe_drive(cm,label=''):
    p=pose()
    if not p: print(f'   {label}: no camera fix, refusing'); return False
    x=p[0]+cm*math.cos(p[2]); y=p[1]+cm*math.sin(p[2])
    if abs(x)>FX-6 or abs(y)>FY-6:
        print(f'   {label}: projected ({x:.1f},{y:.1f}) leaves the field, refusing')
        return False
    drive(cm); return True

def park(tx,ty,tol=2.5):
    for _ in range(6):
        p=pose()
        if not p: return None
        if math.hypot(tx-p[0],ty-p[1])<tol: return p
        turn(math.degrees(ang(math.atan2(ty-p[1],tx-p[0])-p[2])))
        p=pose()
        if not p: return None
        safe_drive(min(math.hypot(tx-p[0],ty-p[1]),30.0),'park')
    return pose()

print('\n--- parking on the NE dot (+50,+30), facing west ---')
park(*DOTS[0])
p=pose(); print(f'   at ({p[0]:.2f},{p[1]:.2f}) yaw {math.degrees(p[2]):+.1f}')
turn(math.degrees(ang(math.pi-p[2])))
start=pose(); print(f'   aimed ({start[0]:.2f},{start[1]:.2f}) yaw {math.degrees(start[2]):+.1f}')

cam_rows=[]; sampling=True
def sampler():
    while sampling:
        q=cam_read()
        if q: cam_rows.append((time.time(),q[0],q[1],q[2]))
        time.sleep(0.1)
threading.Thread(target=sampler,daemon=True).start()

print('\n--- telemetry on, tour starting ---')
L.seqd('TLM POSE'); time.sleep(0.5)
t0=time.time(); marks=[]
for d,name in [(100.0,'NE->NW'),(60.0,'NW->SW'),(100.0,'SW->SE'),(60.0,'SE->NE')]:
    marks.append([time.time()-t0,f'leg {name}'])
    safe_drive(d,name)
    q=pose()
    print(f'   {name}: {d:.0f} cm -> camera ({q[0]:6.2f},{q[1]:6.2f})' if q
          else f'   {name}: tag lost', flush=True)
    marks.append([time.time()-t0,'turn'])
    turn(90.0)
L.seqd('TLM OFF'); time.sleep(0.6)
sampling=False; time.sleep(0.4)
end=pose(); L.seqd('STOP'); L.close()

frames=[]
for ts,t in L.lines:
    p=t.split()
    if len(p)==13 and p[0]=='t':
        try: frames.append((ts,[int(v) for v in p[1:]]))
        except ValueError: pass
with open(f'{OUT}_pose.csv','w') as f:
    f.write('t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox_mm,oy_mm,oh_cdeg\n')
    for ts,r in frames:
        f.write(f'{ts-t0:.3f},{r[1]},{r[3]},{r[4]},{r[5]},{r[6]},{r[7]},{r[8]}\n')
with open(f'{OUT}_vel.csv','w') as f:
    f.write('t_host,vl_mmps,vr_mmps\n')
    for ts,r in frames: f.write(f'{ts-t0:.3f},{r[9]},{r[10]}\n')
with open(f'{OUT}_cam.csv','w') as f:
    f.write('t_host,x_cm,y_cm,yaw_rad\n')
    for ts,x,y,h in cam_rows: f.write(f'{ts-t0:.3f},{x:.2f},{y:.2f},{h:.4f}\n')
otos_live=any(r[6] or r[7] or r[8] for _,r in frames)
json.dump({'start_world_cm':list(start) if start else None,
           'end_world_cm':list(end) if end else None,
           'frames':len(frames),'cam_samples':len(cam_rows),
           'otos_reporting':otos_live,'legs':marks,
           'rect_cm':[100.0,60.0],'verb':'MOVE_X'},
          open(f'{OUT}_meta.json','w'),indent=2)
print(f'\n  telemetry frames {len(frames)},  camera samples {len(cam_rows)}')
print(f'  OTOS reporting: {otos_live}')
if start and end:
    print(f'  camera closure: {math.hypot(end[0]-start[0],end[1]-start[1]):.2f} cm')
    print(f'  start ({start[0]:.2f},{start[1]:.2f})  end ({end[0]:.2f},{end[1]:.2f})')
