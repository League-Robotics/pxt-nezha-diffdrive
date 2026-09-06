#!/usr/bin/env python3
"""Turn calibration against the overhead camera -- pivots of +-90, +-107
and +-180 deg, many repeats, with wheel speeds recorded, then charts.

    uv run python tests/calibration/turn_calibration.py --robot tigez --dance
    uv run python tests/calibration/turn_calibration.py --robot tigez \
        --angles 90 107 180 --reps 4 --cruise 60 --out reports/tigez-turn-cal-20260903
    <plot venv>/bin/python tests/calibration/turn_calibration.py --render reports/tigez-turn-cal-20260903

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
`stop_distance` -- `pivot_overrun` on pre-029 firmware), and after --render: wheel-speeds.png,
turn-error.png, fit.png and REPORT.md.

Calibration model (motion_engine.h): the firmware turns its wheels
|theta| * b_eff / 2 each, b_eff = trackWidth / rotationalSlip. If the
camera sees gain g = measured/commanded, the corrected slip is
slip * g; a constant offset (deg) is a per-wheel overrun of
offset_rad * b_eff / 2 mm, the `stop_distance` knob (`pivot_overrun`
before sprint 029; on 029 firmware SET `lag` first, design S10.2). Both can
be tried live with `--set rotational_slip=... stop_distance=...` before baking
into the robot's radio-robot-lib config.

GATE MODES (sprint 031 ticket 007): `--mode {g1,g2,g3,g5,g6}` runs one
of sprint 029's acceptance gates instead of the sweep above -- these
were previously six standalone scripts under
captures/bench-acceptance-029-20260904d/*.py; this is the one program
now. Every mode prints a PASS/FAIL line against its own bar and writes
summary.json; every mode does its own mandatory pre-flight path check
(.claude/rules/playfield-testing.md) before arming a commanded move,
and fails loudly (SystemExit, or a printed STOP + non-zero exit) on a
missing precondition -- camera not seeing the tag, projected path
outside the margin, MOVE_X not acknowledged -- rather than silently
doing nothing.

    uv run python tests/calibration/turn_calibration.py --robot tovez --mode g1
    uv run python tests/calibration/turn_calibration.py --robot tovez --mode g2 --arcs 6
    uv run python tests/calibration/turn_calibration.py --robot tovez --mode g3 --legs 6 --leg-mm 600
    uv run python tests/calibration/turn_calibration.py --robot tovez --mode g5 --cruise-g5 200
    uv run python tests/calibration/turn_calibration.py --robot tovez --mode g6 --side-mm 500 --laps 3

| mode | folds in (was) | gate | bar (sprint 031 ticket 007) |
|---|---|---|---|
| g1 | g1_run.py | rest-heading pivot accuracy | RESTATED: mean abs err <= 1.0 deg, sd <= 1.0 deg, >= 20-sample fixes |
| g2 | g2_run.py | arc endpoint | RESTATED: endpoint <= 10 mm |
| g3 | g3_run.py | leg length + first-tick/accel (G3+G4) | unchanged |
| g5 | lag_measure.py | continuous WHEELS_V tracking | unchanged |
| g6 | g6_run.py / g6_run_500.py | square-tour closure vs. baseline | unchanged (<= 10.8 mm) |

G1 and G2 are restated because the overhead camera's own noise floor
(heading sd 1.03 deg/sample at rest, position repeatability several mm
-- see the G1_*/G2_* constants above) sits BELOW the original 0.4 deg /
5 mm bars: a "pass" the instrument cannot distinguish from a fail is
not a pass. G3 (length), G4 (first-tick/acceleration), G5 (continuous
tracking) and G6 (square closure) are unchanged -- their FAILs in
sprint 029 were drivetrain/kernel-gain findings, not instrument limits.
See tests/calibration/DESIGN.md (or this sprint's design overlay,
clasi/sprints/031-drivetrain-tuning-and-gate-acceptance-on-tovez/
design/playfield-DESIGN.md) for the full rationale.
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
TAGS = {'tigez': 57, 'tovez': 52, 'vevov': 53, 'gopiv': 54}
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools'))
import field as fieldlib  # noqa: E402  (tools/field.py -- path/margin checks, one owner)
import link as linklib  # noqa: E402  (tools/link.py -- the one sequencer + line buffer)
# Re-exported deliberately: `mount.py` and `distance.py` reach it as
# `tc.wrap`, and this program's own gates call it ~15 times. It is
# `field.wrap()` -- (-180, 180], upper end closed -- not the private
# modulo-idiom copy that lived here until sprint 034 ticket 009, which
# closed the OTHER end.
from field import wrap  # noqa: E402

# --------------------------------------------------- G1-G6 acceptance bars
#
# Sprint 029's bench-acceptance session on tovez measured the overhead
# camera's own instrument noise BEFORE any drivetrain number entered into
# it (captures/bench-acceptance-029-20260904d/g1-run.log line 1, folded
# into camera_noise_floor() below): heading at rest sd 1.03 deg/sample,
# 0.65 deg on the DIFFERENCE of two 5-sample-averaged fixes (a pivot's
# error is exactly such a difference). Position repeatability of the
# SAME stationary robot between two rest reads measured 3-7 mm
# (reports/bench-acceptance-029-20260904d.md S2, the two
# field-dance-refit runs). The original G1 (sd <= 0.4 deg, single-sample
# fixes) and G2 (endpoint <= 5 mm) bars sit BELOW that noise floor -- a
# "pass" the camera cannot distinguish from a "fail" is not a pass,
# independent of anything the drivetrain does. Restated here at roughly
# the measured noise floor (G1) and the measured position repeatability
# (G2), per this sprint's Design Rationale
# (clasi/sprints/031-drivetrain-tuning-and-gate-acceptance-on-tovez/
# design/playfield-DESIGN.md and sprint.md): averaging more samples per
# fix (G1_MIN_FIX_SAMPLES, up from 5) pushes the FIX's own sd well under
# the bar, which is the only lever available without a better fixture
# (larger tag, second tag) -- see that document for the rejected
# alternative (tightening the fixture instead of the bar) and why this
# sprint chose to restate rather than improve the fixture.
G1_MEAN_ABS_ERR_DEG = 1.0   # was 0.5 deg
G1_SD_DEG = 1.0             # was 0.4 deg -- below the measured 1.03 deg/sample noise floor
G1_MIN_FIX_SAMPLES = 20     # was 5 (single-sample rest fixes in the original script)
G2_ENDPOINT_MM = 10.0       # was 5 mm -- below the measured 3-7 mm position repeatability
# G3 (leg length), G4 (first-tick / acceleration), G5 (continuous
# tracking) and G6 (square closure vs. baseline) are UNCHANGED by this
# sprint -- only G1 and G2 sit below the instrument's own noise floor.
G3_LENGTH_TOL_FRAC = 0.005     # +-0.5 %, e.g. 600mm +-3mm (design S10.1)
G4_MAX_ACCEL_FRAC = 1.5        # measured accel <= 1.5 x the `accel` config
G4_MAX_DECEL_FRAC = 2.0        # measured decel <= 2.0 x the `decel` config
G5_PEAK_OVERSHOOT_FRAC = 0.05  # WHEELS_V peak <= cruise * 1.05 (design S10.2 target <= 210 on 200)

# coldboot: "early-ending segment" bar. Every healthy segment across
# Session A's three cold boots (captures/session-a-20260904/) landed
# between 2.41 and 3.37 cm for a 4.0 cm command -- 60 % to 84 %; the two
# that ended early were 0.93 and 1.84 cm (23 % and 46 %). 0.55 sits in
# the gap, below every healthy segment and above the worse of the two
# failures, and is a FRACTION so a different --seg-mm still means
# something. Ticket 010's own bar on the count is zero.
COLDBOOT_SHORT_FRAC = 0.55

# G5's no-motion floor [cm]. A WHEELS_V step at the gate's own default
# (200 mm/s for 1500 ms) travels ~30 cm; the four zero-motion trials of
# 2026-09-05 read 0.011-0.027 cm, which is camera noise. 2 cm is far
# below any real step and far above the noise.
G5_MIN_TRAVEL_CM = 2.0
G5_MAX_RISE_MM_S2 = 600.0      # max frame-to-frame wheel-speed rise, unchanged (design S10.2)
G6_BASELINE_CLOSURE_MM = 10.8  # reports/gopiv-closure-20260901.md, 5-tour mean; unchanged


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
        # Sequencing and line reassembly are tools/link.py's since
        # sprint 034 ticket 006; the background reader thread, which is
        # what makes this carrier different from the others, stays here.
        self.sequencer = linklib.Sequencer()
        self._stop = threading.Event()
        self._buf = linklib.LineBuffer()
        self._th = threading.Thread(target=self._reader, daemon=True)
        self._th.start()
        time.sleep(0.5)

    @property
    def _seq(self):
        return self.sequencer.seq

    @_seq.setter
    def _seq(self, value):
        self.sequencer.seq = value

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
            got = self._buf.feed(c)
            if got:
                now = time.time()
                with self.lock:
                    self.lines.extend((now, s) for s in got)

    def send(self, line):
        try:
            self.sock.sendall((line + '\n').encode())
        except OSError as e:
            print(f'link: send failed ({e}); the carrier is gone')

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
        Retries resend the SAME id (a fresh one would open a gap) --
        `format()` runs ONCE, outside the loop."""
        wire = self.sequencer.format(cmd, force=True)
        wire_id = self.sequencer.seq
        for _ in range(tries):
            t0 = time.time()
            self.send(wire)
            got = self.wait_for(r'^(ack|nack|err)\s+%d\b' % wire_id, t0, wait)
            if got:
                return wire_id, got
        return wire_id, None

    def hello(self):
        got = self.unseq('HELLO', r'^device ')
        self.sequencer.reset()
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


RELAY_HOST, RELAY_PORT = linklib.RELAY_HOST, linklib.RELAY_PORT


def robot_radio(robot):
    """(channel, group) from the robot's radio-robot-lib config -- the
    deploy-time authority for the pair actually baked into the board.

    NEITHER half has a default. `radio_group` used to fall back to 10,
    which is a wrong answer for the whole migrated fleet (groups 43, 60,
    108, 114 -- `.claude/rules/playfield-testing.md`) delivered in
    silence: the relay tunes somewhere the robot is not and the board
    simply never answers. Same defect as the `!CG {channel} 10` sprint
    034 ticket 006 removed from `tools/wire_acceptance.py`; every robot
    config in the fleet sets both keys, so there is nothing to default
    for.
    """
    import json
    path = pathlib.Path('/Volumes/Proj/proj/RobotProjects/radio-robot-lib/config/robots') / f'{robot}.json'
    c = json.loads(path.read_text()).get('connection', {})
    missing = [k for k in ('radio_channel', 'radio_group') if k not in c]
    if missing:
        raise SystemExit(
            f'{path} has no {"/".join(missing)} for {robot!r} -- there is '
            f'no default to fall back to (a guessed group tunes the relay '
            f'at nothing and the robot goes silent). Fill it in, or drive '
            f'this board over --host/--wifi instead.')
    return int(c['radio_channel']), int(c['radio_group'])


