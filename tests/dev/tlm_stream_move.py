"""Stream TLM FULL through one move and the rest after it, to see what the
OTOS heading does once the wheels stop (ZARU treats any change then as bias)."""
import argparse
import json
import time

from devlink import open_serial

ap = argparse.ArgumentParser()
ap.add_argument('--robot', default='vevov')
ap.add_argument('--move', default='MOVE_X 0 1571 100 8000')
ap.add_argument('--secs', type=float, default=12.0)
ap.add_argument('--log', required=True)
a = ap.parse_args()

link = open_serial(a.robot)
out = open(a.log, 'a')
hdr = []
link.send('TLM FULL')
t0 = time.time()
sent = False
while time.time() - t0 < a.secs:
    if not sent and time.time() - t0 > 1.0:
        link.send(a.move)
        sent = True
    for s in link.lines(0.2):
        f = s.split()
        if f and f[0] == 'thdr':
            hdr = f[1:]
        elif f and f[0] == 't' and hdr and len(f) - 1 == len(hdr):
            out.write(json.dumps(dict(t=time.time() - t0, move=a.move, **dict(zip(hdr, map(float, f[1:]))))) + '\n')
link.send('TLM OFF')
list(link.lines(0.5))
out.close()
link.close()
