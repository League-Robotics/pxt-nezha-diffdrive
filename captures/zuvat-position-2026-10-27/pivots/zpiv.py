#!/usr/bin/env python3
"""zpiv.py OUTCSV MODE CRUISE KIND:VALUE... ; KIND = pivot (deg) or leg (mm)
One connection; HELLO, SET position_mode MODE, TLM POSE. For each item: MOVE_X (pivot deg sent as integer mrad), log frames until
both wheels have been at rest >=0.5 s after moving, then record one row per item and write all frames
to <OUTCSV minus .csv>_frames.csv (run,t,seq,now,flags,x,y,h,vl,vr,i2cf). h units: centideg (see notes).
Never sends 0x1D or ESTOP; sends STOP between runs."""
import socket, sys, time, csv
out=sys.argv[1]; mode=int(sys.argv[2]); cruise=int(sys.argv[3]); items=sys.argv[4:]
s=socket.create_connection(("127.0.0.1",7654),timeout=3); s.settimeout(0.005)
t0=time.monotonic(); buf=b''; n=1; cols=None
def poll():
    global buf,cols
    res=[]
    try: d=s.recv(4096)
    except socket.timeout: return res
    now=time.monotonic()-t0; buf+=d
    while b'\n' in buf:
        l,buf=buf.split(b'\n',1); l=l.decode(errors='replace').rstrip()
        if l.startswith('thdr '): cols=l.split()[1:]
        elif l.startswith('t ') and cols:
            p=l.split()[1:]
            if len(p)==len(cols): res.append((now,{c:int(v) for c,v in zip(cols,p)}))
        else: res.append((now,l))
    return res
def send(line,seq=True):
    global n
    if seq: line=f"{line} #{n}"; n+=1
    s.sendall(line.encode()+b"\n")
def run(dur):
    fr=[]; end=time.monotonic()+dur
    while time.monotonic()<end: fr+=poll()
    return fr
send('HELLO',False); run(0.4); n=1
send(f'SET position_mode {mode}'); run(0.2)
send('TLM POSE'); _pre=[f for t,f in run(0.8) if isinstance(f,dict)]
rows=[]; allf=[]; last=(_pre[-1] if _pre else None)
for k,it in enumerate(items):
    kind,val=it.split(':'); val=float(val)
    fr=run(0.4)
    st=[f for t,f in fr if isinstance(f,dict)]
    base=st[-1] if st else last
    cmd = f"MOVE_X 0 {round(val*3.14159265358979/180*1000)} {cruise} 6000" if kind=='pivot' else f"MOVE_X {val:g} 0 {cruise} 6000"
    send(cmd); tc=time.monotonic()-t0
    frames=[]; moved=False; rest_since=None; tend=time.monotonic()+7
    while time.monotonic()<tend:
        for t,f in poll():
            if isinstance(f,dict):
                frames.append((t,f))
                if f['vl'] or f['vr']: moved=True; rest_since=None
                elif moved and rest_since is None: rest_since=t
            else: frames.append((t,f))
        if moved and rest_since is not None and time.monotonic()-t0-rest_since>0.6: break
    send('STOP'); frames+=run(0.3)
    fd=[(t,f) for t,f in frames if isinstance(f,dict)]
    last=fd[-1][1] if fd else last
    for t,f in fd: allf.append((k,kind,val,t-tc,f))
    rows.append((k,kind,val,base,fd[-1][1] if fd else None,
      [l for t,l in frames if isinstance(l,str) and l.startswith('done') or isinstance(l,str) and 'reason' in l][:1]))
    print(k,kind,val,'start',base and (base['x'],base['y'],base['h'],base['i2cf']),'end',fd and (fd[-1][1]['x'],fd[-1][1]['y'],fd[-1][1]['h'],fd[-1][1]['i2cf']),flush=True)
with open(out,'w',newline='') as fh:
    w=csv.writer(fh); w.writerow('run kind value mode cruise x0 y0 h0 i2cf0 x1 y1 h1 i2cf1'.split())
    for k,kind,val,b,e,_ in rows:
        w.writerow([k,kind,val,mode,cruise,b['x'],b['y'],b['h'],b['i2cf'],e['x'],e['y'],e['h'],e['i2cf']])
with open(out[:-4]+'_frames.csv','w',newline='') as fh:
    w=csv.writer(fh); w.writerow('run kind value t seq now flags x y h vl vr i2cf'.split())
    for k,kind,val,t,f in allf: w.writerow([k,kind,val,f"{t:.4f}",f['seq'],f['now'],f['flags'],f['x'],f['y'],f['h'],f['vl'],f['vr'],f['i2cf']])