class RelayLink(Link):
    """The robot over the torture relay pool: the same line pipe after
    the relay's control-plane setup (`!CG <ch> <grp>`, `!GO`). LOSSY --
    66-83 % per-line delivery measured -- so seqd()'s retries matter and
    telemetry frames will have gaps."""

    def __init__(self, channel, group, host=RELAY_HOST, port=RELAY_PORT):
        super().__init__(host, port)
        time.sleep(1.0)
        banner = next((s for _, s in self.since(0) if 'RADIOBRIDGE' in s), '')
        self.relay = banner.split(':')[3] if banner.count(':') >= 3 else '?'
        print(f'relay: {self.relay} ({banner.strip()[:60]})')
        # The FULL relay setup (sprint 034 ticket 006): the relay
        # PERSISTS its config across resets, so `!MODE RAW250`/`!P 7`
        # are not the no-ops "a fresh board defaults to them" suggests.
        # See tools/link.py's relay_setup_lines().
        for c in linklib.relay_setup_lines(channel, group) + ('!GO',):
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

    def __init__(self, tag, heading_offset_deg=0.0, cam=None):
        cam = cam or CAM
        from aprilcam.mcp import connection as _conn
        self.D = _conn.ConnectionManager().resolve()
        self.tag = tag
        self.cam = cam
        self.off = heading_offset_deg
        self.samples = []          # (t, x, y, heading_deg, speed)
        self._last_ts = None       # daemon timestamp of the last accepted record
        self.lock = threading.Lock()
        self._track = threading.Event()
        self._th = None

    def raw(self):
        try:
            recs = self.D.get_tags(self.cam).tags
        except Exception as e:  # a dropped frame / daemon hiccup is a missed fix, not a crash
            now = time.time()
            if now - getattr(self, '_last_err', 0) > 5:
                print(f'camera {self.cam}: {str(e).splitlines()[-1][:90]}')
                self._last_err = now
            return None
        for rec in recs:
            if rec.tag.number == self.tag:
                return rec
        return None

    def sample(self):
        r = self.raw()
        if r is None:
            return None
        # The daemon keeps reporting the LAST pose of a tag it has just
        # lost; a record whose timestamp has not advanced is that stale
        # pose, not a new observation. Measured 2026-09-04 on gopiv: a
        # 97 deg pivot scored 0 deg because both rest fixes were the same
        # stale record.
        ts = getattr(r, 'timestamp', None)
        if ts is not None and ts == self._last_ts:
            return None
        self._last_ts = ts
        h = wrap(math.degrees(r.yaw_rad) + self.off)
        sp = r.speed or 0.0
        s = (time.time(), r.world.x, r.world.y, h, sp)
        with self.lock:
            self.samples.append(s)
        return s

    def fix(self, n=8, gap=0.05):
        xs = ys = sy = cy = 0.0
        got = 0
        for _ in range(n * 6):
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
                total += wrap(h - prev)
            prev = h
        return total, len(hs)


SPEED_SANE = 600  # [mm/s] a wheel never exceeds ~400; radio-corrupted frames carried 5567 (tigez 2026-09-04)


def speed(f, key):
    """A wheel speed from a telemetry frame, 0 for a corrupted value."""
    try:
        v = int(f.get(key, 0))
    except (TypeError, ValueError):
        return 0
    return v if abs(v) <= SPEED_SANE else 0


def intfield(f, key, default=0):
    """A non-speed integer telemetry field (duty, `now`, ...) -- no
    SPEED_SANE clip, since duty/tick fields have their own ranges."""
    try:
        return int(f.get(key, default))
    except (TypeError, ValueError):
        return default


def frame_now_ms(f):
    """The device's own tick clock [ms] for a telemetry frame (the
    `now` column) -- used for dt between frames instead of the host's
    wall-clock receive time, which carries extra latency/jitter."""
    return intfield(f, 'now', 0)


# ----------------------------------------------------------- the sweep
def check_safe(pose, margin=SAFE_MARGIN):
    x, y = pose[0], pose[1]
    if abs(x) > FIELD_X - margin or abs(y) > FIELD_Y - margin:
        return (f'robot at ({x:.1f}, {y:.1f}) cm is within {margin:.0f} cm of a '
                f'rail (limits +-{FIELD_X}, +-{FIELD_Y}); move it toward the middle')
    return None


def _wait_done(link, tid, timeout_ms, extra_s=5.0):
    """Poll STATUS until `done` matches `tid`; returns the reason, or
    `None` on timeout. Shared completion-wait used by every mode that
    sends a sequenced MOVE_X/pivot and needs to know when it resolved."""
    end = time.time() + timeout_ms / 1000.0 + extra_s
    while time.time() < end:
        st = link.status()
        if st.get('done') == str(tid):
            return st.get('reason')
        time.sleep(0.2)
    return None


def one_turn(link, cam, deg, cruise, timeout_ms, cols, out_frames, turn_idx, settle_s,
             fix_n=8, poll=True):
    """One in-place MOVE_X pivot, camera-scored. `fix_n` is the rest-fix
    sample count (default 8, the sweep mode's historical value); G1
    mode passes `fix_n=G1_MIN_FIX_SAMPLES` (>= 20) per the restated bar
    -- see the module-level bar comments above.

    `poll=False` (`--no-poll`) keeps the wire silent for the duration of
    the move and lets the camera alone decide when it is over. Sprint
    029 measurement: STATUS polling and `TLM FULL` both provoke
    early-terminated pivots on some builds (vevov 2026-09-04,
    reports/turn-cal-029-20260904/, 12/12 clean without them)."""
    a = cam.fix(n=fix_n)
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
    if poll:
        reason = _wait_done(link, tid, timeout_ms)
    else:
        # --no-poll: nothing else on the wire during the move; the camera
        # decides when it is over (settle below)
        reason = None
        time.sleep(0.6)
    cam.settle(timeout=settle_s + 8.0)
    time.sleep(settle_s)
    t_end = time.time()
    cam.stop_tracking()
    b = cam.fix(n=fix_n)
    if b is None:
        return None, 'no camera fix after the turn'
    unwrapped, n = cam.unwrapped_turn(t_start, t_end)
    # Snap the rest-to-rest difference onto the unwrapped total: rest fixes
    # are precise, the tracker decides which lap.
    rest_diff = wrap(b[2] - a[2])
    # Snap to the COMMANDED lap, not the tracker's: a pivot never misses
    # by 180 deg, but the tracker does drop samples (stale camera
    # records, lights) and then under-counts a 180 into the wrong lap --
    # gopiv 2026-09-04 scored -180 as +169 (err +349) that way. The
    # tracker still reports, and complains when it clearly disagrees.
    laps = round((deg - rest_diff) / 360.0)
    camera_deg = rest_diff + 360.0 * laps
    if n >= 8 and abs(unwrapped - camera_deg) > 90:
        print(f'WARNING: tracker unwrapped {unwrapped:+.1f} vs rest-to-rest {camera_deg:+.1f} '
              f'({n} samples) -- trusting the rest fixes')
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
    vl = [abs(speed(f, 'vl')) for f in frames]
    vr = [abs(speed(f, 'vr')) for f in frames]
    moving = [f for f in frames if abs(speed(f, 'vl')) > 5 or abs(speed(f, 'vr')) > 5]
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


def _enable_tlm_full(link, no_tlm=False):
    """Turn on `TLM FULL` and return its column list from the `thdr`
    line -- shared by every mode that needs per-frame wheel telemetry
    (the pivot sweep, G1, G3, G5). A lossy carrier drops the header
    occasionally; retried twice before giving up and continuing on the
    camera alone."""
    cols = None
    for _attempt in range(0 if no_tlm else 2):
        t0 = time.time() - 0.5
        link.seqd('TLM FULL', wait=2.0)
        for _ in range(60):          # a lossy carrier drops headers; they repeat every ~1 s
            for _, s in link.since(t0, 'thdr '):
                cols = s.split()[1:]
            if cols:
                break
            time.sleep(0.1)
        if cols:
            break
    if not cols:
        if no_tlm:
            print('telemetry OFF (--no-tlm): camera-only scoring, no wheel speeds or encoder heading')
        else:
            print('WARNING: no thdr after TLM FULL -- continuing on camera alone (no wheel speeds)')
        cols = []
    print(f'telemetry columns: {cols}')
    return cols


def wire_get(link, field, default=None, tries=3):
    """`GET <field>` as a float, or `default` if the robot did not
    answer (an unknown field on older firmware, a lossy carrier).

    The reply window opens at the moment of the SEND and the LAST match
    in it wins. Both halves matter: the previous version looked BACK
    2.5 s and returned the FIRST match, so a second `GET` of the same
    field inside that window re-reported the earlier answer -- MEASURED
    tovez 2026-09-05, captures/session-b-20260905/notes.md, where five
    different writes all read back as one unchanging value while the
    same five round-tripped exactly with the window defeated. That made
    the `(live)` banner -- the only record of what the robot was
    configured to when a capture was taken -- capable of lying
    (clasi/issues/wire-get-returns-a-stale-reading.md).

    Asks up to `tries` times, because a fresh WiFi session drops the odd
    first reply (MEASURED vevov 2026-09-04,
    reports/turn-cal-029-20260904/ -- the post-flash read came back with
    firmware defaults, which reads as a bake that did not take)."""
    for _ in range(tries):
        t0 = time.time()
        link.seqd(f'GET {field}', wait=2.0)
        val = None
        for _, s in link.since(t0, f'get {field} '):
            try:
                val = float(s.split()[2])
            except (IndexError, ValueError):
                continue
        if val is not None:
            return val
    return default


