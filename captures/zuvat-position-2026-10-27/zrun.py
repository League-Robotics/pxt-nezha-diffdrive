#!/usr/bin/env python3
"""zrun.py OUTFILE  step...   step = line | @<seconds> (wait, logging) | @STOPAT:<line>:<seconds>
Logs every received line with host monotonic time (s since start) to OUTFILE.
'!' prefix = unsequenced-send raw. Sequenced lines get #n automatically (n from env NEXT)."""
import socket, sys, time, os
out=open(sys.argv[1],'w')
s=socket.create_connection(("127.0.0.1",7654),timeout=3); s.settimeout(0.01)
t0=time.monotonic(); buf=b''
def pump(dur):
    global buf
    end=time.monotonic()+dur
    while time.monotonic()<end:
        try: d=s.recv(4096)
        except socket.timeout: continue
        now=time.monotonic()-t0
        buf+=d
        while b'\n' in buf:
            l,buf=buf.split(b'\n',1)
            out.write(f"{now:.4f} < {l.decode(errors='replace').rstrip()}\n")
    out.flush()
def send(line):
    out.write(f"{time.monotonic()-t0:.4f} > {line}\n"); out.flush()
    s.sendall(line.encode()+b"\n")
n=int(os.environ.get('NEXT','1'))
UNSEQ=('HELLO','PING','ID','VER','STATUS','HELP','ESTOP')
pump(0.3)
for st in sys.argv[2:]:
    if st.startswith('@'): pump(float(st[1:])); continue
    verb=st.split()[0]
    if verb=='HELLO': n=1
    if verb in UNSEQ: send(st)
    else: send(f"{st} #{n}"); n+=1
    pump(0.05)
print("next id", n)
