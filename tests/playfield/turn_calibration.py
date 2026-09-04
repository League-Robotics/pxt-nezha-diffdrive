#!/usr/bin/env python3
"""Turn calibration against the overhead camera -- pivots of +-90, +-107
and +-180 deg, many repeats, with wheel speeds recorded, then charts.

    uv run python tests/playfield/turn_calibration.py --robot tigez --dance
    uv run python tests/playfield/turn_calibration.py --robot tigez \
        --angles 90 107 180 --reps 4 --cruise 60 --out reports/tigez-turn-cal-20260903
    <plot venv>/bin/python tests/playfield/turn_calibration.py --render reports/tigez-turn-cal-20260903

What it does, per turn: take a rest fix from the camera (position and
heading, several samples averaged), command one in-place pivot over the
wire (`MOVE_X 0 <mrad> <cruise> <timeout>`), stream `TLM FULL` the whole
time so every frame's wheel speeds (`vl`/`vr`), duties and encoder
heading are recorded, watch the camera continuously and UNWRAP its
heading so a 180 is measurable, wait for the robot to actually come to
rest, take another rest fix, and score: camera-measured turn vs
commanded, encoder-believed turn vs commanded, overshoot (+) or
undershoot (-), centre drift, peak wheel speed, duration.

Signs alternate and angles interleave so a direction bias or a
warm-up trend shows up as structure, not as a mean. `--dance` first
runs the convention check the field rule demands (left is left, forward
is forward, comes home) on the same link and camera.

Carriers: the robot's own Pi serial daemon (`--robot <name>` resolves
`<name>._mbserial._tcp` over mDNS; or `--host/--port`), or the WiFi TCP
server (`--wifi <name|ip>`). Both are lossless line streams.

Camera: the aprilcam daemon, with the robot's tag mount REGISTERED
(tools/camlink.py's MOUNTS -- tag 57 for tigez), so the daemon reports
the centre of rotation and a corrected yaw. `--heading-offset` exists
for a tag the daemon does not correct (then robot = yaw + offset; the
dance measures which you have).

Outputs (in --out): turns.csv (one row per pivot), frames.csv (every
telemetry frame, tagged with its turn), camera.csv (every camera
sample), summary.json (fits and the suggested `rotational_slip` /
`pivot_overrun`), and after --render: wheel-speeds.png,
turn-error.png, fit.png and REPORT.md.

Calibration model (motion_engine.h): the firmware turns its wheels
|theta| * b_eff / 2 each, b_eff = trackWidth / rotationalSlip. If the
camera sees gain g = measured/commanded, the corrected slip is
slip * g; a constant offset (deg) is a per-wheel overrun of
offset_rad * b_eff / 2 mm, the `pivot_overrun` knob. Both can be tried
live with `--set rotational_slip=... pivot_overrun=...` before baking
into the robot's radio-robot-lib config.
"""
import argparse
import csv
import json
import math
import pathlib
import re
import socket
import subprocess
import sys
import threading
import time

FIELD_X, FIELD_Y = 67.15, 44.65   # [cm] half-extents, AprilTag-1 centred
SAFE_MARGIN = 25.0                # [cm] default; the field rule's own margin is 12
CAM = 'arducam-ov9782-usb-camera'
TAGS = {'tigez': 57, 'tovez': 52, 'vevov': 53}
LIGHTS = 'http://192.168.1.122/rpc/Switch.Set?id=0&on=true'   # the Shelly; they turn themselves off


def lights_on():
    """Re-assert the playfield lights (playfield-testing.md: they go out
    on their own, and a dark field reads as a vanished robot)."""
    try:
        import urllib.request
        urllib.request.urlopen(LIGHTS, timeout=3).read()
    except Exception:
        pass
TRACKWIDTH_DEFAULT_MM = 114.2     # motion_engine.h default; overridden by GET if exposed


