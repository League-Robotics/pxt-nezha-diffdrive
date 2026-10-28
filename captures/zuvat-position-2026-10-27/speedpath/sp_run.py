#!/usr/bin/env python3
"""Ticket 006 driver: speed_path A/B on zuvat via the loki tunnel (127.0.0.1:7654).
usage: sp_run.py wheels|legs|refresh PATH [outdir]
Writes one CSV per run (t_ms,posl,posr,vl,vr,i2cf,host_s) plus <kind>_p<PATH>_summary.json lines.
All distances are ENCODER truth (0.079322 mm/count)."""
import socket, sys, time, json, os
MM = 0.079322
kind, path = sys.argv[1], int(sys.argv[2])
out = sys.argv[3] if len(sys.argv) > 3 else os.path.dirname(os.path.abspath(__file__))
s = socket.create_connection(("127.0.0.1", 7654), timeout=3); s.settimeout(0.02)
buf = b''; cols = None; frames = []; lines = []; nid = 1
def toint(x):
    try: return int(x)
    except ValueError: return int(x, 16)
def pump(dur):
    global buf, cols
    end = time.monotonic() + dur
    while time.monotonic() < end:
        try: d = s.recv(4096)
        except socket.timeout: continue
        buf += d
        while b'\n' in buf:
            l, buf = buf.split(b'\n', 1); l = l.decode(errors='replace').strip()
            if l.startswith('thdr '): cols = l.split()[1:]
            elif l.startswith('t ') and cols:
                v = l.split()[1:]
                if len(v) == len(cols):
                    r = dict(zip(cols, map(toint, v))); r['host'] = time.monotonic(); frames.append(r)
            else: lines.append(l)
def send(line, seq=True):
    global nid
    if seq: line = f"{line} #{nid}"; nid += 1
    s.sendall(line.encode() + b"\n"); pump(0.15)
def reply(prefix):
    for l in reversed(lines):
        if l.startswith(prefix): return l
def getv(name):
    del lines[:]; send(f"GET {name}"); pump(0.2); return reply(f"get {name}")
def status():
    del lines[:]; s.sendall(b"STATUS\n"); pump(0.4); return reply("status")
pump(0.4); s.sendall(b"HELLO\n"); pump(0.4)
send("STOP"); send("TLM FULL")
send(f"SET speed_path {path}"); rb = getv("speed_path"); print("readback:", rb)
assert rb and float(rb.split()[-1]) == path, rb
os.makedirs(out, exist_ok=True)
def settle():
    send("STOP"); pump(0.8)
def run(name, cmd, hold, done=None):
    """send cmd, record until `hold` s elapsed (or done()), STOP, settle. returns frames of run."""
    settle(); pump(0.3)
    i0 = len(frames); t0 = time.monotonic()
    send(cmd)
    if done is None: pump(max(0, hold - (time.monotonic() - t0)))
    else:
        pump(1.0)
        while time.monotonic() - t0 < hold:
            pump(0.3)
            f = frames[i0:]
            tail = [x for x in f if x['host'] > time.monotonic() - 0.6]
            if len(tail) > 5 and len({(x['posl'], x['posr']) for x in tail}) == 1: break
    send("STOP"); pump(0.8)
    fr = frames[i0:]
    with open(f"{out}/{name}.csv", "w") as fh:
        fh.write("t_ms,posl,posr,vl,vr,i2cf,host_s\n")
        for x in fr: fh.write(f"{x['now']},{x['posl']},{x['posr']},{x['vl']},{x['vr']},{x['i2cf']},{x['host']-t0:.3f}\n")
    return fr, t0
res = []
if kind == "wheels":
    for rep in range(2):
        for sp in (40, 70, 120, 200, 250):
            sign = 1 if rep == 0 else -1
            nm = f"wheels_p{path}_{sp}_{'fwd' if sign>0 else 'rev'}"
            fr, t0 = run(nm, f"WHEELS_V {sign*sp} {sign*sp} 2400", 2.0)
            print(nm, len(fr), "frames", flush=True)
elif kind == "legs":
    for i in range(6):
        sign = 1 if i % 2 == 0 else -1
        nm = f"leg_p{path}_{i}_{'fwd' if sign>0 else 'rev'}"
        fr, t0 = run(nm, f"MOVE_X {sign*600} 0 150 8000", 9.0, done=True)
        print(nm, len(fr), "frames", flush=True)
elif kind == "refresh":
    fr, t0 = run(f"refresh_p{path}_120", "WHEELS_V 120 120 3600", 3.0)
    print("refresh", len(fr))
settle(); st = status(); print(st)
