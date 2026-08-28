"""TURN regression: commanded vs encoder vs camera vs OTOS.

Each angle is run BOTH ways -- +A then -A -- as asked, so a bias fixed
in the world frame separates from one that flips with travel direction.
Pairing them also keeps the robot near its start instead of marching
around the field.

MEASURING BIG ANGLES. The camera and the OTOS report ORIENTATION, which
wraps: a 720 deg turn looks like 0. Only the encoder's `h` accumulates.
So the error for a commanded A is taken as

    err = wrap( measured_final - (start + A) )

which is exact for any A provided the error itself is under 180 deg --
true by orders of magnitude here (errors are single-digit degrees). The
encoder additionally gives the unwrapped total directly, so the two
methods cross-check each other on every trial.

Schedule: 5 deg steps to 90 (where the fine structure is), 10 to 180,
30 to 720. Stated because it is a choice, not a measurement: a uniform
5 deg sweep to 720 would be 286 trials and hours of field time.

Re-parks on the NE dot periodically -- pivots walk slightly, and 100+
of them would otherwise drift into a rail.
"""
import csv, math, os, subprocess, sys, time
import sweeplib as S

OUT=sys.argv[1] if len(sys.argv)>1 else 'turn_sweep.csv'
if len(sys.argv)>2:
    ANGLES=[float(x) for x in sys.argv[2].split(',')]
else:
    ANGLES=([float(a) for a in range(10,91,5)]
           +[float(a) for a in range(100,181,10)]
           +[float(a) for a in range(210,721,30)])
REPARK_EVERY=8

COLS=['cmd_deg','dir','cam_x0_cm','cam_y0_cm','cam_yaw0_rad',
      'cam_x1_cm','cam_y1_cm','cam_yaw1_rad',
      'enc_h0_cdeg','enc_h1_cdeg','enc_x0_mm','enc_y0_mm','enc_x1_mm','enc_y1_mm',
      'otos_h0_cdeg','otos_h1_cdeg','otos_x0_mm','otos_y0_mm','otos_x1_mm','otos_y1_mm',
      'posl0','posr0','posl1','posr1','cyc0','cyc1','i2cf0','i2cf1','t_unix']

def ang(a): return (a+math.pi)%(2*math.pi)-math.pi
def lights_ok():
    try:
        out=subprocess.run(['curl','-s','--max-time','8',
            'http://192.168.1.122/rpc/Switch.GetStatus?id=0'],
            capture_output=True,text=True,timeout=12).stdout
        if '"output":true' in out.replace(' ',''): return True
        subprocess.run(['curl','-s','--max-time','8',
            'http://192.168.1.122/rpc/Switch.Set?id=0&on=true'],
            capture_output=True,timeout=12)
        time.sleep(9); return False
    except Exception: return True

def row(A,d,a,b):
    ca,cb=a['cam'],b['cam']; fa,fb=a['f'],b['f']; I=S.I
    return [A,d,ca[0],ca[1],ca[2],cb[0],cb[1],cb[2],
            fa[I['h']],fb[I['h']],fa[I['x']],fa[I['y']],fb[I['x']],fb[I['y']],
            fa[I['oh']],fb[I['oh']],fa[I['ox']],fa[I['oy']],fb[I['ox']],fb[I['oy']],
            fa[I['posl']],fa[I['posr']],fb[I['posl']],fb[I['posr']],
            fa[I['cyc']],fb[I['cyc']],fa[I['i2cf']],fb[I['i2cf']],
            round(time.time(),2)]

new=not os.path.exists(OUT)
fh=open(OUT,'a',newline=''); w=csv.writer(fh)
if new: w.writerow(COLS); fh.flush()

rig=S.Rig(); print('STATUS:', rig.status())
off=S.heading_offset(rig)
if off is None:
    print('cannot measure heading offset -- aborting'); rig.close(); sys.exit(1)
print(f'measured yaw->travel offset {off:+.2f} deg\n')

n=0
for A in ANGLES:
    for d in (+1,-1):
        if n%REPARK_EVERY==0:
            if not lights_ok(): print('  (lights were off -- on now)')
            if S.park(rig,*S.NE,off) is None:
                print('lost the tag while parking; stopping'); rig.close(); fh.close(); sys.exit(1)
        a=rig.snap()
        if not (a['cam'] and a['f']):
            # A lost fix is USUALLY the room lights, not the robot. The
            # counter `n` only advances on success, so gating the light
            # check on it meant that once trials started failing the
            # check never ran again -- 12 trials were lost that way on
            # 2026-08-28. Check the lights on EVERY failure instead.
            print(f'A={A} {d}: no fix -- checking lights')
            if not lights_ok(): print('   lights were OFF; on now, retrying')
            a=rig.snap()
            if not (a['cam'] and a['f']):
                print(f'A={A} {d}: still no fix, skipping'); continue
        rig.turn(d*A)
        b=rig.snap()
        if not (b['cam'] and b['f']): print(f'A={A} {d}: lost fix after turn'); continue
        w.writerow(row(A,d,a,b)); fh.flush()
        cam_err=math.degrees(ang(b['cam'][2]-a['cam'][2]-math.radians(d*A)))
        enc_tot=(b['f'][S.I['h']]-a['f'][S.I['h']])/100.0
        print(f'  A={A:6.1f} {"CCW" if d>0 else "CW ":>3}  camera err {cam_err:+7.2f} deg   '
              f'encoder total {enc_tot:+8.2f}  (err {enc_tot-d*A:+7.2f})', flush=True)
        n+=1
rig.close(); fh.close()
print(f'\nwrote {OUT}')