# ------------------------------------------------------------- the link
class Link:
    """A lossless TCP line pipe (Pi serial daemon or the WiFi TCP server)
    with a background reader: every line is timestamped and kept, so
    telemetry frames streaming during a move are never lost to a read
    window, and sequenced verbs get their ack found in that log."""

    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(0.1)
        self.lines = []            # (t, line)
        self.lock = threading.Lock()
        self._seq = 0
        self._stop = threading.Event()
        self._buf = b''
        self._th = threading.Thread(target=self._reader, daemon=True)
        self._th.start()
        time.sleep(0.5)

    def _reader(self):
        while not self._stop.is_set():
            try:
                c = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not c:
                break
            self._buf += c
            while b'\n' in self._buf:
                raw, self._buf = self._buf.split(b'\n', 1)
                s = raw.decode('ascii', 'replace').strip()
                if s.startswith('< '):
                    s = s[2:]
                if s:
                    with self.lock:
                        self.lines.append((time.time(), s))

    def send(self, line):
        self.sock.sendall((line + '\n').encode())

    def since(self, t0, prefix=None):
        with self.lock:
            return [(t, s) for t, s in self.lines
                    if t >= t0 and (prefix is None or s.startswith(prefix))]

    def wait_for(self, pattern, t0, timeout):
        rx = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            for _t, s in self.since(t0):
                if rx.match(s):
                    return s
            time.sleep(0.05)
        return None

    def unseq(self, cmd, pattern, tries=3, wait=1.5):
        for _ in range(tries):
            t0 = time.time()
            self.send(cmd)
            got = self.wait_for(pattern, t0, wait)
            if got:
                return got
        return None

    def seqd(self, cmd, tries=3, wait=2.0):
        """Send a sequenced verb; returns (id, ack-or-err line or None).
        Retries resend the SAME id (a fresh one would open a gap)."""
        self._seq += 1
        wire = f'{cmd} #{self._seq}'
        for _ in range(tries):
            t0 = time.time()
            self.send(wire)
            got = self.wait_for(r'^(ack|nack|err)\s+%d\b' % self._seq, t0, wait)
            if got:
                return self._seq, got
        return self._seq, None

    def hello(self):
        got = self.unseq('HELLO', r'^device ')
        self._seq = 0
        return got

    def status(self):
        s = self.unseq('STATUS', r'^status ')
        return dict(kv.split('=', 1) for kv in s.split()[1:]) if s else {}

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def resolve_serial_service(robot, timeout=4.0):
    """`<robot>._mbserial._tcp` -> (host, port) via dns-sd -L, then the
    host's IPv4 via dns-sd -G. macOS only; pass --host/--port elsewhere."""
    def run(args):
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return p.stdout
        except subprocess.TimeoutExpired as e:
            return e.stdout if isinstance(e.stdout, str) else (e.stdout or b'').decode('utf-8', 'replace')
    out = run(['dns-sd', '-L', robot, '_mbserial._tcp', 'local.'])
    m = re.search(r'can be reached at (\S+?)\.?:(\d+)', out)
    if not m:
        raise SystemExit(f'no _mbserial._tcp service named {robot!r} on the LAN')
    host, port = m.group(1), int(m.group(2))
    out = run(['dns-sd', '-G', 'v4', host])
    ip = next((c for c in out.split() if re.match(r'^\d+\.\d+\.\d+\.\d+$', c)), None)
    return ip or host, port


RELAY_HOST, RELAY_PORT = 'torture', 8760   # the micro:bit relay pool


def robot_radio(robot):
    """(channel, group) from the robot's radio-robot-lib config."""
    import json
    path = pathlib.Path('/Volumes/Proj/proj/RobotProjects/radio-robot-lib/config/robots') / f'{robot}.json'
    c = json.loads(path.read_text()).get('connection', {})
    return int(c['radio_channel']), int(c.get('radio_group', 10))


class RelayLink(Link):
    """The robot over the torture relay pool: the same line pipe after
    the relay's control-plane setup (`!CG <ch> <grp>`, `!GO`). LOSSY --
    66-83 % per-line delivery measured -- so seqd()'s retries matter and
    telemetry frames will have gaps."""

    def __init__(self, channel, group, host=RELAY_HOST, port=RELAY_PORT):
        super().__init__(host, port)
        time.sleep(1.0)
        for c in ('!ECHO OFF', f'!CG {channel} {group}', '!GO'):
            self.send(c)
            time.sleep(0.5)


def open_link(a):
    if a.radio:
        ch, grp = robot_radio(a.robot)
        return RelayLink(ch, grp), f'radio relay ch {ch} grp {grp} ({RELAY_HOST}:{RELAY_PORT})'
    if a.wifi:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
        import wifilink
        host = a.wifi if re.match(r'^\d+\.\d+\.\d+\.\d+$', a.wifi) else wifilink.discover(a.wifi)
        return Link(host, 7654), f'WiFi TCP {host}:7654'
    if a.host:
        return Link(a.host, a.port), f'serial daemon {a.host}:{a.port}'
    host, port = resolve_serial_service(a.robot)
    return Link(host, port), f'{a.robot} serial daemon {host}:{port}'