def run_sweep(link, cam, a, out):
    out.mkdir(parents=True, exist_ok=True)
    cols = _enable_tlm_full(link, a.no_tlm)

    # interleaved, sign-alternating schedule
    plan = []
    for rep in range(a.reps):
        for ang in a.angles:
            sign = 1 if rep % 2 == 0 else -1
            plan.append(sign * ang)
            plan.append(-sign * ang)
    print(f'{len(plan)} pivots: {plan}')

    rows, frames_out = [], []
    silent = 0   # consecutive moves the robot never acked
    print(f"{'#':>3} {'cmd':>6} {'camera':>8} {'err':>7} {'enc':>8} {'encerr':>7} {'drift':>6} {'peakL':>6} {'peakR':>6} {'dur':>5}  reason")
    for i, deg in enumerate(plan, 1):
        lights_on()
        pose = cam.fix()
        bad = check_safe(pose, a.margin) if pose else 'no camera fix'
        if bad:
            print(f'STOP: {bad}')
            break
        row, err = one_turn(link, cam, deg, a.cruise, a.timeout_ms, cols, frames_out, i, a.settle, poll=not a.no_poll)
        if err:
            print(f'{i:3d} {deg:6d}  -- {err}')
            if 'not accepted' in err:
                silent += 1
                if silent >= 2 and a.radio:
                    # a pool relay that passes nothing outbound (tigez
                    # 2026-09-04, three sessions): drop it, take another,
                    # re-apply the live SETs, keep going
                    print('  link silent twice -- reconnecting through the relay pool')
                    link.close()
                    link, where = open_link(a)
                    print(f'  link: {where}; robot: {link.hello()}')
                    for kv in a.set:
                        k, v = kv.split('=', 1)
                        tid, ack = link.seqd(f'SET {k} {v}', wait=2.0)
                        print(f'  SET {k} {v} -> {ack}')
                    silent = 0
            continue
        silent = 0
        rows.append(row)
        print(f"{i:3d} {deg:6d} {row['camera_deg']:8.1f} {row['error_deg']:7.1f} "
              f"{str(row['encoder_deg']):>8} {str(row['encoder_error_deg']):>7} {row['drift_cm']:6.1f} "
              f"{str(row['peak_vl']):>6} {str(row['peak_vr']):>6} {row['duration_s']:5.1f}  {row['reason']}")
        _write_csv(out / 'turns.csv', rows)
        _write_csv(out / 'frames.csv', frames_out)
        time.sleep(a.pause)
    if not a.no_tlm:
        link.seqd('TLM OFF', wait=1.5)
    with cam.lock:
        cam_rows = [{'t': s[0], 'x': s[1], 'y': s[2], 'heading': s[3], 'speed': s[4]} for s in cam.samples]
    _write_csv(out / 'camera.csv', cam_rows)
    summary = analyze(rows, a)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    a.link = link   # may have been reconnected mid-sweep
    return rows


# --------------------------------------------- G1-G6 gate modes (drive)
#
# One drive function per gate below (plus one_leg/one_arc, the
# straight-leg/arc analogues of one_turn() above), folded from sprint
# 029's standalone captures/bench-acceptance-029-20260904d/g*.py
# scripts (SUC-007). Each does its own mandatory pre-flight path check
# (.claude/rules/playfield-testing.md) from a measured start pose before
# arming any commanded motion, and fails loudly (SystemExit or a
# printed STOP + non-zero return) on a missing precondition rather than
# silently doing nothing -- these are run by a person under session
# pressure (tickets 011/012/016), not by CI.

def one_leg(link, cam, dist_mm, cruise, timeout_ms, cols, out_frames, leg_idx, settle_s):
    """One straight MOVE_X leg (G3 length / G4 first-tick+accel),
    mirroring one_turn()'s rest-fix/TLM/STATUS-poll shape but for a
    translating move. Folded from sprint 029's g3_run.py."""
    a = cam.fix()
    if a is None:
        return None, 'no camera fix before the leg'
    cam.start_tracking()
    t_start = time.time()
    tid, ack = link.seqd(f'MOVE_X {dist_mm} 0 {cruise} {timeout_ms}', wait=3.0)
    if not ack or not ack.startswith('ack'):
        cam.stop_tracking()
        return None, f'MOVE_X not accepted: {ack}'
    reason = _wait_done(link, tid, timeout_ms)
    cam.settle(timeout=settle_s + 8.0)
    time.sleep(settle_s)
    cam.stop_tracking()
    b = cam.fix()
    if b is None:
        return None, 'no camera fix after the leg'
    dx, dy = b[0] - a[0], b[1] - a[1]
    cam_len = math.hypot(dx, dy) * 10.0        # [mm]
    brg = math.degrees(math.atan2(dy, dx))
    want = a[2] if dist_mm > 0 else a[2] + 180
    lateral = cam_len * math.sin(math.radians(wrap(brg - want)))
    dh = wrap(b[2] - a[2])
    frames = []
    for t, s in link.since(t_start - 0.05, 't '):
        parts = s.split()[1:]
        if cols and len(parts) == len(cols):
            f = dict(zip(cols, parts)); f['t'] = t
            frames.append(f)
    m = leg_metrics(frames)
    for f in frames:
        out_frames.append({'leg': leg_idx, 'commanded_mm': dist_mm, 't_rel': round(f['t'] - t_start, 3),
                           **{k: f.get(k, '') for k in cols}})
    row = {
        'leg': leg_idx, 'commanded_mm': dist_mm, 'cruise': cruise, 'id': tid, 'reason': reason,
        'cam_len_mm': round(cam_len, 1), 'len_err_mm': round(cam_len - abs(dist_mm), 1),
        'lateral_mm': round(lateral, 1), 'dheading_deg': round(dh, 2),
        'x0': round(a[0], 2), 'y0': round(a[1], 2), 'x1': round(b[0], 2), 'y1': round(b[1], 2),
        'peak_v': m['peak_v'], 'first_moving_v': m['first_moving_v'],
        'max_accel': m['max_accel'], 'min_accel': m['min_accel'], 'tail_monotone': m['tail_monotone'],
        'frames': len(frames),
    }
    return row, None


def one_arc(link, cam, dist_mm, theta_rad, cruise, timeout_ms, cols, out_frames, arc_idx, settle_s):
    """One MOVE_X arc (G2 endpoint), scored in the START pose's own
    body frame against arc_expected_endpoint_mm(). Folded from sprint
    029's g2_run.py."""
    a = cam.fix()
    if a is None:
        return None, 'no camera fix before the arc'
    cam.start_tracking()
    t_start = time.time()
    tid, ack = link.seqd(f'MOVE_X {dist_mm} {int(round(theta_rad * 1000))} {cruise} {timeout_ms}', wait=3.0)
    if not ack or not ack.startswith('ack'):
        cam.stop_tracking()
        return None, f'MOVE_X not accepted: {ack}'
    reason = _wait_done(link, tid, timeout_ms)
    cam.settle(timeout=settle_s + 8.0)
    time.sleep(settle_s)
    cam.stop_tracking()
    b = cam.fix()
    if b is None:
        return None, 'no camera fix after the arc'
    h = math.radians(a[2])
    dx, dy = (b[0] - a[0]) * 10.0, (b[1] - a[1]) * 10.0   # [mm], world
    bx = dx * math.cos(h) + dy * math.sin(h)
    by = -dx * math.sin(h) + dy * math.cos(h)
    ex, ey = arc_expected_endpoint_mm(dist_mm, theta_rad)
    err = math.hypot(bx - ex, by - ey)
    dh = wrap(b[2] - a[2])
    frames = []
    for t, s in link.since(t_start - 0.05, 't '):
        parts = s.split()[1:]
        if cols and len(parts) == len(cols):
            f = dict(zip(cols, parts)); f['t'] = t
            frames.append(f)
    peak = max((max(abs(speed(f, 'vl')), abs(speed(f, 'vr'))) for f in frames), default=None)
    for f in frames:
        out_frames.append({'arc': arc_idx, 'commanded_mm': dist_mm, 'commanded_rad': theta_rad,
                           't_rel': round(f['t'] - t_start, 3), **{k: f.get(k, '') for k in cols}})
    row = {
        'arc': arc_idx, 'd_mm': dist_mm, 'theta_rad': theta_rad, 'id': tid, 'reason': reason,
        'endpoint_err_mm': round(err, 1), 'body_end_mm': (round(bx, 1), round(by, 1)),
        'expected_mm': (round(ex, 1), round(ey, 1)), 'dheading_deg': round(dh, 2),
        'dheading_err_deg': round(dh - math.degrees(theta_rad), 2), 'peak_v': peak, 'frames': len(frames),
    }
    return row, None


def run_g1(link, cam, a, out):
    """G1: rest-heading pivot accuracy, RESTATED bar (sprint 031 ticket
    007) -- mean|err| <= G1_MEAN_ABS_ERR_DEG, sd <= G1_SD_DEG, each rest
    fix averaged over >= G1_MIN_FIX_SAMPLES samples. Folds sprint 029's
    g1_run.py: alternating +-90 deg pivots plus the camera at-rest
    noise-floor print that the restated bar is built on."""
    out.mkdir(parents=True, exist_ok=True)
    fix_n = max(a.n_fix, G1_MIN_FIX_SAMPLES)
    noise = camera_noise_floor(cam, n=fix_n)
    print(f"camera heading at rest: n={noise['n']} sd={noise['sd']} deg, peak-to-peak {noise['ptp']} deg "
          f"-- this is why G1 is restated (mean|err|<={G1_MEAN_ABS_ERR_DEG}, sd<={G1_SD_DEG} deg)")
    cols = _enable_tlm_full(link, a.no_tlm)
    n_pivots = a.reps * 2   # alternating +90/-90 pairs (sprint 029's g1_run.py: 6 pairs = 12)
    print(f'{n_pivots} alternating +-90 deg pivots, {fix_n}-sample rest fixes')
    rows, frames_out, sign = [], [], 1
    for i in range(n_pivots):
        lights_on()
        pose = cam.fix()
        bad = check_safe(pose, a.margin) if pose else 'no camera fix'
        if bad:
            print(f'STOP: {bad}')
            break
        row, err = one_turn(link, cam, sign * 90, a.cruise, a.timeout_ms, cols, frames_out, i, a.settle, fix_n=fix_n)
        if err:
            print(f'{i:3d}  -- {err}')
            sign = -sign
            continue
        rows.append(row)
        print(f"{i:3d} cmd {row['commanded']:+4d} cam {row['camera_deg']:+7.2f} err {row['error_deg']:+6.2f} "
              f"peak {row['peak_vl']}/{row['peak_vr']} done {row['reason']}")
        _write_csv(out / 'g1-turns.csv', rows)
        sign = -sign
        time.sleep(a.pause)
    link.seqd('TLM OFF', wait=1.5)
    errs = [r['error_deg'] for r in rows]
    score = g1_score(errs)
    print(f"G1: mean|err| {score['mean_abs_err']} deg, sd {score['sd']} deg, n={score['n']} -- "
          f"{'PASS' if score['passed'] else 'FAIL'} (bar: mean|err|<={G1_MEAN_ABS_ERR_DEG}, sd<={G1_SD_DEG})")
    summary = {'gate': 'G1', 'bar': {'mean_abs_err_deg': G1_MEAN_ABS_ERR_DEG, 'sd_deg': G1_SD_DEG,
               'min_fix_samples': G1_MIN_FIX_SAMPLES}, 'camera_noise': noise, 'score': score}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
    return score['passed']


