"""Trace STATUS active/done/reason against the wheel counts through one
motion verb: does the wire say a move is finished while the wheels still
turn? Streams TLM FULL and polls STATUS every --poll seconds."""
import argparse
import json
import math
import time

from devlink import open_serial, tlm

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='tovez')
ap.add_argument('--move', help='verb line to send')
ap.add_argument('--gotow-rel', help='bx,by [mm] body-frame offset turned into a GO_TO_W from the current pose')
ap.add_argument('--secs', type=float, default=10.0)
ap.add_argument('--poll', type=float, default=0.1)
ap.add_argument('--log', required=True)
a = ap.parse_args()

link = open_serial(a.robot)
if a.gotow_rel:
    bx, by = (float(v) for v in a.gotow_rel.split(','))
    t = tlm(link)
    h = math.radians(t['h'] / 100)
    a.move = (f"GO_TO_W {int(round(t['x'] + bx * math.cos(h) - by * math.sin(h)))} "
              f"{int(round(t['y'] + bx * math.sin(h) + by * math.cos(h)))} 120 5 30000")
    print(a.move, flush=True)
out = open(a.log, 'a')
hdr = []
link.send('TLM FULL')
t0 = time.time()
sent = False
last_poll = 0.0
pos = None
prev = None
while time.time() - t0 < a.secs:
    now = time.time() - t0
    if not sent and now > 0.5:
        link.send(a.move)
        sent = True
    if now - last_poll >= a.poll:
        link.send('STATUS')
        last_poll = now
    for s in link.lines(0.05):
        f = s.split()
        if not f:
            continue
        if f[0] == 'thdr':
            hdr = f[1:]
        elif f[0] == 't' and hdr and len(f) - 1 == len(hdr):
            row = dict(zip(hdr, map(float, f[1:])))
            pos = (row['posl'], row['posr'])
            out.write(json.dumps(dict(t=round(time.time() - t0, 3), kind='tlm', **row)) + '\n')
        elif f[0] == 'status':
            st = dict(kv.split('=', 1) for kv in f[1:] if '=' in kv)
            key = (st.get('active'), st.get('done'), st.get('reason'))
            out.write(json.dumps(dict(t=round(time.time() - t0, 3), kind='status', **st)) + '\n')
            if key != prev:
                print(f'{time.time() - t0:6.2f}s  active={key[0]} done={key[1]} reason={key[2]}  wheels {pos}', flush=True)
                prev = key
link.send('TLM OFF')
list(link.lines(0.5))
last = None
for line in open(a.log):
    r = json.loads(line)
    if r['kind'] == 'tlm':
        if last is not None and (r['posl'], r['posr']) != last:
            moved_at = r['t']
        last = (r['posl'], r['posr'])
print(f'last wheel movement at {moved_at:.2f}s')
out.close()
link.close()