# ------------------------------------------------------------ the camera
class Camera:
    """One aprilcam daemon connection; `fix()` averages rest samples;
    `Tracker` samples continuously for unwrapped heading during a turn."""

    def __init__(self, tag, heading_offset_deg=0.0, cam=CAM):
        from aprilcam.mcp import connection as _conn
        self.D = _conn.ConnectionManager().resolve()
        self.tag = tag
        self.cam = cam
        self.off = heading_offset_deg
        self.samples = []          # (t, x, y, heading_deg, speed)
        self.lock = threading.Lock()
        self._track = threading.Event()
        self._th = None

    def raw(self):
        for rec in self.D.get_tags(self.cam).tags:
            if rec.tag.number == self.tag:
                return rec
        return None

    def sample(self):
        r = self.raw()
        if r is None:
            return None
        h = (math.degrees(r.yaw_rad) + self.off + 180) % 360 - 180
        sp = r.speed or 0.0
        s = (time.time(), r.world.x, r.world.y, h, sp)
        with self.lock:
            self.samples.append(s)
        return s

    def fix(self, n=8, gap=0.05):
        xs = ys = sy = cy = 0.0
        got = 0
        for _ in range(n * 2):
            s = self.sample()
            if s is not None:
                xs += s[1]; ys += s[2]
                sy += math.sin(math.radians(s[3])); cy += math.cos(math.radians(s[3]))
                got += 1
                if got >= n:
                    break
            time.sleep(gap)
        if not got:
            return None
        return xs / got, ys / got, math.degrees(math.atan2(sy, cy))

    def start_tracking(self, hz=15.0):
        self._track.set()
        def run():
            period = 1.0 / hz
            while self._track.is_set():
                t = time.time()
                self.sample()
                dt = period - (time.time() - t)
                if dt > 0:
                    time.sleep(dt)
        self._th = threading.Thread(target=run, daemon=True)
        self._th.start()

    def stop_tracking(self):
        self._track.clear()
        if self._th:
            self._th.join(timeout=1.0)

    def settle(self, timeout=10.0, still_cm_s=0.6, still_n=5):
        """Wait for the camera to see the robot at rest."""
        t0 = time.time(); still = 0
        while time.time() - t0 < timeout:
            s = self.sample()
            if s is not None:
                still = still + 1 if s[4] < still_cm_s else 0
                if still >= still_n:
                    return True
            time.sleep(0.06)
        return False

    def unwrapped_turn(self, t0, t1):
        with self.lock:
            hs = [s[3] for s in self.samples if t0 <= s[0] <= t1]
        total, prev = 0.0, None
        for h in hs:
            if prev is not None:
                total += (h - prev + 180) % 360 - 180
            prev = h
        return total, len(hs)


def wrap(d):
    return (d + 180) % 360 - 180


# ----------------------------------------------------------- the sweep
def check_safe(pose, margin=SAFE_MARGIN):
    x, y = pose[0], pose[1]
    if abs(x) > FIELD_X - margin or abs(y) > FIELD_Y - margin:
        return (f'robot at ({x:.1f}, {y:.1f}) cm is within {margin:.0f} cm of a '
                f'rail (limits +-{FIELD_X}, +-{FIELD_Y}); move it toward the middle')
    return None


def one_turn(link, cam, deg, cruise, timeout_ms, cols, out_frames, turn_idx, settle_s):
    a = cam.fix()
    if a is None:
        return None, 'no camera fix before the turn'
    st0 = link.status()
    cam.start_tracking()
    t_start = time.time()
    mrad = int(round(math.radians(deg) * 1000))
    tid, ack = link.seqd(f'MOVE_X 0 {mrad} {cruise} {timeout_ms}', wait=3.0)
    if not ack or not ack.startswith('ack'):
        cam.stop_tracking()
        return None, f'MOVE_X not accepted: {ack}'
    # Wait until the robot reports this move resolved (done=<id>), then
    # until the camera sees it at rest.
    reason = None
    end = time.time() + timeout_ms / 1000.0 + 5.0
    while time.time() < end:
        st = link.status()
        if st.get('done') == str(tid):
            reason = st.get('reason')
            break
        time.sleep(0.25)
    cam.settle(timeout=settle_s + 8.0)
    time.sleep(settle_s)
    t_end = time.time()
    cam.stop_tracking()
    b = cam.fix()
    if b is None:
        return None, 'no camera fix after the turn'
    unwrapped, n = cam.unwrapped_turn(t_start, t_end)
    # Snap the rest-to-rest difference onto the unwrapped total: rest fixes
    # are precise, the tracker decides which lap.
    rest_diff = wrap(b[2] - a[2])
    laps = round((unwrapped - rest_diff) / 360.0)
    camera_deg = rest_diff + 360.0 * laps
    # telemetry frames for this turn
    frames = []
    for t, s in link.since(t_start - 0.05, 't '):
        parts = s.split()[1:]
        if cols and len(parts) == len(cols):
            f = dict(zip(cols, parts)); f['t'] = t
            frames.append(f)
    enc_h = None
    if frames:
        try:
            enc_h = (int(frames[-1]['h']) - int(frames[0]['h'])) / 100.0
        except (KeyError, ValueError):
            enc_h = None
    vl = [abs(int(f.get('vl', 0))) for f in frames]
    vr = [abs(int(f.get('vr', 0))) for f in frames]
    moving = [f for f in frames if abs(int(f.get('vl', 0))) > 5 or abs(int(f.get('vr', 0))) > 5]
    dur = (moving[-1]['t'] - moving[0]['t']) if len(moving) > 1 else 0.0
    for f in frames:
        out_frames.append({'turn': turn_idx, 'commanded': deg, 't_rel': round(f['t'] - t_start, 3),
                           **{k: f.get(k, '') for k in cols}})
    row = {
        'turn': turn_idx, 'commanded': deg, 'cruise': cruise, 'id': tid, 'reason': reason,
        'camera_deg': round(camera_deg, 2), 'error_deg': round(camera_deg - deg, 2),
        'unwrapped_deg': round(unwrapped, 2), 'cam_samples': n,
        'encoder_deg': None if enc_h is None else round(enc_h, 2),
        'encoder_error_deg': None if enc_h is None else round(enc_h - deg, 2),
        'x0': round(a[0], 2), 'y0': round(a[1], 2), 'x1': round(b[0], 2), 'y1': round(b[1], 2),
        'drift_cm': round(math.hypot(b[0] - a[0], b[1] - a[1]), 2),
        'peak_vl': max(vl) if vl else None, 'peak_vr': max(vr) if vr else None,
        'duration_s': round(dur, 2), 'frames': len(frames),
        'ready_before': st0.get('ready'),
    }
    return row, None