def run_g2(link, cam, a, out):
    """G2: arc endpoint accuracy, RESTATED bar (sprint 031 ticket 007)
    -- mean endpoint error <= G2_ENDPOINT_MM. Folds sprint 029's
    g2_run.py: `a.arcs` alternating +-`a.arc_deg` deg arcs of chord
    `a.arc_mm`."""
    out.mkdir(parents=True, exist_ok=True)
    cols = _enable_tlm_full(link, a.no_tlm)
    theta = math.radians(a.arc_deg)
    print(f'{a.arcs} alternating +-{a.arc_deg} deg arcs, chord {a.arc_mm} mm')
    rows, frames_out = [], []
    for i in range(a.arcs):
        lights_on()
        pose = cam.fix()
        d = a.arc_mm if i % 2 == 0 else -a.arc_mm
        th = theta if i % 2 == 0 else -theta
        if pose is None:
            print('STOP: no camera fix'); break
        offenders = fieldlib.check_path([(pose[0], pose[1])] + arc_path_points(pose, d, th))
        if offenders:
            print(f'STOP: projected arc path leaves the margin near {offenders[0]}'); break
        row, err = one_arc(link, cam, d, th, a.cruise, a.timeout_ms, cols, frames_out, i, a.settle)
        if err:
            print(f'{i:3d}  -- {err}')
            continue
        rows.append(row)
        print(f"{i:3d} d={row['d_mm']:+5d} th={row['theta_rad']:+.3f} endpoint_err {row['endpoint_err_mm']:6.1f} mm "
              f"dh_err {row['dheading_err_deg']:+.2f} deg reason={row['reason']}")
        _write_csv(out / 'g2-arcs.csv', rows)
        time.sleep(a.pause)
    link.seqd('TLM OFF', wait=1.5)
    errs = [r['endpoint_err_mm'] for r in rows]
    score = g2_score(errs)
    print(f"G2: endpoint err mean {score['mean']} mm, max {score['max']} mm, {score['n_within']}/{score['n']} within "
          f"{G2_ENDPOINT_MM} mm -- {'PASS' if score['passed'] else 'FAIL'} (bar: mean<={G2_ENDPOINT_MM} mm)")
    summary = {'gate': 'G2', 'bar': {'endpoint_mm': G2_ENDPOINT_MM}, 'score': score}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
    return score['passed']


def run_g3(link, cam, a, out):
    """G3 (leg length) + G4 (first-tick, acceleration), UNCHANGED bars
    (sprint 031 restates only G1/G2). Folds sprint 029's g3_run.py:
    `a.legs` alternating +-`a.leg_mm` mm straight legs."""
    out.mkdir(parents=True, exist_ok=True)
    accel = wire_get(link, 'accel', 400.0)
    v_floor = wire_get(link, 'v_floor', 70.0)
    cols = _enable_tlm_full(link, a.no_tlm)
    print(f'{a.legs} alternating +-{a.leg_mm} mm legs at cruise {a.cruise} mm/s '
          f'(accel={accel}, v_floor={v_floor} live)')
    rows, frames_out, sign = [], [], 1
    for i in range(a.legs):
        lights_on()
        pose = cam.fix()
        d = sign * a.leg_mm
        if pose is None:
            print('STOP: no camera fix'); break
        h = math.radians(pose[2])
        end = (pose[0] + (d / 10.0) * math.cos(h), pose[1] + (d / 10.0) * math.sin(h))
        offenders = fieldlib.check_path([(pose[0], pose[1]), end])
        if offenders:
            print(f'STOP: projected leg path leaves the margin near {offenders[0]}'); break
        row, err = one_leg(link, cam, d, a.cruise, a.timeout_ms, cols, frames_out, i, a.settle)
        if err:
            print(f'{i:3d}  -- {err}')
            sign = -sign
            continue
        rows.append(row)
        print(f"{i:3d} cmd {row['commanded_mm']:+5d} cam {row['cam_len_mm']:7.1f} mm (err {row['len_err_mm']:+.1f}) "
              f"peak {row['peak_v']} first {row['first_moving_v']} dh {row['dheading_deg']:+.2f} reason={row['reason']}")
        _write_csv(out / 'g3-legs.csv', rows)
        sign = -sign
        time.sleep(a.pause)
    link.seqd('TLM OFF', wait=1.5)
    if not rows:
        print('G3/G4: no legs completed -- FAIL')
        return False
    errs = [r['len_err_mm'] for r in rows]
    mean_err = sum(errs) / len(errs)
    len_tol = max(3.0, abs(a.leg_mm) * G3_LENGTH_TOL_FRAC)
    g3_pass = max(abs(e) for e in errs) <= len_tol
    peak_v_max = max((r['peak_v'] for r in rows if r['peak_v'] is not None), default=None)
    peak_bar = a.cruise * (1.0 + G5_PEAK_OVERSHOOT_FRAC)
    first_vs = [r['first_moving_v'] for r in rows if r['first_moving_v'] is not None]
    accels = [r['max_accel'] for r in rows if r['max_accel'] is not None]
    decels = [-r['min_accel'] for r in rows if r['min_accel'] is not None]
    g4_first_pass = not first_vs or max(first_vs) <= v_floor
    g4_accel_pass = not accels or max(accels) <= G4_MAX_ACCEL_FRAC * accel
    g4_decel_pass = not decels or max(decels) <= G4_MAX_DECEL_FRAC * accel
    g3_peak_pass = peak_v_max is None or peak_v_max <= peak_bar
    print(f"G3: length err mean {mean_err:+.1f} mm (bar +-{len_tol:.1f}) -- {'PASS' if g3_pass else 'FAIL'}; "
          f"peak v max {peak_v_max} mm/s (bar <= {peak_bar:.0f}) -- {'PASS' if g3_peak_pass else 'FAIL'}")
    print(f"G4: first-tick max {max(first_vs) if first_vs else None} mm/s (bar <= v_floor {v_floor}) -- "
          f"{'PASS' if g4_first_pass else 'FAIL'}; max accel {max(accels) if accels else None} "
          f"(bar <= {G4_MAX_ACCEL_FRAC}x accel={accel:.0f}) -- {'PASS' if g4_accel_pass else 'FAIL'}; "
          f"max decel {max(decels) if decels else None} (bar <= {G4_MAX_DECEL_FRAC}x accel) -- "
          f"{'PASS' if g4_decel_pass else 'FAIL'}")
    summary = {'gate': 'G3/G4', 'accel_config': accel, 'v_floor_config': v_floor, 'rows': rows,
               'g3_pass': g3_pass, 'g3_peak_pass': g3_peak_pass, 'g4_first_pass': g4_first_pass,
               'g4_accel_pass': g4_accel_pass, 'g4_decel_pass': g4_decel_pass}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
    return g3_pass and g3_peak_pass and g4_first_pass and g4_accel_pass and g4_decel_pass


def run_g5(link, cam, a, out):
    """G5: continuous WHEELS_V step-response tracking, UNCHANGED bars
    (sprint 031 restates only G1/G2): peak <= cruise*(1+
    G5_PEAK_OVERSHOOT_FRAC), max frame-to-frame rise <=
    G5_MAX_RISE_MM_S2. Folds sprint 029's lag_measure.py: alternating
    `WHEELS_V +-v +-v <hold>` steps from rest (net camera travel stays
    near zero), per-wheel lag fit plus the shared leg_metrics() peak/
    accel check (same telemetry shape as a MOVE_X leg)."""
    out.mkdir(parents=True, exist_ok=True)
    accel = wire_get(link, 'accel', 400.0)
    pose = cam.fix()
    if pose is None:
        raise SystemExit('no camera fix -- cannot safety-check WHEELS_V travel before driving')
    reach_cm = (a.cruise_g5 / 10.0) * (a.hold_ms / 1000.0) * 1.15   # generous bound, both directions
    h = math.radians(pose[2])
    for s in (1, -1):
        end = (pose[0] + s * reach_cm * math.cos(h), pose[1] + s * reach_cm * math.sin(h))
        offenders = fieldlib.check_path([(pose[0], pose[1]), end])
        if offenders:
            raise SystemExit(f'projected WHEELS_V travel leaves the margin near {offenders[0]}; reposition first')
    cols = _enable_tlm_full(link, a.no_tlm)
    trials = []
    for k, sign in enumerate(([1, -1] * a.reps)):
        pre = cam.fix()
        t0 = time.time() - 0.3
        # WHEELS_V is SEQUENCED (.claude/rules/playfield-testing.md's own
        # table). Sent unsequenced it parses as `#0`, which is
        # unconditionally below the robot's `expectedNext_`, so the v6
        # handler classifies it as a stale retransmit and does not
        # execute it -- silently. This mode used `link.send()` and so
        # never moved the robot at all; MEASURED tovez 2026-09-05,
        # captures/session-b-20260905/g5-today/summary.json: four trials,
        # every one peak_v 0, max_accel null, travel 0.011-0.027 cm, and
        # byte-identical lag fits -- scored `passed: true`.
        link.seqd(f'WHEELS_V {sign * a.cruise_g5} {sign * a.cruise_g5} '
                  f'{a.hold_ms}', wait=2.0)
        time.sleep(a.hold_ms / 1000.0 + 0.6)
        frames = []
        for t, s2 in link.since(t0, 't '):
            parts = s2.split()[1:]
            if cols and len(parts) == len(cols):
                f = dict(zip(cols, parts)); f['t'] = t
                frames.append(f)
        post = cam.fix()
        idx = next((i for i, f in enumerate(frames) if intfield(f, 'dutl') or intfield(f, 'dutr')), None)
        onset = frames[max(0, (idx or 1) - 1):]
        fit_l = fit_wheel_lag(onset, sign, accel=accel, vcmd=a.cruise_g5, key='vl')
        fit_r = fit_wheel_lag(onset, sign, accel=accel, vcmd=a.cruise_g5, key='vr')
        m = leg_metrics(frames)
        trav = math.hypot(post[0] - pre[0], post[1] - pre[1]) if pre and post else None
        trials.append({'k': k, 'sign': sign, 'fit_vl': fit_l, 'fit_vr': fit_r,
                       'peak_v': m['peak_v'], 'max_accel': m['max_accel'], 'travel_cm': trav})
        print(f"trial {k:2d} sign {sign:+d}: lag vl={fit_l} vr={fit_r} peak={m['peak_v']} "
              f"max_accel={m['max_accel']} travel={trav and round(trav, 2)} cm")
        time.sleep(a.pause)
    link.seqd('TLM OFF', wait=1.5)
    peaks = [t['peak_v'] for t in trials if t['peak_v'] is not None]
    rises = [t['max_accel'] for t in trials if t['max_accel'] is not None]
    peak_bar = a.cruise_g5 * (1.0 + G5_PEAK_OVERSHOOT_FRAC)
    # A robot that never moved trivially clears "peak <= bar" and
    # reports no acceleration data at all to fail the rise bar with --
    # so the ORIGINAL form of this gate scored `passed: true` on four
    # trials of zero motion. `.claude/rules/playfield-testing.md` is
    # explicit that odometry cannot detect its own failure to move and
    # only an external instrument can; the camera travel per trial is
    # that instrument, and it is already recorded. Fail closed on it.
    moved = [t['travel_cm'] for t in trials if t['travel_cm'] is not None]
    motion_pass = bool(moved) and max(moved) >= G5_MIN_TRAVEL_CM
    peak_pass = bool(peaks) and max(peaks) > 0 and max(peaks) <= peak_bar
    rise_pass = bool(rises) and max(rises) <= G5_MAX_RISE_MM_S2
    if not motion_pass:
        print(f"G5: NO MOTION -- max camera travel "
              f"{max(moved) if moved else None} cm over {len(trials)} trials, "
              f"below the {G5_MIN_TRAVEL_CM} cm floor. The robot did not "
              f"move; every bar below is vacuous. Check that WHEELS_V "
              f"carried a sequence id, that the e-stop is clear, and that "
              f"the brick has power (playfield-testing.md).")
    print(f"G5: peak {max(peaks) if peaks else None} mm/s (bar <= {peak_bar:.0f}) -- "
          f"{'PASS' if peak_pass else 'FAIL'}; max rise {max(rises) if rises else None} mm/s^2 "
          f"(bar <= {G5_MAX_RISE_MM_S2}) -- {'PASS' if rise_pass else 'FAIL'}")
    passed = motion_pass and peak_pass and rise_pass
    summary = {'gate': 'G5', 'cruise_mm_s': a.cruise_g5, 'accel_config': accel, 'bar_peak_mm_s': peak_bar,
               'bar_rise_mm_s2': G5_MAX_RISE_MM_S2, 'trials': trials,
               'min_travel_cm_bar': G5_MIN_TRAVEL_CM, 'motion_pass': motion_pass,
               'peak_pass': peak_pass, 'rise_pass': rise_pass, 'passed': passed}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
    return passed


