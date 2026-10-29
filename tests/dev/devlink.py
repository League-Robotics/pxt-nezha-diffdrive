"""Shared plumbing for the tests/dev camera-truthed robot scripts.

Run from the repo root:
    uv run --with intelhex --with zeroconf --with psutil python tests/dev/<script>.py
"""
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, str(REPO.parent / 'mbtools' / 'src'))

from camlink import Cam  # noqa: E402
from field import DOTS, wrap  # noqa: E402
from mbtools.registry.client import SOCKET_ENV_VAR, RegistryClient, find_local_api_address  # noqa: E402
from mbtools.registry.remote_client import RemoteRegistryClient  # noqa: E402
from mbtools.serial import remote_connect  # noqa: E402
from robotlink import Link  # noqa: E402

LIGHTS = 'http://192.168.6.122/rpc/Switch.Set?id=0&on=true'
CAPTURES = REPO / 'captures'

__all__ = ['Cam', 'DOTS', 'wrap', 'open_serial', 'fix', 'settled', 'still_pose', 'status', 'send_move', 'tlm', 'movex', 'CAPTURES']


def open_serial(name='vevov'):
    """Serial link to `name` through whichever registry node holds it.
    DEVLINK_NODE=host[:port] skips the local registry when it has not peered."""
    node = os.environ.get('DEVLINK_NODE')
    if node:
        host, _, port = node.partition(':')
        port = port or '7440'
    else:
        with RegistryClient(find_local_api_address(None, SOCKET_ENV_VAR)) as c:
            dev = c.find(name)
        host, _, port = dev['endpoint'].rpartition(':')
    rc = RemoteRegistryClient(host, int(port))
    rc.__enter__()
    dev = rc.find(name)
    link = Link(remote_connect.connect(rc, dev['uid']), False)
    link.hello()
    return link


def fix(cam, n):
    """Median pose (x cm, y cm, heading deg); turns the garage lights on if the tag is lost."""
    for _ in range(3):
        p = cam.fix(n=n)
        if p is not None:
            return p
        urllib.request.urlopen(LIGHTS, timeout=5).read()
        time.sleep(5)
    raise SystemExit('no camera fix even with lights on')


def settled(cam, n=15):
    """A fix taken only once the robot has stopped moving on camera."""
    prev = fix(cam, 5)
    for _ in range(40):
        time.sleep(0.3)
        cur = fix(cam, 5)
        if math.hypot(cur[0] - prev[0], cur[1] - prev[1]) < 0.1 and abs(wrap(cur[2] - prev[2])) < 0.5:
            return fix(cam, n)
        prev = cur
    raise SystemExit('robot never settled on camera')


def still_pose(cam, fixes=8, n=25):
    """Averaged at-rest pose. Single fixes' headings scatter ~0.7 deg sd
    (tag pose ambiguity), so a frame-defining heading wants several."""
    ps = [settled(cam, n) for _ in range(fixes)]
    h0 = ps[0][2]
    dh = sum(wrap(p[2] - h0) for p in ps) / len(ps)
    return (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps), wrap(h0 + dh))


def status(link):
    link.send('STATUS')
    st = next((s for s in link.lines(1.0) if s.startswith('status ')), '')
    return dict(kv.split('=', 1) for kv in st.split()[1:] if '=' in kv)


def send_move(link, cmd, limit=30.0, on_poll=None):
    """Send a motion verb and return once it has started AND finished.
    Waiting for active=0 alone races a command still in flight."""
    before = status(link).get('done')
    link.send(cmd)
    t0 = time.time()
    started = False
    while time.time() - t0 < limit:
        if on_poll:
            on_poll()
        st = status(link)
        if st.get('active') == '1' or st.get('done') != before:
            started = True
        if started and st.get('active') == '0':
            return st
        time.sleep(0.1)
    return status(link)


def tlm(link, secs=1.2, tries=3):
    """Latest TLM FULL row as a dict: x y [mm], h oh [cdeg], ox oy [mm], posl posr [counts]."""
    for _ in range(tries):
        row = _tlm_once(link, secs)
        if row:
            return row
    raise SystemExit('no TLM row from the robot')


def _tlm_once(link, secs):
    hdr, row = [], {}
    link.send('TLM FULL')
    for s in link.lines(secs):
        f = s.split()
        if f and f[0] == 'thdr':
            hdr = f[1:]
        elif f and f[0] == 't' and hdr and len(f) - 1 == len(hdr):
            try:
                row = dict(zip(hdr, (float(v) for v in f[1:])))
            except ValueError:
                pass
    link.send('TLM OFF')
    list(link.lines(0.4))
    return row


def movex(link, cam, mm, deg, cruise):
    send_move(link, f'MOVE_X {int(round(mm))} {int(round(math.radians(deg) * 1000))} {cruise} 15000')
    return settled(cam)
