"""DISTANCE regression: commanded vs encoder vs camera vs OTOS.

Every trial parks on the NE orange dot facing west, then consumes the
commanded distance along the orange-dots rectangle, turning 90 deg at
each corner. Turns are NOT measured -- only the straight legs are, and
they are summed. That is what lets a 200 cm run be measured inside a
110 cm box without calling a path with corners in it a "distance".

Rows are per LEG, appended as they are taken, so a crash or a dead
battery costs one leg rather than the whole sweep. Raw encoder COUNTS
(posl/posr) are recorded at both ends of every leg so encoder position
can be recomputed offline instead of trusted as integrated.

The room lights are re-checked every few trials: they switched
themselves off mid-run earlier today and every tag vanished.
"""
import csv, math, os, subprocess, sys, time
import sweeplib as S

OUT=sys.argv[1] if len(sys.argv)>1 else 'dist_sweep.csv'
DISTS=[float(x) for x in sys.argv[2].split(',')] if len(sys.argv)>2 \
      else [float(d) for d in range(10,201,5)]

COLS=['commanded_total_cm','leg_idx','leg_cmd_cm',
      'cam_x0_cm','cam_y0_cm','cam_yaw0_rad','cam_x1_cm','cam_y1_cm','cam_yaw1_rad',
      'enc_x0_mm','enc_y0_mm','enc_h0_cdeg','enc_x1_mm','enc_y1_mm','enc_h1_cdeg',
      'otos_x0_mm','otos_y0_mm','otos_h0_cdeg','otos_x1_mm','otos_y1_mm','otos_h1_cdeg',
      'posl0','posr0','posl1','posr1','cyc0','cyc1','i2cf0','i2cf1','t_unix']

def lights_ok():
    try:
        out=subprocess.run(['curl','-s','--max-time','8',
            'http://192.168.1.122/rpc/Switch.GetStatus?id=0'],
            capture_output=True,text=True,timeout=12).stdout
        if '"output":true' in out.replace(' ',''): return True
        subprocess.run(['curl','-s','--max-time','8',
            'http://192.168.1.122/rpc/Switch.Set?id=0&on=true'],
            capture_output=True,timeout=12)
        time.sleep(9)          # camera needs ~8 s to re-expose
        return False
    except Exception:
        return True

def row(cmd_total,leg_idx,leg_cm,a,b):
    ca,cb=a['cam'],b['cam']; fa,fb=a['f'],b['f']
    I=S.I
    return [cmd_total,leg_idx,leg_cm,
            ca[0],ca[1],ca[2],cb[0],cb[1],cb[2],
            fa[I['x']],fa[I['y']],fa[I['h']],fb[I['x']],fb[I['y']],fb[I['h']],
            fa[I['ox']],fa[I['oy']],fa[I['oh']],fb[I['ox']],fb[I['oy']],fb[I['oh']],
            fa[I['posl']],fa[I['posr']],fb[I['posl']],fb[I['posr']],
            fa[I['cyc']],fb[I['cyc']],fa[I['i2cf']],fb[I['i2cf']],
            round(time.time(),2)]

new = not os.path.exists(OUT)
fh=open(OUT,'a',newline=''); w=csv.writer(fh)
if new: w.writerow(COLS); fh.flush()

rig=S.Rig()
print('STATUS:', rig.status())
off=S.heading_offset(rig)
if off is None:
    print('cannot measure heading offset -- aborting'); rig.close(); sys.exit(1)
print(f'measured yaw->travel offset {off:+.2f} deg\n')

done=0
for D in DISTS:
    if done%6==0 and not lights_ok():
        print('  (lights were OFF -- switched on, waiting for re-expose)')
    p=S.park(rig,*S.NE,off)
    if p is None: print(f'D={D}: lost the tag while parking; stopping'); break
    p=S.face(rig,180.0,off)
    if p is None: print(f'D={D}: lost the tag while aiming; stopping'); break
    legs=S.legs_for(D); tot_cam=0.0
    print(f'D={D:6.1f} cm  legs {legs}  from ({p[0]:.1f},{p[1]:.1f})', flush=True)
    ok=True
    for i,L in enumerate(legs):
        a=rig.snap()
        if not (a['cam'] and a['f']): ok=False; break
        h=a['cam'][2]+math.radians(off)
        nx,ny=a['cam'][0]+L*math.cos(h), a['cam'][1]+L*math.sin(h)
        if not S.safe(nx,ny):
            print(f'   leg {i} would reach ({nx:.1f},{ny:.1f}) -- unsafe, stopping trial')
            ok=False; break
        rig.drive(L)
        b=rig.snap()
        if not (b['cam'] and b['f']): ok=False; break
        w.writerow(row(D,i,L,a,b)); fh.flush()
        d=math.hypot(b['cam'][0]-a['cam'][0], b['cam'][1]-a['cam'][1])
        tot_cam+=d
        print(f'   leg {i}: cmd {L:6.1f}  camera {d:6.2f} cm', flush=True)
        if i<len(legs)-1: rig.turn(90.0)
    if ok:
        print(f'   TOTAL cmd {D:6.1f}  camera {tot_cam:7.2f} cm  '
              f'({100*(tot_cam/D-1):+5.2f}%)', flush=True)
    done+=1
rig.close(); fh.close()
print(f'\nwrote {OUT}')