def run_sweep(link, cam, a, out):
    out.mkdir(parents=True, exist_ok=True)
    # telemetry on, FULL columns
    tid, ack = link.seqd('TLM FULL', wait=2.0)
    t0 = time.time() - 3.0
    cols = None
    for _ in range(20):
        for _, s in link.since(t0, 'thdr '):
            cols = s.split()[1:]
        if cols:
            break
        time.sleep(0.1)
    if not cols:
        raise SystemExit('no thdr after TLM FULL -- telemetry not streaming')
    print(f'telemetry columns: {cols}')

    # interleaved, sign-alternating schedule
    plan = []
    for rep in range(a.reps):
        for ang in a.angles:
            sign = 1 if rep % 2 == 0 else -1
            plan.append(sign * ang)
            plan.append(-sign * ang)
    print(f'{len(plan)} pivots: {plan}')

    rows, frames_out = [], []
    print(f"{'#':>3} {'cmd':>6} {'camera':>8} {'err':>7} {'enc':>8} {'encerr':>7} {'drift':>6} {'peakL':>6} {'peakR':>6} {'dur':>5}  reason")
    for i, deg in enumerate(plan, 1):
        lights_on()
        pose = cam.fix()
        bad = check_safe(pose, a.margin) if pose else 'no camera fix'
        if bad:
            print(f'STOP: {bad}')
            break
        row, err = one_turn(link, cam, deg, a.cruise, a.timeout_ms, cols, frames_out, i, a.settle)
        if err:
            print(f'{i:3d} {deg:6d}  -- {err}')
            continue
        rows.append(row)
        print(f"{i:3d} {deg:6d} {row['camera_deg']:8.1f} {row['error_deg']:7.1f} "
              f"{str(row['encoder_deg']):>8} {str(row['encoder_error_deg']):>7} {row['drift_cm']:6.1f} "
              f"{str(row['peak_vl']):>6} {str(row['peak_vr']):>6} {row['duration_s']:5.1f}  {row['reason']}")
        _write_csv(out / 'turns.csv', rows)
        _write_csv(out / 'frames.csv', frames_out)
        time.sleep(a.pause)
    link.seqd('TLM OFF', wait=1.5)
    with cam.lock:
        cam_rows = [{'t': s[0], 'x': s[1], 'y': s[2], 'heading': s[3], 'speed': s[4]} for s in cam.samples]
    _write_csv(out / 'camera.csv', cam_rows)
    summary = analyze(rows, a)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return rows


