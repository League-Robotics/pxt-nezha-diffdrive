#!/usr/bin/env python3
"""Ticket 007 driver: kernel-default A/B on zuvat via the loki tunnel (127.0.0.1:7654).
usage: kd_run.py EXPERIMENT [outdir]     (see EXPS below)
Each trial: apply the setting's SETs, MOVE_X, record TLM FULL frames until still, STOP.
Settings are interleaved (A fwd, B fwd, A rev, B rev, ...). ENCODER truth, 0.079322 mm/count."""
import socket, sys, time, os, json
MM = 0.079322
BOOT = {"v_floor": 70, "decel": 400, "stop_distance": 0, "pid_ki": None, "omega_floor": 20}
EXPS = {}
def leg(cruise): return f"MOVE_X {{s}}600 0 {cruise} 8000"
EXPS["a"] = dict(cmd=leg(150), n=4, settings={"boot": {}, "dec1000_sd0.3": {"decel": 1000, "stop_distance": 0.3}})
EXPS["b"] = dict(cmd=leg(150), n=4, settings={"vf70": {}, "vf50": {"v_floor": 50}})
EXPS["c150"] = dict(cmd=leg(150), n=4, settings={"ki_boot": {}, "ki0": {"pid_ki": 0}})
EXPS["c250"] = dict(cmd=leg(250), n=4, settings={"ki_boot": {}, "ki0": {"pid_ki": 0}})
EXPS["after150"] = dict(cmd=leg(150), n=4, settings={"after": {"decel": 1000, "stop_distance": 0.3}})
B = {"decel": 1000, "stop_distance": 0.3}
EXPS["b2"] = dict(cmd=leg(150), n=4, settings={"vf70": dict(B), "vf50": dict(B, v_floor=50)})
EXPS["c150b"] = dict(cmd=leg(150), n=4, settings={"ki6": dict(B), "ki0": dict(B, pid_ki=0)})
EXPS["c250b"] = dict(cmd=leg(250), n=4, settings={"ki6": dict(B), "ki0": dict(B, pid_ki=0)})
for _c in (20, 40, 60, 80, 120):
    for _sg in (1, -1):
        pass
EXPS["omega"] = dict(cmd="MOVE_X 0 {s}1571 {c} 6000", n=2, settings={f"c{c}": {} for c in (20, 40, 60, 80, 120)})
EXPS["omf20"] = dict(cmd="MOVE_X 0 {s}1571 20 6000", n=2, settings={"of40": {"omega_floor": 40}})
EXPS["om10"] = dict(cmd="MOVE_X 0 {s}175 150 6000", n=4, settings={"of20": {}, "of40": {"omega_floor": 40}})
exp = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
E = EXPS[exp]
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
def send(line):
    global nid
    line = f"{line} #{nid}"; nid += 1
    s.sendall(line.encode() + b"\n"); pump(0.15)
def getv(name):
    del lines[:]; send(f"GET {name}"); pump(0.2)
    for l in reversed(lines):
        if l.startswith(f"get {name}"): return float(l.split()[-1])
pump(0.4); s.sendall(b"HELLO\n"); pump(0.4)
send("STOP"); send("TLM FULL")
send("SET position_mode 0"); send("SET v_max 250")
boot = {k: getv(k) for k in BOOT}
print("boot readback", boot, flush=True)
os.makedirs(out, exist_ok=True)
meta = dict(boot=boot, exp=exp)
def apply(vals):
    for k, v in boot.items():
        if v is not None: send(f"SET {k} {v}")
    for k, v in vals.items(): send(f"SET {k} {v}")
    for k, v in vals.items():
        rb = getv(k); print("  set", k, v, "readback", rb, flush=True)
names = list(E["settings"])
trial = 0
for rep in range(E["n"]):
    sign = 1 if rep % 2 == 0 else -1
    for nm in names:
        apply(E["settings"][nm])
        send("STOP"); pump(0.8)
        i0 = len(frames); t0 = time.monotonic()
        send(E["cmd"].format(s="" if sign > 0 else "-", c=int(nm[1:]) if exp == "omega" else 0))
        pump(1.5)
        while time.monotonic() - t0 < 12:
            pump(0.3)
            tail = [x for x in frames[i0:] if x['host'] > time.monotonic() - 0.6]
            if len(tail) > 5 and len({(x['posl'], x['posr']) for x in tail}) == 1: break
        send("STOP"); pump(0.8)
        fr = frames[i0:]
        fn = f"{exp}_{nm}_{trial}_{'fwd' if sign>0 else 'rev'}.csv"
        with open(f"{out}/{fn}", "w") as fh:
            fh.write("t_ms,posl,posr,vl,vr,i2cf,host_s\n")
            for x in fr: fh.write(f"{x['now']},{x['posl']},{x['posr']},{x['vl']},{x['vr']},{x['i2cf']},{x['host']-t0:.3f}\n")
        print(fn, len(fr), "frames", flush=True)
        trial += 1
apply({})
send("STOP"); send("TLM OFF")
print("restored; readback", {k: getv(k) for k in boot}, flush=True)