def run_g6(link, cam, a, out):
    """G6: square-tour closure vs. baseline, UNCHANGED bar (sprint 031
    restates only G1/G2): closure <= G6_BASELINE_CLOSURE_MM. Folds
    sprint 029's g6_run.py/g6_run_500.py into one mode parameterized by
    `--side-mm` (200 for the south-corridor run, 500 for this sprint's
    own square) and `--laps`."""
    out.mkdir(parents=True, exist_ok=True)
    side_cm = a.side_mm / 10.0
    pose = cam.fix()
    if pose is None:
        raise SystemExit('no camera fix -- cannot plan the square')
    x, y, heading = pose[0], pose[1], math.radians(pose[2])
    corners = [(x, y)]
    for _ in range(4):
        x += side_cm * math.cos(heading); y += side_cm * math.sin(heading)
        corners.append((x, y)); heading += math.pi / 2
    offenders = fieldlib.check_path(corners)
    if offenders:
        raise SystemExit(f'projected {a.side_mm} mm square leaves the margin near {offenders[0]}; reposition first')
    print(f'{a.laps} laps of a {a.side_mm} mm square, left turns, from ({pose[0]:.1f}, {pose[1]:.1f})')
    laps = []
    p0 = cam.fix()
    for lap in range(a.laps):
        ok = True
        for i in range(4):
            tid, ack = link.seqd(f'MOVE_X {a.side_mm} 0 {a.cruise} {a.timeout_ms}', wait=3.0)
            if not ack or not ack.startswith('ack'):
                ok = False; print(f'leg {i} not accepted: {ack}'); break
            _wait_done(link, tid, a.timeout_ms)
            time.sleep(0.4)
            tid, ack = link.seqd('MOVE_X 0 1571 100 5000', wait=3.0)
            if not ack or not ack.startswith('ack'):
                ok = False; print(f'pivot {i} not accepted: {ack}'); break
            _wait_done(link, tid, 5000)
            time.sleep(0.4)
        p1 = cam.fix()
        closure_mm = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 10.0 if p1 and p0 else None
        dh = wrap(p1[2] - p0[2]) if p1 and p0 else None
        laps.append({'lap': lap, 'closure_mm': closure_mm, 'heading_residual_deg': dh, 'ok': ok})
        print(f"lap {lap}: closure {closure_mm and round(closure_mm)} mm, heading residual "
              f"{dh and round(dh, 1)} deg, ok={ok}")
        if not ok:
            break
        p0 = cam.fix()
    closures = [l['closure_mm'] for l in laps if l['closure_mm'] is not None]
    passed = bool(closures) and all(square_closure_ok(c) for c in closures)
    print(f"G6: closures {[round(c) for c in closures]} mm (bar <= {G6_BASELINE_CLOSURE_MM} mm) -- "
          f"{'PASS' if passed else 'FAIL'}")
    summary = {'gate': 'G6', 'side_mm': a.side_mm, 'bar_mm': G6_BASELINE_CLOSURE_MM, 'laps': laps, 'passed': passed}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
    return passed


# --- coldboot: the cold-boot segment protocol (sprint 031 tickets 009/010) --
#
# Ten short `MOVE_X` segments from a cold boot, camera-fixed at every
# boundary, with STATUS polled at 8 Hz from BEFORE the first command.
# Folds sprint 031 ticket 001's Session A harness in as a mode, with two
# corrections that capture forced:
#
# 1. **The poller starts before the pre-pivot, not after.** Session A's
#    harness started its 8 Hz thread only once the repositioning pivot
#    was done, so each run's log opened at whatever `i2cf` the pivot had
#    already accrued -- boot 3's first sample reads 25, boot 4's reads
#    22. Reading those logs as "0 -> N" made boot 4 look like a 6x
#    regression against boot 1 (which had no pre-pivot at all and so
#    genuinely started at 0); per control cycle the four runs are 26.8 /
#    16.3 / 26.2 / 52.0 faults per 1000 `cyc`. Whatever the truth about
#    the post-030 build, it has to be measured on the same window.
# 2. **`i2cf` and `cyc` are recorded at every segment boundary**, so a
#    rate can be computed per segment instead of only across a run.
#
# `i2cf` is NOT a bus-wide I2C counter and the OTOS is not in it:
# `DifferentialDrive::step()` increments `i2cFaultCount_` on a cycle
# whose WHEEL-ENCODER sample timestamp failed to advance
# (`src/core/diffdrive.cpp`), i.e. a failed Nezha collect. Nor does a
# wire-issued `MOVE_X` read the OTOS at all: OTOS sampling lives in
# `test/test.ts`'s `tickToCompletion()` (the on-robot RUN-handler loop),
# while wire motion is ticked by the protocol fiber through
# `tickDrive()` (`src/shims.cpp`), which issues no OTOS transaction.
# So `otos=1` vs `otos=0` across runs does not change the bus traffic
# this protocol measures, and runs on either can be compared directly.


def _status_poller(link, stop, rows, hz=8.0):
    """Poll STATUS at `hz` into `rows` as (t, line). STATUS is
    unsequenced (`.claude/rules/playfield-testing.md`), so hammering it
    cannot disturb the sequence a move is running under."""
    period = 1.0 / hz
    while not stop.is_set():
        t0 = time.time()
        link.send('STATUS')
        dt = period - (time.time() - t0)
        if dt > 0:
            time.sleep(dt)


def _status_now(link, timeout=1.5):
    """The most recent `status ...` line as a dict, or {}."""
    t0 = time.time()
    link.send('STATUS')
    got = link.wait_for(r'^status ', t0, timeout)
    return dict(kv.split('=', 1) for kv in got.split()[1:]) if got else {}


def _best_heading(x, y, need_cm):
    """Heading [deg] with the most straight-line room inside the safe
    box, and that room. Same scan as Session A's harness."""
    best, bestd = 0.0, -1.0
    for h in range(0, 360, 5):
        d = 0.0
        while d < max(90.0, need_cm + 10.0):
            nx = x + (d + 2.0) * math.cos(math.radians(h))
            ny = y + (d + 2.0) * math.sin(math.radians(h))
            if fieldlib.check_path([(x, y), (nx, ny)]):
                break
            d += 2.0
        if d > bestd:
            best, bestd = float(h), d
    return best, bestd


def _pivot_to(link, cam, target_deg, a, tol=4.0, tries=4):
    """Camera-closed-loop pivot in place. MOVE_X takes millIRADIANS."""
    for _ in range(tries):
        p = cam.fix(n=3)
        if p is None:
            return None
        err = wrap(target_deg - p[2])
        if abs(err) <= tol:
            return p
        mrad = int(round(math.radians(err) * 1000))
        link.seqd(f'MOVE_X 0 {mrad} 150 6000', wait=2.0)
        time.sleep(2.2)
        cam.settle(timeout=4.0)
    return cam.fix(n=3)