def _write_csv(path, rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


def _fit(cmds, meas):
    """Least squares meas = gain*cmd + offset (sign-aware: offset is the
    per-turn overshoot in the turn's own direction)."""
    n = len(cmds)
    if n < 2:
        return None, None
    # regress |meas| on |cmd| with the sign folded in: m*sign = g*c*sign + off
    xs = [abs(c) for c in cmds]
    ys = [m * (1 if c > 0 else -1) for c, m in zip(cmds, meas)]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None, None
    g = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return g, my - g * mx


def analyze(rows, a):
    if not rows:
        return {}
    cmds = [r['commanded'] for r in rows]
    meas = [r['camera_deg'] for r in rows]
    g, off = _fit(cmds, meas)
    by = {}
    for r in rows:
        key = f"{'+' if r['commanded'] > 0 else '-'}{abs(r['commanded'])}"
        by.setdefault(key, []).append(r['error_deg'])
    per = {k: {'n': len(v), 'mean_err': round(sum(v) / len(v), 2),
               'min': min(v), 'max': max(v)} for k, v in by.items()}
    lefts = [r['error_deg'] for r in rows if r['commanded'] > 0]
    rights = [r['error_deg'] for r in rows if r['commanded'] < 0]
    b_eff = a.trackwidth_mm / a.slip_now
    suggested = None
    if g:
        # overshoot in the turn direction: error_deg>0 on a left turn means
        # over-rotation; the fit's `off` is the signed per-turn overrun.
        slip_new = a.slip_now * g
        overrun_mm = max(0.0, math.radians(off) * b_eff / 2.0 + a.overrun_now)
        suggested = {'rotational_slip': round(slip_new, 4),
                     'pivot_overrun_mm': round(overrun_mm, 2),
                     'model': 'camera = gain*cmd + offset; slip_new = slip*gain; '
                              'overrun_new = overrun + offset_rad*b_eff/2'}
    return {
        'robot': a.robot, 'cruise_mm_s': a.cruise, 'n_turns': len(rows),
        'slip_during_run': a.slip_now, 'pivot_overrun_during_run_mm': a.overrun_now,
        'trackwidth_assumed_mm': a.trackwidth_mm, 'b_eff_mm': round(b_eff, 2),
        'fit_gain': None if g is None else round(g, 4),
        'fit_offset_deg': None if off is None else round(off, 2),
        'mean_err_left_deg': round(sum(lefts) / len(lefts), 2) if lefts else None,
        'mean_err_right_deg': round(sum(rights) / len(rights), 2) if rights else None,
        'per_command': per,
        'mean_abs_err_deg': round(sum(abs(e) for e in [r['error_deg'] for r in rows]) / len(rows), 2),
        'mean_drift_cm': round(sum(r['drift_cm'] for r in rows) / len(rows), 2),
        'suggested': suggested,
    }


# ------------------------------------------------------------- the dance
def dance(link, cam, cruise, turns_only=False, margin=SAFE_MARGIN):
    """Convention check: +90, +180, +90 must read as left turns summing to
    a lap; +20 cm must move along the heading. Gate is convention, not
    accuracy (field-dance-first rule). `turns_only` skips the drive legs
    -- pivots move nothing, so they are safe anywhere the robot clears
    the rails by its own half-diagonal; a drive is not, unless the
    robot is in the middle of the field."""
    home = cam.fix()
    bad = check_safe(home, margin) if home else 'no camera fix'
    if bad:
        raise SystemExit(f'DANCE: {bad}')
    print(f'home ({home[0]:.1f}, {home[1]:.1f}) h={home[2]:.1f}')
    fails = []
    def turn(deg):
        a = cam.fix(); cam.start_tracking(); t0 = time.time()
        tid, ack = link.seqd(f'MOVE_X 0 {int(round(math.radians(deg)*1000))} {cruise} 9000', wait=3.0)
        end = time.time() + 12
        while time.time() < end:
            if link.status().get('done') == str(tid):
                break
            time.sleep(0.25)
        cam.settle(); time.sleep(0.8); t1 = time.time(); cam.stop_tracking()
        b = cam.fix()
        unw, n = cam.unwrapped_turn(t0, t1)
        got = wrap(b[2] - a[2]) + 360 * round((unw - wrap(b[2] - a[2])) / 360)
        ok = abs(wrap(got - deg)) <= 12 and abs(got) > 5
        print(f'turn {deg:+4d}: camera {got:+7.1f} (unwrapped {unw:+7.1f}, {n} samples) '
              f'{"PASS" if ok else "**FAIL**"}')
        if not ok:
            fails.append(f'turn {deg:+}')
    def drive(cm):
        a = cam.fix()
        tid, ack = link.seqd(f'MOVE_X {int(cm*10)} 0 200 10000', wait=3.0)
        end = time.time() + 12
        while time.time() < end:
            if link.status().get('done') == str(tid):
                break
            time.sleep(0.25)
        cam.settle(); time.sleep(0.8)
        b = cam.fix()
        dx, dy = b[0]-a[0], b[1]-a[1]
        brg = math.degrees(math.atan2(dy, dx))
        want = a[2] if cm > 0 else a[2] + 180
        dirn = wrap(brg - want)
        dist = math.hypot(dx, dy)
        ok = dist > 5 and abs(dirn) < 25
        print(f'drive {cm:+4d} cm: moved {dist:5.1f} cm at bearing off-heading {dirn:+6.1f} deg '
              f'{"PASS" if ok else "**FAIL**"}')
        if not ok:
            fails.append(f'drive {cm:+}')
    turn(90); turn(180); turn(90)
    if turns_only:
        print('(drive legs skipped: --dance-turns-only)')
    else:
        drive(20); drive(-40); drive(20)
    end = cam.fix()
    back = math.hypot(end[0]-home[0], end[1]-home[1])
    print(f'returned home within {back:.1f} cm; net heading {wrap(end[2]-home[2]):+.1f} deg')
    if back > 8:
        fails.append('return home')
    if fails:
        print('DANCE FAILED: ' + ', '.join(fails))
        return False
    print('DANCE PASSED -- left is left, forward is forward, and it comes home.')
    return True


# ------------------------------------------------------------- rendering
def render(out):
    """Charts + REPORT.md from the CSVs. Runs under any interpreter with
    matplotlib (the project venv has none; use a scratch venv)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out = pathlib.Path(out)
    turns = list(csv.DictReader(open(out / 'turns.csv')))
    frames = list(csv.DictReader(open(out / 'frames.csv')))
    summary = json.loads((out / 'summary.json').read_text()) if (out / 'summary.json').exists() else {}
    for r in turns:
        for k in ('commanded', 'camera_deg', 'error_deg', 'drift_cm', 'duration_s'):
            r[k] = float(r[k])
        r['turn'] = int(r['turn'])
        r['encoder_error_deg'] = float(r['encoder_error_deg']) if r.get('encoder_error_deg') not in ('', 'None', None) else None

    # 1. wheel speeds per turn
    by_turn = {}
    for f in frames:
        by_turn.setdefault(int(f['turn']), []).append(f)
    n = len(by_turn)
    ncols = 4
    nrows = max(1, math.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 2.6 * nrows), squeeze=False)
    for ax in axes.flat:
        ax.axis('off')
    for i, (tn, fs) in enumerate(sorted(by_turn.items())):
        ax = axes.flat[i]; ax.axis('on')
        t = [float(f['t_rel']) for f in fs]
        ax.plot(t, [int(f['vl']) for f in fs], label='vl', lw=1.2)
        ax.plot(t, [int(f['vr']) for f in fs], label='vr', lw=1.2)
        row = next((r for r in turns if r['turn'] == tn), None)
        title = f"#{tn} cmd {row['commanded']:+.0f} -> cam {row['camera_deg']:+.1f}" if row else f'#{tn}'
        ax.set_title(title, fontsize=9)
        ax.set_xlabel('s', fontsize=8); ax.set_ylabel('mm/s', fontsize=8)
        ax.tick_params(labelsize=7); ax.axhline(0, color='k', lw=0.5)
        if i == 0:
            ax.legend(fontsize=7)
    fig.suptitle('Wheel speeds per pivot (telemetry vl / vr)')
    fig.tight_layout(); fig.savefig(out / 'wheel-speeds.png', dpi=110); plt.close(fig)

    # 2. turn error by commanded angle, left vs right
    fig, ax = plt.subplots(figsize=(7, 4))
    for sign, color, label in ((1, 'tab:blue', 'left (+)'), (-1, 'tab:red', 'right (-)')):
        rs = [r for r in turns if (r['commanded'] > 0) == (sign > 0)]
        ax.scatter([abs(r['commanded']) for r in rs], [r['error_deg'] for r in rs], c=color, label=f'{label} camera', alpha=0.8)
        rs_e = [r for r in rs if r['encoder_error_deg'] is not None]
        ax.scatter([abs(r['commanded']) + 2 for r in rs_e], [r['encoder_error_deg'] for r in rs_e], marker='x', c=color, label=f'{label} encoders', alpha=0.6)
    ax.axhline(0, color='k', lw=0.6)
    ax.set_xlabel('commanded pivot [deg]'); ax.set_ylabel('measured - commanded [deg]  (+ = overshoot)')
    ax.set_title('Pivot error vs commanded angle'); ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out / 'turn-error.png', dpi=110); plt.close(fig)

    # 3. fit: signed measured vs commanded
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.scatter([r['commanded'] for r in turns], [r['camera_deg'] for r in turns], s=18)
    lim = max(abs(r['commanded']) for r in turns) * 1.15
    ax.plot([-lim, lim], [-lim, lim], 'k--', lw=0.7, label='ideal')
    g, off = summary.get('fit_gain'), summary.get('fit_offset_deg')
    if g is not None:
        xs = [-lim, -1, 1, lim]
        ax.plot(xs, [g * x + (off if x > 0 else -off) for x in xs], 'r-', lw=1, label=f'fit gain {g:.3f}, offset {off:+.1f} deg')
    ax.set_xlabel('commanded [deg]'); ax.set_ylabel('camera [deg]'); ax.legend(fontsize=8); ax.grid(alpha=0.3)
    ax.set_title('Measured vs commanded')
    fig.tight_layout(); fig.savefig(out / 'fit.png', dpi=110); plt.close(fig)

    # 4. REPORT.md
    lines = [f"# Turn calibration -- {summary.get('robot', '?')} -- {out.name}", '',
             f"{len(turns)} camera-scored pivots at cruise {summary.get('cruise_mm_s')} mm/s, "
             f"rotational_slip {summary.get('slip_during_run')}, pivot_overrun {summary.get('pivot_overrun_during_run_mm')} mm "
             f"(b_eff {summary.get('b_eff_mm')} mm).", '',
             '![turn error](turn-error.png)', '', '![fit](fit.png)', '', '![wheel speeds](wheel-speeds.png)', '',
             '| commanded | n | mean error [deg] | min | max |', '|---|---|---|---|---|']
    for k, v in sorted(summary.get('per_command', {}).items(), key=lambda kv: (kv[0][0], float(kv[0][1:]))):
        lines.append(f"| {k} | {v['n']} | {v['mean_err']:+.2f} | {v['min']:+.1f} | {v['max']:+.1f} |")
    lines += ['', f"Fit: camera = **{summary.get('fit_gain')}** x commanded **{summary.get('fit_offset_deg'):+}** deg; "
                  f"mean |error| {summary.get('mean_abs_err_deg')} deg; left mean {summary.get('mean_err_left_deg')}, "
                  f"right mean {summary.get('mean_err_right_deg')}; mean centre drift {summary.get('mean_drift_cm')} cm.", '']
    if summary.get('suggested'):
        s = summary['suggested']
        lines += [f"Suggested: `SET rotational_slip {s['rotational_slip']}`, `SET pivot_overrun {s['pivot_overrun_mm']}` ({s['model']}).", '']
    lines += ['| # | cmd | camera | err | encoder err | drift cm | peak vl | peak vr | dur s | reason |', '|---|---|---|---|---|---|---|---|---|---|']
    for r in turns:
        enc = '' if r['encoder_error_deg'] is None else f"{r['encoder_error_deg']:+.1f}"
        lines.append(f"| {r['turn']} | {r['commanded']:+.0f} | {r['camera_deg']:+.1f} | {r['error_deg']:+.1f} | "
                     f"{enc} | {r['drift_cm']:.1f} | "
                     f"{r.get('peak_vl')} | {r.get('peak_vr')} | {r['duration_s']:.1f} | {r.get('reason')} |")
    (out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(f'rendered {out}/REPORT.md, wheel-speeds.png, turn-error.png, fit.png')


def compare(dirs, out):
    """One chart across robots/runs: per-angle direction-folded error
    (mean, sd) side by side, plus a +90 wheel-speed overlay."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    angles, data = None, []
    for d in dirs:
        d = pathlib.Path(d)
        rows = list(csv.DictReader(open(d / 'turns.csv')))
        summ = json.loads((d / 'summary.json').read_text()) if (d / 'summary.json').exists() else {}
        label = f"{summ.get('robot', d.name)} ({d.name})"
        angs = sorted(set(int(abs(float(r['commanded']))) for r in rows))
        angles = angles or angs
        stats = {}
        for ang in angs:
            e = [float(r['error_deg']) * (1 if float(r['commanded']) > 0 else -1) for r in rows if abs(float(r['commanded'])) == ang]
            enc = [float(r['encoder_error_deg']) * (1 if float(r['commanded']) > 0 else -1) for r in rows
                   if abs(float(r['commanded'])) == ang and r.get('encoder_error_deg') not in ('', 'None', None)]
            stats[ang] = (sum(e) / len(e), (sum((x - sum(e) / len(e)) ** 2 for x in e) / len(e)) ** 0.5, len(e),
                          sum(enc) / len(enc) if enc else float('nan'))
        data.append((label, stats, d))
    fig, ax = plt.subplots(figsize=(9, 5))
    w = 0.8 / max(1, len(data))
    for i, (label, stats, _) in enumerate(data):
        xs = [k + (i - (len(data) - 1) / 2) * w for k in range(len(angles))]
        ax.bar(xs, [stats[a][0] for a in angles], width=w, yerr=[stats[a][1] for a in angles], capsize=3, label=label)
        ax.scatter(xs, [stats[a][3] for a in angles], marker='x', color='k', zorder=3)
    ax.axhline(0, color='k', lw=0.8); ax.set_xticks(range(len(angles))); ax.set_xticklabels([f'{a} deg' for a in angles])
    ax.set_ylabel('camera over (+) / under (-) [deg]; x = encoder-believed'); ax.legend(fontsize=8); ax.grid(axis='y', alpha=0.3)
    ax.set_title('Pivot error by robot')
    fig.tight_layout(); fig.savefig(out / 'compare-error.png', dpi=120); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4))
    for label, _stats, d in data:
        frames = list(csv.DictReader(open(d / 'frames.csv')))
        tn = next((int(f['turn']) for f in frames if float(f['commanded']) == angles[0]), None)
        fs = [f for f in frames if int(f['turn']) == tn]
        ax.plot([float(f['t_rel']) for f in fs], [int(f['vr']) for f in fs], label=f'{label} vr')
    ax.set_title(f'+{angles[0]} deg pivot: right wheel speed'); ax.set_xlabel('s'); ax.set_ylabel('mm/s'); ax.legend(fontsize=7); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out / 'compare-wheel-speed.png', dpi=120); plt.close(fig)
    lines = ['# Pivot comparison', '', '| robot / run | ' + ' | '.join(f'{a} deg mean (sd, n) / encoder' for a in angles) + ' |',
             '|---|' + '---|' * len(angles)]
    for label, stats, _ in data:
        lines.append(f'| {label} | ' + ' | '.join(f'{stats[a][0]:+.1f} ({stats[a][1]:.1f}, {stats[a][2]}) / {stats[a][3]:+.1f}' for a in angles) + ' |')
    lines += ['', '![error](compare-error.png)', '', '![wheel speed](compare-wheel-speed.png)', '']
    (out / 'COMPARE.md').write_text('\n'.join(lines))
    print(f'wrote {out}/COMPARE.md, compare-error.png, compare-wheel-speed.png')


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot', default='tigez')
    ap.add_argument('--host'); ap.add_argument('--port', type=int)
    ap.add_argument('--wifi', metavar='NAME|IP')
    ap.add_argument('--radio', action='store_true',
                    help="drive over the torture relay pool on the robot's own channel/group (lossy)")
    ap.add_argument('--tag', type=int)
    ap.add_argument('--heading-offset', type=float, default=0.0,
                    help='deg added to the camera yaw (0 when the tag mount is registered)')
    ap.add_argument('--angles', type=int, nargs='+', default=[90, 107, 180])
    ap.add_argument('--reps', type=int, default=4, help='repeats per angle AND sign')
    ap.add_argument('--cruise', type=int, default=60, help='wheel speed [mm/s] for the pivot (0 = firmware default)')
    ap.add_argument('--timeout-ms', type=int, default=9000)
    ap.add_argument('--settle', type=float, default=1.0)
    ap.add_argument('--pause', type=float, default=0.5)
    ap.add_argument('--set', nargs='*', default=[], metavar='FIELD=VALUE', help='SET wire fields before the sweep')
    ap.add_argument('--trackwidth-mm', type=float, default=TRACKWIDTH_DEFAULT_MM)
    ap.add_argument('--dance', action='store_true', help='run the convention check first')
    ap.add_argument('--dance-only', action='store_true')
    ap.add_argument('--dance-turns-only', action='store_true',
                    help='dance with the three pivots only (robot not in the middle of the field)')
    ap.add_argument('--margin', type=float, default=SAFE_MARGIN,
                    help='cm from a rail the robot must clear before anything moves (pivots only: 12)')
    ap.add_argument('--out', default=None)
    ap.add_argument('--render', metavar='DIR', help='only render charts + REPORT.md from an existing --out')
    ap.add_argument('--compare', nargs='+', metavar='DIR', help='overlay several runs/robots into --out')
    a = ap.parse_args()
    if a.render:
        render(a.render); return 0
    if a.compare:
        compare(a.compare, a.out or 'reports/turn-compare'); return 0

    tag = a.tag or TAGS.get(a.robot)
    if not tag:
        ap.error(f'no tag known for {a.robot}; pass --tag')
    out = pathlib.Path(a.out or f'reports/{a.robot}-turn-cal-{time.strftime("%Y%m%d-%H%M")}')

    link, where = open_link(a)
    print(f'link: {where}')
    banner = link.hello()
    print(f'robot: {banner}')
    if not banner:
        raise SystemExit('no HELLO banner -- robot not answering')
    st = link.status()
    print(f'status: {st}')
    if st.get('ready') != '1':
        print('WARNING: ready=0 -- the kernel needs a first move before it reports ready; continuing')
    for kv in a.set:
        k, v = kv.split('=', 1)
        tid, ack = link.seqd(f'SET {k} {v}', wait=2.0)
        print(f'SET {k} {v} -> {ack}')
    def get(field):
        tid, ack = link.seqd(f'GET {field}', wait=2.0)
        t0 = time.time() - 2.5
        for _, s in link.since(t0, f'get {field} '):
            return float(s.split()[2])
        return None
    a.slip_now = get('rotational_slip') or 0.952
    a.overrun_now = get('pivot_overrun') or 0.0
    print(f'rotational_slip={a.slip_now} pivot_overrun={a.overrun_now} (live), trackwidth assumed {a.trackwidth_mm} mm')

    lights_on()
    cam = Camera(tag, a.heading_offset)
    pose = cam.fix()
    if pose is None:
        raise SystemExit(f'camera does not see tag {tag} -- lights? robot on the field?')
    print(f'camera: tag {tag} at ({pose[0]:.1f}, {pose[1]:.1f}) cm heading {pose[2]:.1f} deg')
    bad = check_safe(pose, a.margin)
    if bad:
        raise SystemExit(f'not safe to pivot: {bad}')

    try:
        if a.dance or a.dance_only:
            if not dance(link, cam, a.cruise, a.dance_turns_only, a.margin) or a.dance_only:
                return 1 if not a.dance_only else 0
        run_sweep(link, cam, a, out)
    finally:
        link.seqd('STOP', wait=1.0)
        link.close()
    print(f'wrote {out}; render with: <plot venv>/bin/python {sys.argv[0]} --render {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
