#!/usr/bin/env python3
"""zstop.py LOG STARTLINE TRIGGER_MM ACTION|- [AFTER_S] [WATCH_S]
HELLO, TLM POSE, STARTLINE (sequenced). If ACTION != '-', send it when |x-x0|>=TRIGGER_MM.
Then log AFTER_S more seconds (default 1.5). Does NOT send STOP unless ACTION is STOP."""
import socket, sys, time
log=open(sys.argv[1],'w'); start=sys.argv[2]; trig=float(sys.argv[3]); act=sys.argv[4]
after=float(sys.argv[5]) if len(sys.argv)>5 else 1.5
s=socket.create_connection(("127.0.0.1",7654),timeout=3); s.settimeout(0.005)
t0=time.monotonic(); buf=b''; n=1; cols='seq now flags x y h ox oy oh vl vr i2cf'.split(); x0=None; sent=False; tsent=None
def send(line,seq=True):
    global n
    if seq: line=f"{line} #{n}"; n+=1
    log.write(f"{time.monotonic()-t0:.4f} > {line}\n"); log.flush()
    s.sendall(line.encode()+b"\n")
def poll():
    global buf,cols
    out=[]
    try: d=s.recv(4096)
    except socket.timeout: return out
    buf+=d
    while b'\n' in buf:
        l,buf=buf.split(b'\n',1); l=l.decode(errors='replace').rstrip()
        log.write(f"{time.monotonic()-t0:.4f} < {l}\n"); out.append(l)
    return out
def run(dur,cb=None):
    end=time.monotonic()+dur
    while time.monotonic()<end:
        for l in poll():
            if cb: cb(l)
send('HELLO',False); run(0.3)
n=1; send('TLM POSE'); run(0.4)
fr=[]
def cb0(l):
    global cols,x0
    if l.startswith('thdr '): cols=l.split()[1:]
    elif l.startswith('t ') and cols:
        p=l.split()[1:]
        if len(p)==len(cols): x0=int(dict(zip(cols,p))['x'])
run(0.3,cb0)
log.write(f"# x0={x0}\n")
send(start)
state={'done':False}
def cb(l):
    global cols,sent,tsent
    if l.startswith('t ') and cols and not sent and act!='-':
        p=dict(zip(cols,l.split()[1:]))
        if abs(int(p['x'])-x0)>=trig:
            sent=True; tsent=time.monotonic()-t0
            send(act, seq=(act!='ESTOP'))
end=time.monotonic()+30
while time.monotonic()<end:
    for l in poll(): cb(l)
    if act=='-' or sent: break
if act=='-': run(after+3.0,cb)
else: run(after,cb)
log.write(f"# trigger_sent_host_time={tsent}\n"); log.close()
print("x0",x0,"sent",tsent,"next",n)