def run_coldboot(link, cam, a, out):
    """Cold-boot segment protocol: `a.segments` short `MOVE_X` legs with
    STATUS at 8 Hz from before the first command.

    Ticket 009's controlled repeat (does the post-sprint-030 build
    really accrue `i2cf` faster, on a charged battery?) and ticket 010's
    three-cold-boot early-end re-verification are the SAME run; which
    one a given run answers is a matter of how many boots are done, not
    of what the program does. `--boot-label` names the sub-directory so
    several boots land side by side under one `--out`."""
    out = out / a.boot_label
    out.mkdir(parents=True, exist_ok=True)

    st0 = _status_now(link)
    cold = st0.get('cyc') == '0'
    print(f"pre-move STATUS: {st0}")
    if not cold:
        print(f"  !! NOT a fresh boot (cyc={st0.get('cyc')}) -- recorded and flagged")

    poll, stop = [], threading.Event()
    with link.lock:
        poll_from = time.time()
    th = threading.Thread(target=_status_poller, args=(link, stop, poll),
                          daemon=True)
    th.start()                      # BEFORE the pre-pivot -- see above

    try:
        p0 = cam.fix()
        if p0 is None:
            print('ABORT: no camera fix'); return False
        print(f'start pose ({p0[0]:.2f}, {p0[1]:.2f}) h={p0[2]:.2f}')
        need = (a.seg_mm / 10.0) * a.segments
        h, room = _best_heading(p0[0], p0[1], need)
        print(f'best heading {h:.0f} deg with {room:.0f} cm of room (need {need:.0f})')
        pre_pivot = None
        if room < need:
            print(f'ABORT: nowhere from here has {need:.0f} cm of straight room')
            return False
        if abs(wrap(h - p0[2])) > 6.0:
            print(f'pre-pivot {p0[2]:.1f} -> {h:.0f} deg (a recorded step, inside the poll window)')
            pre_pivot = dict(from_deg=p0[2], to_deg=h,
                             i2cf_before=intfield(st0, 'i2cf'),
                             cyc_before=intfield(st0, 'cyc'))
            pp = _pivot_to(link, cam, h, a)
            st = _status_now(link)
            pre_pivot.update(achieved_deg=pp[2] if pp else None,
                             i2cf_after=intfield(st, 'i2cf'),
                             cyc_after=intfield(st, 'cyc'))
            print(f"  after pivot: h={pp[2]:.2f} i2cf {pre_pivot['i2cf_before']}"
                  f" -> {pre_pivot['i2cf_after']} over "
                  f"{pre_pivot['cyc_after'] - pre_pivot['cyc_before']} cyc"
                  if pp else '  after pivot: no camera fix')

        rows = []
        for i in range(1, a.segments + 1):
            lights_on()
            p = cam.fix(n=3)
            if p is None:
                print(f'seg {i}: ABORT -- lost camera fix'); break
            d = a.seg_mm / 10.0
            end = (p[0] + d * math.cos(math.radians(p[2])),
                   p[1] + d * math.sin(math.radians(p[2])))
            offenders = fieldlib.check_path([(p[0], p[1]), end])
            if offenders:
                print(f'seg {i}: ABORT -- path check failed near {offenders[0]}')
                break
            before = _status_now(link)
            tid, _ack = link.seqd(
                f'MOVE_X {a.seg_mm} 0 {a.cruise_seg} {a.timeout_ms}', wait=2.0)
            time.sleep(a.seg_settle)
            cam.settle(timeout=4.0)
            after = _status_now(link)
            p2 = cam.fix(n=3)
            moved = (math.hypot(p2[0] - p[0], p2[1] - p[1])
                     if p2 else float('nan'))
            row = dict(seg=i, id=tid, commanded_cm=d, moved_cm=moved,
                       x0=p[0], y0=p[1], h0=p[2],
                       x1=p2[0] if p2 else None, y1=p2[1] if p2 else None,
                       h1=p2[2] if p2 else None,
                       dheading_deg=wrap(p2[2] - p[2]) if p2 else None,
                       i2cf_before=intfield(before, 'i2cf'),
                       i2cf_after=intfield(after, 'i2cf'),
                       cyc_before=intfield(before, 'cyc'),
                       cyc_after=intfield(after, 'cyc'),
                       reason=after.get('reason'), done=after.get('done'))
            rows.append(row)
            print(f"seg {i:2d}: cmd {d:.1f} cm  moved {moved:5.2f} cm  "
                  f"dh {row['dheading_deg']:+6.2f}  "
                  f"i2cf +{row['i2cf_after'] - row['i2cf_before']}"
                  f"/{row['cyc_after'] - row['cyc_before']} cyc  "
                  f"reason={row['reason']}")
            _write_csv(out / 'segments.csv', rows)
    finally:
        stop.set()
        th.join(timeout=3)

    lines = link.since(poll_from, 'status')
    with open(out / 'status-8hz.log', 'w') as f:
        for t, ln in lines:
            f.write(f'{t:.3f} {ln}\n')

    if not rows:
        print('coldboot: no segments completed -- FAIL')
        return False

    travel = sum(r['moved_cm'] for r in rows
                 if r['moved_cm'] == r['moved_cm'])
    commanded = sum(r['commanded_cm'] for r in rows)
    dh = sum(r['dheading_deg'] for r in rows
             if r['dheading_deg'] is not None)
    seg_i2cf = rows[-1]['i2cf_after'] - rows[0]['i2cf_before']
    seg_cyc = rows[-1]['cyc_after'] - rows[0]['cyc_before']
    rate = 1000.0 * seg_i2cf / seg_cyc if seg_cyc else None
    # An "early end" is a segment far below the band every healthy
    # segment in Session A's three boots landed in (2.41-3.37 cm for a
    # 4.0 cm command). Expressed as a fraction of the command so a
    # different --seg-mm still means something.
    short = [r for r in rows
             if r['moved_cm'] == r['moved_cm']
             and r['moved_cm'] < COLDBOOT_SHORT_FRAC * r['commanded_cm']]
    print(f"\ntravel {travel:.2f} / {commanded:.1f} cm commanded "
          f"({100.0*travel/commanded:.1f} %)")
    print(f"net heading change {dh:+.2f} deg over {travel:.2f} cm "
          f"({dh/travel:+.3f} deg/cm)" if travel else '')
    print(f"i2cf over the segments: +{seg_i2cf} in {seg_cyc} cyc"
          + (f" ({rate:.1f} per 1000 cyc)" if rate is not None else ''))
    print(f"early-ending segments (< {COLDBOOT_SHORT_FRAC:.0%} of command): "
          f"{[r['seg'] for r in short] or 'none'}")
    if short:
        print('  ^ ticket 010\'s bar is ZERO across three cold boots -- '
              'this run FAILS it; capture is kept for ticket 005')
    summary = dict(mode='coldboot', boot_label=a.boot_label,
                   cold_boot=cold, pre_move_status=st0,
                   pre_pivot=pre_pivot, segments=rows,
                   travel_cm=travel, commanded_cm=commanded,
                   net_heading_deg=dh,
                   heading_per_cm=(dh / travel) if travel else None,
                   segment_i2cf=seg_i2cf, segment_cyc=seg_cyc,
                   i2cf_per_1000_cyc=rate,
                   early_ending_segments=[r['seg'] for r in short],
                   status_samples=len(lines))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
    print(f'-> {out}/')
    return not short


# --- busguard: Item 1 restated so the counter can actually answer it ------
#
# Sprint 030's bus-ownership guard claims a wire-issued OTOS read landing
# mid-drive no longer destroys the encoder sample it lands inside of.
# Ticket 009 Item 1 tried to check that by watching `i2cf` "not climb"
# across a run. That bar cannot pass on post-028 firmware: `i2cf`
# increments whenever a DRIVEN wheel's raw counts are unchanged
# (src/DESIGN.md "Sprint 028: frozen-read hold"), i.e. on every
# breakaway, whether or not anything touched the bus. MEASURED across
# Session A's four logs, 100 % of i2cf increments landed within 1 s of a
# command, in a window covering only 19-29 % of wall time.
#
# So the question is restated as a CONTROLLED COMPARISON on one build:
# identical legs, half of them with a `RUN:fix` (which calls
# worldReady()/logFix() -> readWorld(), a real OTOS I2C transaction from
# the protocol fiber) fired mid-drive, half without. The guard's claim
# is that the two groups are indistinguishable. Pre-guard, the OTOS
# transaction could land inside the Nezha encoder's select->read settle
# window and destroy that sample -- which shows up as extra i2cf on the
# interfered legs AND as travel/heading error, since a destroyed sample
# is a lost tick of control.
#
# Reporting both is the point: i2cf alone cannot separate "the guard
# works" from "breakaway dominates", but a DIFFERENCE between the two
# groups can only come from the interference.


def run_busguard(link, cam, a, out):
    """Alternating legs, every other one interfered with by a mid-drive
    `RUN:fix`. Reports i2cf-per-move and camera travel/heading for the
    interfered vs clean groups."""
    out.mkdir(parents=True, exist_ok=True)
    rows, sign = [], 1
    for i in range(a.legs):
        interfere = (i % 2 == 1)
        lights_on()
        pose = cam.fix(n=4)
        if pose is None:
            print('STOP: no camera fix'); break
        d = sign * a.busguard_mm
        h = math.radians(pose[2])
        end = (pose[0] + (d / 10.0) * math.cos(h),
               pose[1] + (d / 10.0) * math.sin(h))
        offenders = fieldlib.check_path([(pose[0], pose[1]), end])
        if offenders:
            print(f'STOP: projected leg leaves the margin near {offenders[0]}')
            break
        before = _status_now(link)
        tid, _ack = link.seqd(f'MOVE_X {d} 0 {a.cruise_seg} {a.timeout_ms}',
                              wait=2.0)
        fix_line = None
        if interfere:
            time.sleep(a.busguard_delay)      # land it INSIDE the drive
            t0 = time.time()
            link.send('RUN:fix')
            # RUN:fix -> logFix("now") emits `OCAL:now:<x>:<y>:<h>`, and
            # `OERR:read-failed:now` first if the OTOS read itself failed
            # (test/test.ts:310-320). Both are the reply; a failed read
            # is the more interesting one and must not be silently
            # counted as "no reply".
            fix_line = link.wait_for(r'^(OCAL|OERR):', t0, 2.0)
        time.sleep(max(0.0, a.seg_settle - (a.busguard_delay if interfere else 0)))
        cam.settle(timeout=5.0)
        after = _status_now(link)
        p2 = cam.fix(n=4)
        moved = (math.hypot(p2[0] - pose[0], p2[1] - pose[1])
                 if p2 else float('nan'))
        row = dict(leg=i, interfered=interfere, commanded_mm=d,
                   cam_mm=moved * 10.0,
                   len_err_mm=moved * 10.0 - abs(d),
                   dheading_deg=wrap(p2[2] - pose[2]) if p2 else None,
                   i2cf_delta=intfield(after, 'i2cf') - intfield(before, 'i2cf'),
                   cyc_delta=intfield(after, 'cyc') - intfield(before, 'cyc'),
                   run_fix_reply=fix_line, reason=after.get('reason'))
        rows.append(row)
        print(f"leg {i:2d} {'FIX ' if interfere else 'clean'} cmd {d:+5d} "
              f"cam {row['cam_mm']:6.1f} mm (err {row['len_err_mm']:+.1f}) "
              f"dh {row['dheading_deg']:+6.2f} i2cf +{row['i2cf_delta']}"
              f"/{row['cyc_delta']} cyc"
              + (f"  RUN:fix -> {fix_line}" if interfere else ''))
        _write_csv(out / 'busguard-legs.csv', rows)
        sign = -sign
        time.sleep(a.pause)

    if len(rows) < 2:
        print('busguard: too few legs -- INCONCLUSIVE')
        return False

    def stats(group):
        n = len(group)
        if not n:
            return None
        return dict(n=n,
                    i2cf_per_move=sum(r['i2cf_delta'] for r in group) / n,
                    mean_len_err=sum(r['len_err_mm'] for r in group) / n,
                    mean_abs_dh=sum(abs(r['dheading_deg']) for r in group
                                     if r['dheading_deg'] is not None) / n)
    clean = stats([r for r in rows if not r['interfered']])
    fixed = stats([r for r in rows if r['interfered']])
    print(f"\nclean legs:      {clean}")
    print(f"interfered legs: {fixed}")
    verdict = None
    if clean and fixed:
        d_i2cf = fixed['i2cf_per_move'] - clean['i2cf_per_move']
        d_len = fixed['mean_len_err'] - clean['mean_len_err']
        print(f"difference (interfered - clean): i2cf/move {d_i2cf:+.2f}, "
              f"length err {d_len:+.1f} mm")
        print('NOTE: this is a small-n comparison. State it as a difference '
              'with its n, never as a pass on one leg either way.')
        verdict = dict(delta_i2cf_per_move=d_i2cf, delta_len_err_mm=d_len)
    (out / 'summary.json').write_text(json.dumps(
        dict(mode='busguard', legs=rows, clean=clean, interfered=fixed,
             difference=verdict), indent=2, default=str))
    print(f'-> {out}/')
    return True


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


DISTURBED_DRIFT_CM = 8.0      # a pivot moves the centre < 1 cm, an unregistered tag lever ~5; a hand 9-27 (2026-09-04)
DISTURBED_DISAGREE_DEG = 15.0  # camera vs encoders never differ this much on a real pivot
                               # (the worst honest case, tigez's mid-ramp glitch, was ~8)
DISTURBED_ENCODER_DEG = 30.0   # the encoders say the robot executed a different angle


def disturbed(r):
    """True for a pivot whose score cannot be the drivetrain's: the body
    translated (someone moved the robot -- gopiv 2026-09-04 pivots 17-19,
    9-27 cm), or camera and encoders disagree by tens of degrees (a
    stale rest fix, or a garbled command the robot executed as a
    different angle: gopiv #23 turned -90 for a commanded -180 on both
    instruments). Kept in turns.csv, excluded from the statistics."""
    enc = r.get('encoder_error_deg')
    if enc not in (None, '', 'None'):
        if abs(float(enc)) > DISTURBED_ENCODER_DEG:
            return True
        if abs(float(r['error_deg']) - float(enc)) > DISTURBED_DISAGREE_DEG:
            return True
    return float(r['drift_cm']) > DISTURBED_DRIFT_CM


def analyze(rows, a):
    all_rows = rows
    rows = [r for r in rows if not disturbed(r)]
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
        field = getattr(a, 'overrun_field', 'pivot_overrun')
        suggested = {'rotational_slip': round(slip_new, 4),
                     f'{field}_mm': round(overrun_mm, 2),
                     'model': 'camera = gain*cmd + offset; slip_new = slip*gain; '
                              f'{field}_new = {field} + offset_rad*b_eff/2'}
        if field == 'stop_distance':
            # design motion-profile-unification.md S10.2: stop_distance is
            # the residual AFTER lag is set; an unmeasured lag shows up
            # here as a speed-dependent offset that stop_distance cannot
            # absorb.
            suggested['note'] = ('029 firmware: measure and SET lag first (S10.2); '
                                 'this stop_distance is only valid at the cruise it was fitted at')
    return {
        'robot': a.robot, 'cruise_mm_s': a.cruise, 'n_turns': len(rows),
        'n_disturbed_excluded': len(all_rows) - len(rows),
        'disturbed_turns': [r.get('turn') for r in all_rows if disturbed(r)],
        'slip_during_run': a.slip_now, 'pivot_overrun_during_run_mm': a.overrun_now,
        'overrun_field': getattr(a, 'overrun_field', 'pivot_overrun'), 'lag_during_run_s': getattr(a, 'lag_now', None),
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


# --------------------------------------------- G1-G6 gate scoring (pure)
#
# Every function in this section takes plain data (no Link/Camera) and
# is unit-testable without hardware -- see
# tests/calibration/test_turn_calibration_gates.py. The drive-and-measure
# halves that call these (one_leg/one_arc/run_g1..run_g6 below) need a
# live robot and camera and are exercised on real hardware in Session C
# (ticket 016), not here (sprint 031 ticket 007's own Testing section).

def camera_noise_floor(cam, n=20, gap=0.12):
    """At-rest camera heading noise: sd and peak-to-peak over `n`
    single-shot samples. This is the instrument fact the restated G1
    bar (G1_SD_DEG) is sized against -- folded from sprint 029's
    g1_run.py (`g1-run.log` line 1: n=20, sd=1.03, peak-to-peak 4.2).
    `cam` needs only a `.sample()` method returning `(t, x, y,
    heading_deg, speed)` or `None`, so a fake stands in for tests."""
    samples = []
    end = time.time() + n * gap * 3 + 1.0
    while len(samples) < n and time.time() < end:
        s = cam.sample()
        if s is not None:
            samples.append(s[3])
        time.sleep(gap)
    if not samples:
        return {'n': 0, 'sd': None, 'ptp': None}
    sy = sum(math.sin(math.radians(h)) for h in samples)
    cy = sum(math.cos(math.radians(h)) for h in samples)
    mean = math.degrees(math.atan2(sy, cy))
    dev = [wrap(h - mean) for h in samples]
    sd = (sum(d * d for d in dev) / len(dev)) ** 0.5
    return {'n': len(samples), 'sd': round(sd, 3), 'ptp': round(max(dev) - min(dev), 3)}


def g1_score(errs):
    """Restated G1 bar (sprint 031 ticket 007): mean|err| <=
    G1_MEAN_ABS_ERR_DEG, sd <= G1_SD_DEG. `errs` are camera-measured-
    minus-commanded pivot errors [deg]."""
    if not errs:
        return {'n': 0, 'mean_abs_err': None, 'sd': None, 'mean': None, 'passed': False}
    n = len(errs)
    mean = sum(errs) / n
    mean_abs = sum(abs(e) for e in errs) / n
    sd = (sum((e - mean) ** 2 for e in errs) / n) ** 0.5
    passed = mean_abs <= G1_MEAN_ABS_ERR_DEG and sd <= G1_SD_DEG
    return {'n': n, 'mean_abs_err': round(mean_abs, 3), 'sd': round(sd, 3),
            'mean': round(mean, 3), 'passed': passed}


def g2_score(endpoint_errs_mm):
    """Restated G2 bar (sprint 031 ticket 007): mean endpoint error <=
    G2_ENDPOINT_MM."""
    if not endpoint_errs_mm:
        return {'n': 0, 'mean': None, 'max': None, 'n_within': 0, 'passed': False}
    n = len(endpoint_errs_mm)
    mean = sum(endpoint_errs_mm) / n
    passed = mean <= G2_ENDPOINT_MM
    return {'n': n, 'mean': round(mean, 2), 'max': round(max(endpoint_errs_mm), 2),
            'n_within': sum(1 for e in endpoint_errs_mm if e <= G2_ENDPOINT_MM), 'passed': passed}


def arc_expected_endpoint_mm(d_mm, theta_rad):
    """(ex_mm, ey_mm) endpoint of a constant-curvature MOVE_X arc of
    chord-drive distance `d_mm` and turn `theta_rad`, in the START
    pose's own body frame (x forward, y left): R = d/theta, endpoint
    (R sin(theta), R(1 - cos(theta))). Folded from sprint 029's
    g2_run.py `expected()`."""
    R = d_mm / theta_rad
    return R * math.sin(theta_rad), R * (1.0 - math.cos(theta_rad))


def arc_path_points(p0, d_mm, theta_rad, n=8):
    """`n + 1` world `(x_cm, y_cm)` waypoints tracing the ACTUAL arc
    geometry (not just its endpoint chord) from world pose `p0 =
    (x_cm, y_cm, heading_deg)` -- for the mandatory pre-flight path
    check (.claude/rules/playfield-testing.md: "compute the full
    projected path ... through every planned leg and turn"). An arc
    bows outward past the straight line to its own endpoint, so
    checking only the start/end points under-counts a margin
    violation partway around the curve."""
    x0, y0, h0 = p0
    h0r = math.radians(h0)
    R = d_mm / theta_rad
    pts = []
    for i in range(n + 1):
        th = (i / n) * theta_rad
        bx, by = R * math.sin(th), R * (1.0 - math.cos(th))  # body frame, mm
        wx = x0 + (bx * math.cos(h0r) - by * math.sin(h0r)) / 10.0
        wy = y0 + (bx * math.sin(h0r) + by * math.cos(h0r)) / 10.0
        pts.append((wx, wy))
    return pts


def leg_metrics(frames):
    """Wheel-speed metrics from one move's telemetry frames (dicts with
    string-valued `vl`/`vr`/`dutl`/`dutr`/`now`, the shape one_leg()/
    one_arc()/run_g5() build): peak speed, first moving-tick speed, max/
    min mean-wheel acceleration, and tail monotonicity. Folded from
    sprint 029's g3_run.py -- feeds G3/G4 (a straight leg's frames) and
    G5 (a WHEELS_V trial's frames; the same telemetry columns apply to
    both)."""
    moving = [f for f in frames if speed(f, 'vl') or speed(f, 'vr')]
    vmean = [0.5 * (speed(f, 'vl') + speed(f, 'vr')) for f in moving]
    peak = max((max(abs(speed(f, 'vl')), abs(speed(f, 'vr'))) for f in frames), default=None)
    first_v = abs(vmean[0]) if vmean else None
    dvdt = []
    for f0, f1 in zip(moving, moving[1:]):
        dt = (frame_now_ms(f1) - frame_now_ms(f0)) / 1000.0
        if dt > 0:
            dvdt.append((0.5 * (speed(f1, 'vl') + speed(f1, 'vr')) -
                         0.5 * (speed(f0, 'vl') + speed(f0, 'vr'))) / dt)
    tail = [abs(v) for v in vmean[-10:]]
    monotone = all(b <= a + 8 for a, b in zip(tail, tail[1:])) if len(tail) > 1 else True
    return {'peak_v': peak, 'first_moving_v': first_v,
            'max_accel': max(dvdt) if dvdt else None, 'min_accel': min(dvdt) if dvdt else None,
            'tail_monotone': monotone, 'tail_v': tail}


def fit_wheel_lag(frames, sign, accel=400.0, vcmd=200.0, key='vl'):
    """Least-squares lag [s] of one wheel's measured speed against the
    commanded accel ramp from a WHEELS_V step, folded and made pure
    from sprint 029's lag_measure.py `fit_lag` (split per-wheel; the
    caller passes `frames` already trimmed to start at the last
    zero-duty frame before onset). `None` if fewer than 2 frames."""
    if len(frames) < 2:
        return None
    t0 = frame_now_ms(frames[0])
    best = None
    for i in range(0, 401, 5):
        lag = i / 1000.0
        sse, n = 0.0, 0
        for f in frames:
            t = (frame_now_ms(f) - t0) / 1000.0
            if t > 1.4:
                break
            cmd = sign * min(vcmd, max(0.0, accel * (t - lag)))
            sse += (speed(f, key) - cmd) ** 2
            n += 1
        if n and (best is None or sse < best[1]):
            best = (lag, sse, n)
    if best is None:
        return None
    return {'lag': best[0], 'rms': round(math.sqrt(best[1] / best[2]), 2), 'n': best[2]}


def square_closure_ok(closure_mm, baseline_mm=G6_BASELINE_CLOSURE_MM):
    """Unchanged G6 bar: closure <= the baseline
    (reports/gopiv-closure-20260901.md)."""
    return closure_mm <= baseline_mm


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
        if not ack or not ack.startswith('ack'):
            # A lossy carrier can lose all three sends; that is not a
            # convention finding. One more try before calling it.
            print(f'  (MOVE_X {deg:+d} not acknowledged: {ack}; retrying once)')
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
        # CONVENTION gate, not accuracy (field-dance-first): the sign and rough
        # size must be right; an uncalibrated robot 10 deg long still passes.
        ok = abs(wrap(got - deg)) <= 30 and abs(got) > 5
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
def rescore(out):
    """Re-derive camera_deg/error_deg from the rest-to-rest fixes snapped
    to the commanded lap (see one_turn), rewriting turns.csv and
    summary.json in place. Idempotent; repairs runs scored before the
    lap snap was fixed (2026-09-04)."""
    out = pathlib.Path(out)
    rows = list(csv.DictReader(open(out / 'turns.csv')))
    if not rows:
        return
    changed = False
    for r in rows:
        cmd, cam = float(r['commanded']), float(r['camera_deg'])
        fixed = cmd + wrap(cam - cmd)
        if abs(fixed - cam) > 1e-6:
            r['camera_deg'] = f'{fixed:.2f}'; r['error_deg'] = f'{fixed - cmd:.2f}'; changed = True
    if not changed:
        return
    fields = list(rows[0].keys())
    with open(out / 'turns.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    sp = out / 'summary.json'
    if sp.exists():
        old = json.loads(sp.read_text())
        a = argparse.Namespace(robot=old.get('robot'), cruise=old.get('cruise_mm_s'),
                               slip_now=old.get('slip_during_run') or 0.952,
                               overrun_now=old.get('pivot_overrun_during_run_mm') or 0.0,
                               trackwidth_mm=old.get('trackwidth_assumed_mm') or 114.2)
        typed = []
        for r in rows:
            t = dict(r)
            for k in ('commanded', 'camera_deg', 'error_deg', 'drift_cm'):
                t[k] = float(t[k])
            typed.append(t)
        new = analyze(typed, a)
        new['rescored'] = 'lap snapped to commanded (2026-09-04)'
        sp.write_text(json.dumps(new, indent=2))
    print(f'rescore: {out} rewritten (lap snap)')


def render(out):
    """Charts + REPORT.md from the CSVs. Runs under any interpreter with
    matplotlib (the project venv has none; use a scratch venv)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out = pathlib.Path(out)
    rescore(out)
    turns = list(csv.DictReader(open(out / 'turns.csv')))
    frames = list(csv.DictReader(open(out / 'frames.csv'))) if (out / 'frames.csv').exists() else []   # --no-tlm runs have none
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
        ax.plot(t, [speed(f, 'vl') for f in fs], label='vl', lw=1.2)
        ax.plot(t, [speed(f, 'vr') for f in fs], label='vr', lw=1.2)
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
        fld = next((k[:-3] for k in s if k.endswith('_mm')), 'pivot_overrun')
        lines += [f"Suggested: `SET rotational_slip {s['rotational_slip']}`, `SET {fld} {s[fld + '_mm']}` ({s['model']})."
                  + (f" {s['note']}" if s.get('note') else ''), '']
    lines += ['| # | cmd | camera | err | encoder err | drift cm | peak vl | peak vr | dur s | reason |', '|---|---|---|---|---|---|---|---|---|---|']
    for r in turns:
        enc = '' if r['encoder_error_deg'] is None else f"{r['encoder_error_deg']:+.1f}"
        mark = ' (disturbed, excluded)' if disturbed(r) else ''
        lines.append(f"| {r['turn']}{mark} | {r['commanded']:+.0f} | {r['camera_deg']:+.1f} | {r['error_deg']:+.1f} | "
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
        rescore(d)
        rows = list(csv.DictReader(open(d / 'turns.csv')))
        n_all = len(rows)
        rows = [r for r in rows if not disturbed(r)]
        summ = json.loads((d / 'summary.json').read_text()) if (d / 'summary.json').exists() else {}
        label = f"{summ.get('robot', d.name)} ({d.name}, {len(rows)}/{n_all} pivots)"
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
        ax.plot([float(f['t_rel']) for f in fs], [speed(f, 'vr') for f in fs], label=f'{label} vr')
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
    global CAM, FIELD_X, FIELD_Y
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot', default='tigez')
    ap.add_argument('--host'); ap.add_argument('--port', type=int)
    ap.add_argument('--wifi', metavar='NAME|IP')
    ap.add_argument('--radio', action='store_true',
                    help="drive over the torture relay pool on the robot's own channel/group (lossy)")
    ap.add_argument('--tag', type=int)
    ap.add_argument('--camera', default=CAM, help='aprilcam camera name (main field: arducam-ov9782-usb-camera; secondary: hd-usb-camera)')
    ap.add_argument('--field-cm', type=float, nargs=2, metavar=('W', 'H'), default=None,
                    help='playfield width and height [cm] (main 134.3 89.3, secondary 110 70); sets the rail limits')
    ap.add_argument('--heading-offset', type=float, default=0.0,
                    help='deg added to the camera yaw (0 when the tag mount is registered)')
    ap.add_argument('--angles', type=int, nargs='+', default=[90, 107, 180])
    ap.add_argument('--reps', type=int, default=4,
                    help='repeats per angle AND sign (sweep); pivot PAIRS for --mode g1 '
                         '(defaults to 6 = 12 pivots, sprint 029s g1_run.py, unless overridden)')
    ap.add_argument('--cruise', type=int, default=60, help='wheel speed [mm/s] for the pivot (0 = firmware default)')
    ap.add_argument('--timeout-ms', type=int, default=9000)
    ap.add_argument('--settle', type=float, default=1.0)
    ap.add_argument('--pause', type=float, default=0.5)
    ap.add_argument('--set', nargs='*', default=[], metavar='FIELD=VALUE', help='SET wire fields before the sweep')
    ap.add_argument('--no-tlm', action='store_true', help='no TLM FULL during the sweep (camera-only scoring)')
    ap.add_argument('--no-poll', action='store_true', help='no STATUS polling during a move; the camera decides when it is over')
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
    ap.add_argument('--mode', choices=['sweep', 'g1', 'g2', 'g3', 'g5', 'g6', 'coldboot', 'busguard'], default='sweep',
                    help="sweep (default) = the multi-angle pivot sweep above; g1/g2/g3/g5/g6 = "
                         "sprint 029's acceptance gates, folded in as named modes (sprint 031 ticket "
                         "007). g4 reports alongside g3 (same telemetry, same script upstream). "
                         "coldboot = the cold-boot segment protocol (tickets 009/010). "
                         "busguard = ticket 009 Item 1's mid-drive OTOS-read comparison. "
                         "G1 and G2 use this sprint's RESTATED bars; G3/G4/G5/G6 are unchanged. "
                         "See each run_gN() docstring for what it folds in.")
    ap.add_argument('--n-fix', type=int, default=G1_MIN_FIX_SAMPLES,
                    help=f'g1: camera rest-fix sample count (restated bar needs >= {G1_MIN_FIX_SAMPLES})')
    ap.add_argument('--arcs', type=int, default=6, help='g2: number of arcs (alternating +/-)')
    ap.add_argument('--arc-mm', type=int, default=300, help='g2: arc chord distance [mm]')
    ap.add_argument('--arc-deg', type=float, default=45.0, help='g2: arc turn angle [deg]')
    ap.add_argument('--legs', type=int, default=6, help='g3/g4: number of alternating straight legs')
    ap.add_argument('--leg-mm', type=int, default=600, help='g3/g4: leg length [mm]')
    ap.add_argument('--cruise-g5', type=int, default=200, help='g5: WHEELS_V step command [mm/s]')
    ap.add_argument('--hold-ms', type=int, default=1500, help='g5: WHEELS_V hold duration [ms]')
    ap.add_argument('--side-mm', type=int, default=200, help='g6: square side length [mm] (200 or 500)')
    ap.add_argument('--laps', type=int, default=3, help='g6: number of laps')
    ap.add_argument('--segments', type=int, default=10,
                    help='coldboot: number of MOVE_X segments after the boot')
    ap.add_argument('--seg-mm', type=int, default=40,
                    help='coldboot: segment distance [mm]')
    ap.add_argument('--cruise-seg', type=int, default=100,
                    help='coldboot: segment cruise speed [mm/s]')
    ap.add_argument('--seg-settle', type=float, default=1.8,
                    help='coldboot: seconds to wait after each MOVE_X before the camera fix')
    ap.add_argument('--busguard-mm', type=int, default=120,
                    help='busguard: leg length [mm]')
    ap.add_argument('--busguard-delay', type=float, default=0.6,
                    help='busguard: seconds after the MOVE_X ack to fire RUN:fix')
    ap.add_argument('--boot-label', default='boot1',
                    help='coldboot: sub-directory under --out for THIS power cycle')
    a = ap.parse_args()
    CAM = a.camera
    if a.field_cm:
        FIELD_X, FIELD_Y = a.field_cm[0] / 2.0, a.field_cm[1] / 2.0
    if a.render:
        render(a.render); return 0
    if a.compare:
        compare(a.compare, a.out or 'reports/turn-compare'); return 0
    if a.mode == 'g1' and a.reps == 4:   # untouched default -> match sprint 029's 12-pivot g1_run.py
        a.reps = 6

    tag = a.tag or TAGS.get(a.robot)
    if not tag:
        ap.error(f'no tag known for {a.robot}; pass --tag')
    name = a.robot if a.mode == 'sweep' else f'{a.robot}-{a.mode}'
    out = pathlib.Path(a.out or f'reports/{name}-turn-cal-{time.strftime("%Y%m%d-%H%M")}')

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
    a.slip_now = wire_get(link, 'rotational_slip', 0.952)
    # Sprint 029 renamed the per-wheel end-of-move coast `pivot_overrun` to
    # `stop_distance` (mm) and added `lag` (s); pre-029 firmware still
    # answers `pivot_overrun`. Ask for the new name first and remember
    # which vocabulary the robot speaks so the suggestion uses it.
    sd = wire_get(link, 'stop_distance')
    if sd is not None:
        a.overrun_field, a.overrun_now = 'stop_distance', sd
        a.lag_now = wire_get(link, 'lag')
    else:
        a.overrun_field = 'pivot_overrun'
        a.overrun_now = wire_get(link, 'pivot_overrun', 0.0)
        a.lag_now = None
    lag_txt = '' if a.lag_now is None else f' lag={a.lag_now}'
    print(f'rotational_slip={a.slip_now} {a.overrun_field}={a.overrun_now}{lag_txt} (live), trackwidth assumed {a.trackwidth_mm} mm')

    lights_on()
    cam = Camera(tag, a.heading_offset)
    pose = cam.fix()
    if pose is None:
        raise SystemExit(f'camera does not see tag {tag} -- lights? robot on the field?')
    print(f'camera: {CAM}, field +-{FIELD_X} x +-{FIELD_Y} cm, margin {a.margin} cm; tag {tag} at ({pose[0]:.1f}, {pose[1]:.1f}) cm heading {pose[2]:.1f} deg')
    bad = check_safe(pose, a.margin)
    if bad:
        raise SystemExit(f'not safe to pivot: {bad}')

    gate_ok = True
    try:
        if a.dance or a.dance_only:
            passed = dance(link, cam, a.cruise, a.dance_turns_only, a.margin)
            if not passed:
                return 1
            if a.dance_only:
                return 0
        if a.mode == 'sweep':
            run_sweep(link, cam, a, out)
        else:
            gate_fn = {'g1': run_g1, 'g2': run_g2, 'g3': run_g3, 'g5': run_g5,
                       'g6': run_g6, 'coldboot': run_coldboot,
                       'busguard': run_busguard}[a.mode]
            gate_ok = gate_fn(link, cam, a, out)
    finally:
        link.seqd('STOP', wait=1.0)
        getattr(a, "link", link).close()
    print(f'wrote {out}; render with: <plot venv>/bin/python {sys.argv[0]} --render {out}')
    return 0 if gate_ok else 1


if __name__ == '__main__':
    sys.exit(main())
