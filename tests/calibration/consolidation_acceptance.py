#!/usr/bin/env python3
"""consolidation_acceptance -- the on-field acceptance of sprint 034's
consolidated link, camera and geofence.

Sprint 034 collapsed four link layers onto `tools/link.py`, two `Cam`
classes onto `tools/camlink.py`, two repositioning loops onto
`tools/reposition.py`, and pointed every geofence at `tools/field.py`.
Every one of those is proved host-side with an injected fake. Three
things a fake cannot prove, and this program is the scripted session
that does (sprint 034 ticket 013):

  a. a `MOVE_X` sent through the consolidated `Link` really moves the
     robot -- the id is *attached* host-side, but only a robot shows it
     is *accepted and executed*, and only an EXTERNAL instrument shows
     the robot moved. Odometry cannot detect its own failure to move
     (`.claude/rules/playfield-testing.md`), so travel here is scored
     from the overhead camera and never from the wire;
  b. the in-process `Cam` reads the same poses the deleted camera
     subprocess did -- a real daemon, a real tag and a real REGISTERED
     mount, compared against the ground truth of a known dot, with the
     daemon's corrected heading used UNCHANGED
     (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`);
  c. the geofence refuses a real out-of-bounds target without refusing
     a legitimate in-bounds one.

Run it (WiFi TCP is the default carrier,
`.claude/rules/connecting-to-a-robot.md`)::

    uv run python tests/calibration/calibrate.py acceptance tovez
    uv run python tests/calibration/calibrate.py acceptance tovez --radio
    uv run python tests/calibration/calibrate.py acceptance tovez \
        --serial nada.local:port --dot NE

    uv run python tests/calibration/calibrate.py acceptance tovez --dry-run

`--dry-run` prints the plan -- every command line that would go out --
and opens no carrier, no camera and no socket, so the argument parsing
and the plan can be read before a robot is anywhere near it.

**Pre-flight, in this order, and a run stops on the first non-PASS.**
Lights (the Shelly turns itself off, and a dark field looks exactly
like a broken camera); `PING` on the chosen carrier (`PING` is the
liveness probe -- `HELLO` is a session RESET and must not be used as
one); the field-centre tag at world (0, 0); this robot's tag visible
and registered from the calibration of record. Every commanded move
then re-checks its own projected path from a freshly MEASURED start
pose before its first byte goes out -- the geofence is the backstop,
not the primary check.

**Park it facing inward.** The `MOVE_X` probe drives along the robot's
CURRENT measured heading, and the path check is computed from that
measured pose -- so a robot on a corner dot facing outward has its
probe refused, correctly, before anything is sent. Face it toward the
field centre.

**This program asserts nothing about hardware on its own.** It writes
what it measured into `<capture-dir>/notes.md`, and that file is what a
later MEASURED citation points at (`.claude/rules/measurement-citations.md`).
`captures/` is gitignored, so the artifact has to be committed with
`git add -f` or the citation points at nothing.

Host-side tests: `tests/calibration/test_consolidation_acceptance.py`
(fake link, fake camera, no robot, no daemon, no network).
"""
import argparse
import dataclasses
import json
import math
import pathlib
import socket
import sys
import time
import urllib.request

_HERE = pathlib.Path(__file__).resolve().parent
_TOOLS = _HERE.parents[1] / 'tools'
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import camlink  # noqa: E402  (path must be set up first)
import field as fieldlib  # noqa: E402
import robotlink  # noqa: E402
import wifilink  # noqa: E402
from field import PathRefused, require_clear_path, wrap  # noqa: E402
from reposition import Repositioner  # noqa: E402

#: The Shelly Plus 1 that runs the room lights, read-only status
#: endpoint (`.claude/rules/playfield-testing.md`). Read, never set:
#: this program reports what the lights ARE, and an operator who wants
#: them on turns them on -- a check that fixes what it is checking
#: cannot report that it was broken.
SHELLY_STATUS_URL = 'http://192.168.1.122/rpc/Switch.GetStatus?id=0'
SHELLY_SET_ON_URL = 'http://192.168.1.122/rpc/Switch.Set?id=0&on=true'

#: AprilTag 1 is the fixed field-centre marker and must read world
#: (0, 0). `camlink.py --check` verifies tags 10/11 instead, which the
#: ArUco border set made unreliable to look for -- tag 1 is the check
#: `.claude/rules/playfield-testing.md` names.
FIELD_CENTRE_TAG = 1
FIELD_CENTRE_TOL_CM = 3.0

PASS, FAIL, BLOCKED = 'PASS', 'FAIL', 'BLOCKED'

#: `--wifi-tcp` given with no value means "this robot, by name".
_SELF = '<robot>'


@dataclasses.dataclass
class Result:
    """One check's outcome. `status` is `PASS`, `FAIL` or `BLOCKED`.

    The three are deliberately distinct. `FAIL` is a finding about the
    robot or the consolidated code; `BLOCKED` is a finding about the
    bench (dark field, dead daemon, tag out of frame, a projected path
    that leaves the field) and says nothing at all about what was under
    test. Collapsing them would let a dark room read as a broken
    camera, which is the single most-repeated misdiagnosis on this rig.
    """

    name: str
    status: str
    detail: str
    data: dict = dataclasses.field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == PASS

    def line(self) -> str:
        return f'{self.name:28s} {self.status:8s} {self.detail}'


# ----------------------------------------------------------- pre-flight

def _http_json(url, timeout=3.0):
    """The real HTTP getter. Injected in tests; never called there."""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def check_lights(get_json=None, url=SHELLY_STATUS_URL):
    """PASS iff the Shelly reports `output == true`.

    `get_json` is an injected callable taking a URL and returning the
    parsed JSON body -- the real one is `_http_json`, which uses
    `urllib`. A dark field is `BLOCKED`, not `FAIL`: it says nothing
    about the link, the camera or the geofence, and the remedy is a
    curl to `SHELLY_SET_ON_URL`, not a code change.
    """
    getter = get_json or _http_json
    try:
        status = getter(url)
    except Exception as e:
        return Result('lights', BLOCKED,
                      f'the Shelly at {url} did not answer ({e}) -- check '
                      f'the lights by hand before reading anything else')
    output = status.get('output') if isinstance(status, dict) else None
    if output is True:
        return Result('lights', PASS, 'output=true', {'output': True})
    if output is False:
        return Result('lights', BLOCKED,
                      'output=false -- THE FIELD IS DARK. A dark field looks '
                      f'exactly like a broken camera or a lost robot. Turn '
                      f'them on: curl -s "{SHELLY_SET_ON_URL}"',
                      {'output': False})
    return Result('lights', BLOCKED,
                  f'the Shelly answered without an "output" key: {status!r}')


def check_ping(link, wait=3.0, tries=3):
    """PASS iff the robot answers `PING` with `pong` on this carrier.

    `PING` and not `HELLO`: `HELLO` is a session RESET that sets the
    robot's `expectedNext_` to 1, so firing it at a live session
    desyncs the link being checked (`.claude/rules/playfield-testing.md`).
    The carrier's own open already sent exactly one `HELLO`.
    """
    for attempt in range(tries):
        link.send('PING')
        for line in link.lines(wait):
            if line.startswith('pong'):
                return Result('robot answers PING', PASS,
                              f'{line} (attempt {attempt + 1})',
                              {'pong': line})
    return Result('robot answers PING', FAIL,
                  f'no pong in {tries} tries of {wait:.1f} s -- the robot is '
                  f'not on this carrier (unmigrated radio address? WiFi '
                  f'dropped under motor load? board off?)')


def one_frame(cam):
    """The first frame `Cam.frames()` yields as
    `{tag_number: (yaw_deg, x_cm, y_cm)}`, or `None` if the stream is
    dead. An empty dict is a real frame in which nothing was detected,
    which is a different answer from a dead instrument.
    """
    try:
        for tags in cam.frames():
            return tags
    except camlink.CamDown:
        return None
    return {}


def check_field_centre(frame, tol_cm=FIELD_CENTRE_TOL_CM,
                       tag=FIELD_CENTRE_TAG):
    """PASS iff `tag` (the fixed field-centre marker) reads world
    (0, 0) within `tol_cm`.

    `frame` is one `one_frame()` result. `None` (a dead stream) and a
    tag that is simply not in view are both `BLOCKED` -- the daemon and
    the lights are bench conditions, not the thing under test. A tag
    that IS visible and reads somewhere other than the origin is a
    `FAIL`: the world frame itself is wrong, and every pose this
    session records would inherit that.
    """
    if frame is None:
        return Result('field centre (tag 1)', BLOCKED,
                      'the aprilcam stream is dead -- the daemon needs a '
                      'Terminal launch for the camera grant; it will not '
                      'start from an agent process tree')
    seen = frame.get(tag)
    if seen is None:
        return Result('field centre (tag 1)', BLOCKED,
                      f'tag {tag} is not in frame ({len(frame)} tag(s) were) '
                      f'-- check the lights first, then the camera')
    err = math.hypot(seen[1], seen[2])
    data = {'x_cm': seen[1], 'y_cm': seen[2], 'err_cm': err}
    if err <= tol_cm:
        return Result('field centre (tag 1)', PASS,
                      f'({seen[1]:+.2f}, {seen[2]:+.2f}) cm, '
                      f'{err:.2f} cm from the origin', data)
    return Result('field centre (tag 1)', FAIL,
                  f'({seen[1]:+.2f}, {seen[2]:+.2f}) cm is {err:.2f} cm from '
                  f'world (0, 0), over the {tol_cm:.1f} cm tolerance -- the '
                  f'world frame is wrong, so every pose below is too', data)


def check_robot_tag(cam, samples=8):
    """PASS iff this robot's REGISTERED tag gives a camera fix.

    The fix comes back as `(x_cm, y_cm, yaw_deg)` of the robot's centre
    of rotation, because the mount was registered from the calibration
    of record -- the daemon applies the lever, the parallax and the
    heading convention itself. Nothing here corrects any of that a
    second time.
    """
    fix = cam.fix(n=samples)
    if fix is None:
        if getattr(cam, 'err', None):
            return Result('robot tag registered', BLOCKED,
                          f'the camera stream died: {cam.err}')
        return Result('robot tag registered', BLOCKED,
                      f'tag {cam.tag} gave no fix in {samples} samples -- is '
                      f'the robot on the field, and lit?')
    return Result('robot tag registered', PASS,
                  f'tag {cam.tag} at ({fix[0]:+.2f}, {fix[1]:+.2f}) cm '
                  f'heading {registered_heading(fix):+.1f} deg',
                  {'fix': list(fix)})


def preflight_blocks(results) -> bool:
    """True if any pre-flight result is not a PASS -- the gate that
    stops a session before it arms a single move. A commanded move on a
    dark field, an unconfirmed carrier or a wrong world frame produces
    a number nobody can use and a robot nobody is watching."""
    return any(not r.ok for r in results)


# ------------------------------------------------- heading, used UNCHANGED

def registered_heading(fix) -> float:
    """The robot's heading [deg] from a REGISTERED tag fix, used
    **unchanged**.

    This function is deliberately a wrap and nothing else. A registered
    tag's reported yaw already IS the robot's heading: the daemon baked
    the fixed -90 deg front-edge convention plus the mount's sub-degree
    residual in at registration time
    (`camlink.mount_yaw_rad()`). Running it through
    `field.robot_heading_from_tag_yaw()` -- which is for a RAW,
    unregistered reading and is the ONE place that convention is added
    back -- adds the 90 a second time.

    That bug survives a pivot check, because a heading DELTA cancels a
    constant offset, and shows up only on absolute bearings: sprint 029
    ticket 007 found three pivots netting close to clean while all
    three drives came back +87/+91/+86 deg off
    (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`,
    "registered vs raw: who adds the 90"). `check_move_x()` below
    computes exactly that bearing error and `double_add_signature()`
    names the pattern, which is the whole point of check (b).
    """
    return wrap(fix[2])


def pose_from_cam_samples(samples, lever_cm=(0.0, 0.0)):
    """`(x_cm, y_cm, heading_deg)` averaged over `Cam.samples`-shaped
    4-tuples `(t, x_cm, y_cm, yaw_deg)`.

    Delegates to `field.pose_from_registered_samples()` -- the one
    owner of this averaging, and the one that documents why the +90 is
    not re-added -- converting only the degrees the `Cam` surface
    reports into the radians that function takes. `lever_cm` defaults
    to no lever because a registered mount already puts the daemon's
    report at the centre of rotation; pass the calibration file's
    `lever_cm` only for a robot whose entry still carries one.
    """
    return fieldlib.pose_from_registered_samples(
        [(math.radians(s[3]), s[1], s[2]) for s in samples], lever_cm)


def double_add_signature(bearing_err_deg, turn_err_deg=None, window=25.0):
    """The `+90 applied twice` signature, or `None`.

    A travel bearing that comes out ~90 deg off WHILE pivots look fine
    is that bug, not a mount problem. Both wrong is just wrong -- so a
    `turn_err_deg` outside `window` disqualifies the diagnosis rather
    than supporting it, and a bearing error that is not near +/-90
    disqualifies it outright.
    """
    off = abs(abs(wrap(bearing_err_deg)) - 90.0)
    if off > window:
        return None
    if turn_err_deg is not None and abs(turn_err_deg) > window:
        return None
    return (f'travel bearing is {bearing_err_deg:+.1f} deg off, i.e. ~90 deg, '
            f'while rotation looks fine -- that is the "+90 applied twice" '
            f'signature (a registered reading run through '
            f'robot_heading_from_tag_yaw()), NOT a mount problem. See '
            f'.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md.')


# ------------------------------------------------------------ the wire

def parse_status(line):
    """`status k=v k=v ...` as a dict; `{}` for any other line."""
    if not line.startswith('status '):
        return {}
    return dict(kv.split('=', 1) for kv in line.split()[1:] if '=' in kv)


def send_sequenced(link, line, tries=3, wait=3.0):
    """Send one sequenced v6 verb; return `(wire, ident, reply, seen)`.

    The id is allocated ONCE, by the consolidated `link.Sequencer` the
    `Link` owns, and every retry resends the identical string: a resend
    that took a fresh id presents as a numeric gap, and the firmware
    stalls the stream on a gap deliberately (`tools/link.py`). `reply`
    is the first `ack`/`nack`/`err` line carrying this id, or `None`.

    `_format`/`_seq` are `robotlink.Link`'s documented written-to
    surface (its own tests set and read them); this is the one place
    this program touches them, so that the id it reports in the capture
    file is the id that actually went out.
    """
    wire = link._format(line)
    ident = link._seq
    seen = []
    for _ in range(tries):
        link.send(wire)
        for reply in link.lines(wait):
            seen.append(reply)
            head = reply.split(' ', 2)[:2]
            if len(head) == 2 and head[0] in ('ack', 'nack', 'err') \
                    and head[1] == str(ident):
                return wire, ident, reply, seen
    return wire, ident, None, seen


def wait_done(link, ident, timeout=15.0, wait=1.0, sleep=time.sleep):
    """Poll `STATUS` until it reports `done=<ident>`; return the last
    status dict seen (`{}` if none was).

    A completion poll, not a guessed sleep: a fixed sleep either wastes
    the session's time or reads the camera while the robot is still
    moving, and both have produced numbers on this rig that nobody
    could use.
    """
    end = time.time() + timeout
    status = {}
    while time.time() < end:
        link.send('STATUS')
        for line in link.lines(wait):
            got = parse_status(line)
            if got:
                status = got
                break
        if status.get('done') == str(ident):
            return status
        sleep(0.3)
    return status


# ------------------------------------------------------- the three checks

def projected_end(pose, dist_cm):
    """`(x, y)` a straight `dist_cm` ahead of `pose`, along its
    heading -- the endpoint the pre-flight path check needs, computed
    from a MEASURED pose and never from an assumed one."""
    h = math.radians(registered_heading(pose))
    return pose[0] + dist_cm * math.cos(h), pose[1] + dist_cm * math.sin(h)


def check_move_x(link, cam, dist_mm=100, cruise=0, timeout_ms=8000,
                 min_travel_cm=5.0, settle_s=1.2, samples=8,
                 tries=3, wait=3.0, done_timeout=15.0, done_wait=1.0,
                 sleep=time.sleep):
    """Check (a): a `MOVE_X` through the consolidated `Link` is
    acknowledged AND the robot moves, confirmed by the camera.

    The order is the whole check. A measured start pose from the
    camera; the full projected path checked against the field margin
    before a single byte goes out; the command sent once with its
    sequence id attached by the shared `Sequencer`; the ack matched by
    id; the completion polled; then the displacement scored from the
    CAMERA.

    `min_travel_cm` is what makes this different from reading an ack.
    A robot that is switched off answers `PING`, answers `STATUS` with
    a perfectly healthy `ready=1 connL=1 connR=1`, acks the move and
    reports the full commanded distance in its own odometry, while the
    camera holds its tag within a fraction of a millimetre -- MEASURED
    tovez 2026-08-26, `.claude/rules/playfield-testing.md` ("The robot
    is OFF -- check this first"). Only an external instrument can tell
    those apart, so a short travel is reported as exactly that case.

    `MOVE_X` arguments are integers on the wire; they are coerced here
    rather than trusted from the caller.
    """
    start = cam.fix(n=samples)
    if start is None:
        return Result('MOVE_X moves the robot', BLOCKED,
                      'no camera fix for the START pose -- a commanded move '
                      'from an assumed pose is exactly what the pre-flight '
                      'path check exists to prevent')
    dist_cm = dist_mm / 10.0
    end_xy = projected_end(start, dist_cm)
    try:
        require_clear_path([(start[0], start[1]), end_xy],
                           what=f'MOVE_X {int(dist_mm)} mm probe')
    except PathRefused as e:
        return Result('MOVE_X moves the robot', BLOCKED, str(e))

    wire, ident, reply, seen = send_sequenced(
        link, f'MOVE_X {int(dist_mm)} 0 {int(cruise)} {int(timeout_ms)}',
        tries=tries, wait=wait)
    data = {'wire': wire, 'id': ident, 'reply': reply,
            'start': list(start), 'lines': seen}
    if reply is None:
        return Result('MOVE_X moves the robot', FAIL,
                      f'sent {wire!r} and got no ack/nack/err for id {ident} '
                      f'in {tries} tries -- the consolidated Link attached '
                      f'the id, the robot never answered it', data)
    if not reply.startswith('ack'):
        return Result('MOVE_X moves the robot', FAIL,
                      f'sent {wire!r} and the robot answered {reply!r} -- the '
                      f'command was refused, not executed', data)

    wait_done(link, ident, timeout=done_timeout, wait=done_wait, sleep=sleep)
    sleep(settle_s)
    finish = cam.fix(n=samples)
    if finish is None:
        return Result('MOVE_X moves the robot', BLOCKED,
                      f'acked {reply!r} but the camera lost the robot before '
                      f'the END pose -- travel UNVERIFIED', data)

    travel = fieldlib.registered_pose_distance(start, finish)
    bearing = math.degrees(math.atan2(finish[1] - start[1],
                                      finish[0] - start[0]))
    bearing_err = wrap(bearing - registered_heading(start))
    data.update({'finish': list(finish), 'travel_cm': travel,
                 'commanded_cm': dist_cm, 'bearing_deg': bearing,
                 'bearing_err_deg': bearing_err})
    if travel < min_travel_cm:
        return Result('MOVE_X moves the robot', FAIL,
                      f'{reply} for {wire!r}, but the CAMERA saw only '
                      f'{travel:.2f} cm of travel against a commanded '
                      f'{dist_cm:.1f} cm (floor {min_travel_cm:.1f} cm). The '
                      f'robot did not move: it is switched off, stalled, or '
                      f'up on the bench stand. Odometry cannot detect its own '
                      f'failure to move, and a healthy STATUS proves nothing '
                      f'about motor power '
                      f'(.claude/rules/playfield-testing.md).', data)
    note = double_add_signature(bearing_err)
    detail = (f'{reply} for {wire!r}; camera saw {travel:.2f} cm against a '
              f'commanded {dist_cm:.1f} cm, bearing {bearing_err:+.1f} deg '
              f'off the measured heading')
    if note:
        return Result('MOVE_X moves the robot', FAIL,
                      f'{detail}. {note}', data)
    return Result('MOVE_X moves the robot', PASS, detail, data)


def check_pose_ground_truth(pose, dot, tol_cm=5.0, dots=None):
    """Check (b): the camera's pose for a robot parked on a known dot,
    against that dot's ground truth, using the REGISTERED mount.

    Pure: it takes the pose the camera measured, so the comparison is
    testable with no daemon. `dot` names one of `field.DOTS` -- the
    four orange dots are the field's own ground truth, and the pose
    passed in must come from a registered tag (see
    `registered_heading()` for why nothing is corrected on top).
    """
    table = fieldlib.DOTS if dots is None else dots
    truth = table.get(dot)
    if truth is None:
        return Result('pose vs ground truth', BLOCKED,
                      f'{dot!r} is not a known dot -- known: '
                      f'{sorted(table)}')
    err = math.hypot(pose[0] - truth[0], pose[1] - truth[1])
    data = {'dot': dot, 'truth': list(truth), 'pose': list(pose),
            'err_cm': err, 'heading_deg': registered_heading(pose)}
    detail = (f'{dot} truth ({truth[0]:+.1f}, {truth[1]:+.1f}) vs camera '
              f'({pose[0]:+.2f}, {pose[1]:+.2f}) = {err:.2f} cm, heading '
              f'{registered_heading(pose):+.1f} deg (registered, used '
              f'unchanged)')
    if err <= tol_cm:
        return Result('pose vs ground truth', PASS, detail, data)
    return Result('pose vs ground truth', FAIL,
                  f'{detail} -- over the {tol_cm:.1f} cm tolerance', data)


def default_out_of_bounds_target(margin_cm=10.0):
    """A target deliberately outside the usable field: `margin_cm`
    beyond the x half-extent `field.usable_half_extent()` derives.
    Derived, never a literal, so it cannot drift away from the geofence
    it is meant to trip."""
    hx, _hy = fieldlib.usable_half_extent()
    return hx + margin_cm, 0.0


def nearest_dot(pose, dots=None):
    """`(name, (x, y))` of the dot nearest `pose` -- the legitimate,
    in-bounds target the geofence must NOT refuse. The dots sit well
    inside the usable half-extent, and a straight leg between two
    points inside a convex rectangle stays inside it."""
    table = fieldlib.DOTS if dots is None else dots
    name = min(table, key=lambda k: math.hypot(pose[0] - table[k][0],
                                               pose[1] - table[k][1]))
    return name, table[name]


def check_geofence(link, cam, heading=0.0, out_target=None, in_target=None,
                   drive=False):
    """Check (c): a real out-of-bounds `Repositioner.go()` is refused
    with nothing sent, and a legitimate in-bounds target is not.

    Both halves matter and the second is the one that is easy to lose:
    a geofence that refuses everything passes the first half and makes
    the field unusable. `link` must be a `RecordingLink`, because the
    assertion is on what the WIRE received -- a refusal that has
    already sent the seed has still changed the robot's world frame,
    and a return value cannot show that (`tests/tools/test_reposition.py`
    makes the same argument).

    `drive=True` runs the in-bounds leg for real; the default checks it
    through `Repositioner.check_path()`, the same gate `go()` runs
    before its first byte, without committing the field to a move.
    """
    pose = cam.fix()
    if pose is None:
        return Result('geofence refuses/permits', BLOCKED,
                      'no camera fix -- the geofence is checked from a '
                      'MEASURED pose, never an assumed one')
    out_target = out_target or default_out_of_bounds_target()
    dot_name, dot_xy = nearest_dot(pose)
    in_target = in_target or dot_xy
    rep = Repositioner(link, cam)

    before = list(link.sent)
    try:
        rep.go(out_target[0], out_target[1], heading, echo=False)
    except PathRefused as refusal:
        refused = str(refusal)
    else:
        return Result('geofence refuses/permits', FAIL,
                      f'the out-of-bounds target {out_target} was NOT '
                      f'refused -- the geofence is not in the path',
                      {'sent': link.sent[len(before):]})
    if link.sent != before:
        return Result('geofence refuses/permits', FAIL,
                      f'refused ({refused[:120]}...) but {len(link.sent) - len(before)} '
                      f'line(s) had already gone out: '
                      f'{link.sent[len(before):]} -- a refusal after the seed '
                      f'has still changed the robot',
                      {'sent': link.sent[len(before):]})

    try:
        rep.check_path(pose, in_target[0], in_target[1])
        if drive:
            rep.go(in_target[0], in_target[1], heading, echo=False)
    except PathRefused as refusal:
        return Result('geofence refuses/permits', FAIL,
                      f'the LEGITIMATE in-bounds target {dot_name} '
                      f'{in_target} was refused: {refusal}', {})
    return Result('geofence refuses/permits', PASS,
                  f'refused ({out_target[0]:.1f}, {out_target[1]:.1f}) with '
                  f'nothing sent, and permitted the in-bounds {dot_name} dot '
                  f'({in_target[0]:.1f}, {in_target[1]:.1f})'
                  + (' (driven)' if drive else ' (path-checked)'),
                  {'out_target': list(out_target), 'in_dot': dot_name,
                   'in_target': list(in_target), 'refusal': refused})


# ------------------------------------------------------------ carriers

class DaemonPort(robotlink.WifiSerial):
    """`robotlink.WifiSerial` pointed at an explicit `host:port`.

    An on-robot Pi's `_mbserial._tcp` serial daemon lives on a dynamic
    port, not `WifiSerial`'s fixed 7654, and it needs no mDNS name
    resolution -- but `write()`/`readline()`/`close()` are byte-for-byte
    the same TCP line pipe. So this subclasses rather than copies, and
    deliberately does not call `super().__init__()`: the ONLY thing that
    differs is how the address is arrived at. (Do not SSH to the robot
    Pis; mDNS plus the advertised port is the documented route --
    `.claude/rules/connecting-to-a-robot.md`.)
    """

    def __init__(self, host, port, timeout=0.3):
        self.host = host
        self.s = socket.create_connection((host, int(port)), timeout=10)
        self.s.settimeout(timeout)
        self._buf = b''
        self._socket = socket


class RecordingLink:
    """Any link, plus a log of every line sent.

    Two things need it, and neither is decoration. The geofence check
    asserts that a refused move sent NOTHING, which is a statement
    about the wire and not about a return value; and the capture file
    has to name the command lines that produced each reading, or the
    MEASURED citation it backs cannot be re-run
    (`.claude/rules/measurement-citations.md`).

    It forwards the surface this program and `Repositioner` use, plus
    `robotlink.Link`'s `_format`/`_seq` so `send_sequenced()` can
    report the id that actually went out.
    """

    def __init__(self, inner):
        self.inner = inner
        self.sent = []

    def send(self, line, *args, **kwargs):
        self.sent.append(line)
        return self.inner.send(line, *args, **kwargs)

    def lines(self, timeout, until=None):
        return self.inner.lines(timeout, until)

    def hello(self, *args, **kwargs):
        return self.inner.hello(*args, **kwargs)

    def close(self):
        return self.inner.close()

    def _format(self, line):
        return self.inner._format(line)

    @property
    def _seq(self):
        return self.inner._seq


def carrier_spec(args):
    """`(kind, target, description)` for the chosen carrier -- pure, so
    `--dry-run` can print it without opening anything.

    WiFi TCP is the default (`.claude/rules/connecting-to-a-robot.md`),
    with the caveat the field has measured repeatedly: WiFi drops once
    the motors have been working, so a session with sustained motion
    should prefer `--radio` or `--serial`.
    """
    if args.radio:
        return ('radio', args.robot,
                f'radio relay, address resolved for {args.robot!r} '
                f'(robotlink.open_link(radio=True))')
    if args.serial:
        return ('serial', args.serial, f'Pi serial daemon {args.serial}')
    target = args.robot if args.wifi_tcp in (None, _SELF) else args.wifi_tcp
    return ('wifi-tcp', target,
            f'WiFi TCP {target}:{wifilink.ROBOT_PORT} (the default carrier)')


def open_carrier(args):
    """Open the chosen carrier and return `(RecordingLink, description)`.

    Every path ends with exactly one `HELLO` -- a script that connects
    without it inherits the robot's `expectedNext_` while sending ids
    from 1, so every command classifies as a stale retransmit and is
    dropped in silence: `ack: None`, no motion, a perfectly healthy
    `STATUS` (`tests/calibration/DESIGN.md`, 2026-09-05, cost a run).
    `robotlink.open_link()` does it for the WiFi and radio paths; the
    serial-daemon path does it here.
    """
    kind, target, desc = carrier_spec(args)
    if kind == 'radio':
        return RecordingLink(robotlink.open_link(radio=True,
                                                 robot=args.robot)), desc
    if kind == 'serial':
        host, _, port = target.partition(':')
        if not port:
            raise SystemExit(f'--serial wants HOST:PORT, got {target!r}')
        link = robotlink.Link(DaemonPort(host, port), radio=False)
        link.hello()
        return RecordingLink(link), desc
    return RecordingLink(robotlink.open_link(wifi=target)), desc


def robot_tag(robot, calibration=None):
    """`robot`'s tag number from the calibration of record.

    `field_calibration.json` is the one authority for tag mounts
    (TL-02); a tag guessed from a table in a script is how the fleet
    ended up with two disagreeing ones."""
    cal = calibration if calibration is not None else camlink.load_calibration()
    entry = cal.get('robots', {}).get(robot)
    if entry is None or 'tag_number' not in entry:
        raise SystemExit(
            f'no tag_number for {robot!r} in {camlink.CALIBRATION_PATH} -- '
            f'known robots: {sorted(cal.get("robots", {}))}. Run '
            f'`calibrate.py mount --robot {robot} ... --write` first, or '
            f'pass --tag.')
    return int(entry['tag_number'])


def open_camera(args, tag, client=None):
    """The in-process `Cam` following `tag`, registered first from the
    calibration of record unless `--no-register` says the operator has
    already done it.

    Registration is explicit and idempotent: `Cam.register()`
    overwrites the daemon's stored entry rather than compounding, and
    constructing a `Cam` never registers anything (TL-02 -- the old
    unconditional registration silently overwrote fresh remounts).
    """
    if not args.no_register:
        camlink.Cam.register(args.robot, client=client)
    return camlink.Cam(tag=tag, cam=args.camera, client=client)


# ------------------------------------------------------------- capture

def default_capture_dir(robot, today=None):
    """`captures/consolidation-acceptance-<robot>-<YYYYMMDD>` -- the
    directory this run's artifact goes in. `captures/` is gitignored,
    so committing it needs `git add -f`; the run prints that."""
    stamp = today or time.strftime('%Y%m%d')
    return f'captures/consolidation-acceptance-{robot}-{stamp}'


CAPTURE_REMINDER = (
    'captures/ is GITIGNORED. Commit this artifact with `git add -f '
    '<path>` or the MEASURED citation that names it points at nothing '
    '(.claude/rules/measurement-citations.md).')


def notes_text(header, results, sent, now=None):
    """The markdown one run appends to `notes.md`.

    `header` is a dict of session facts (board, date, carrier, command
    line); `results` the `Result` list; `sent` every line that went out.
    Everything a later reader needs to judge the numbers is in here,
    because a capture file that records only the numbers cannot be
    argued with.
    """
    stamp = now or time.strftime('%Y-%m-%d %H:%M:%S')
    out = [f'## {stamp}', '']
    for key in sorted(header):
        out.append(f'- **{key}**: {header[key]}')
    out += ['', '### Results', '',
            '| check | status | detail |', '| --- | --- | --- |']
    for r in results:
        out.append(f'| {r.name} | {r.status} | {r.detail} |')
    out += ['', '### Measurements', '', '```json',
            json.dumps({r.name: r.data for r in results}, indent=2,
                       default=str),
            '```', '', '### Command lines sent', '', '```']
    out += list(sent) or ['(nothing was sent)']
    out += ['```', '', f'> {CAPTURE_REMINDER}', '']
    return '\n'.join(out)


def write_notes(path, header, results, sent, now=None):
    """Append this run to `<capture-dir>/notes.md`, creating it.

    Append, never overwrite: a bench session is several runs, and the
    one that gets overwritten is always the one that recorded the
    failure.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as fh:
        fh.write(notes_text(header, results, sent, now=now))
    return path


# ------------------------------------------------------------- the plan

def plan_lines(args):
    """Every step this run would take, in order -- what `--dry-run`
    prints. Pure: it opens no carrier, no camera and no socket."""
    kind, target, desc = carrier_spec(args)
    capture = args.capture_dir or default_capture_dir(args.robot)
    out_target = default_out_of_bounds_target()
    tag = args.tag or '(this robot\'s, from field_calibration.json)'
    registration = ('no (--no-register)' if args.no_register else
                    f'Cam.register({args.robot!r}) from the calibration '
                    f'of record')
    return [
        f'PLAN for {args.robot} (dry run -- nothing is opened, nothing is '
        f'sent)',
        f'  carrier      {kind}: {desc}',
        f'  camera       {args.camera}, tag {tag}',
        f'  register     {registration}',
        f'  capture      {capture}/notes.md',
        '',
        '  pre-flight (a non-PASS stops the run before any motion):',
        f'    GET  {SHELLY_STATUS_URL}   -> output must be true',
        '    send PING                                  -> pong',
        f'    camera frame                               -> tag '
        f'{FIELD_CENTRE_TAG} within {FIELD_CENTRE_TOL_CM:.1f} cm of (0, 0)',
        '    camera fix                                 -> this robot, '
        'registered',
        '',
        '  check (a) MOVE_X through the consolidated Link:',
        f'    send MOVE_X {int(args.move_mm)} 0 0 {int(args.move_timeout_ms)} '
        f'#<id>   (id attached by link.Sequencer)',
        '    send STATUS (polled)                       -> done=<id>',
        f'    camera must show >= {args.min_travel_cm:.1f} cm of travel; '
        f'odometry alone never confirms it',
        '    NOTE the probe drives along the robot\'s CURRENT measured '
        'heading -- face it',
        '    toward the field centre first, or the path check refuses it '
        '(correctly).',
        '',
        f'  check (b) camera pose on the {args.dot} dot vs ground truth '
        f'{fieldlib.DOTS.get(args.dot)}:',
        f'    tolerance {args.dot_tol_cm:.1f} cm; the registered heading is '
        f'used UNCHANGED (no +90 on top)',
        '',
        '  check (c) geofence:',
        f'    Repositioner.go({out_target[0]:.1f}, {out_target[1]:.1f}, ...) '
        f'must raise PathRefused with NOTHING sent',
        '    then the nearest in-bounds dot must NOT be refused',
        '',
        '  run separately, once, on the same session:',
        f'    uv run python tools/wire_acceptance.py --wifi-tcp {target}',
        '',
        f'  {CAPTURE_REMINDER}',
    ]


# ------------------------------------------------------------- the run

def run_session(args, open_link=None, open_cam=None, get_json=None):
    """The scripted session: pre-flight, then the three checks, then
    the capture file. Returns `(exit_code, results)`.

    The collaborators are injectable so the session can be exercised
    without a robot; on the field they default to the real ones.
    """
    open_link = open_link or open_carrier
    open_cam = open_cam or open_camera
    capture = pathlib.Path(args.capture_dir
                           or default_capture_dir(args.robot))
    tag = args.tag or robot_tag(args.robot)

    results = [check_lights(get_json)]
    link, desc = None, carrier_spec(args)[2]
    cam = None
    try:
        if results[0].ok:
            link, desc = open_link(args)
            results.append(check_ping(link))
            cam = open_cam(args, tag)
            results.append(check_field_centre(one_frame(cam),
                                              tol_cm=args.centre_tol_cm))
            results.append(check_robot_tag(cam))
        preflight = list(results)

        if preflight_blocks(preflight):
            reason = next(r.name for r in preflight if not r.ok)
            for name in ('MOVE_X moves the robot', 'pose vs ground truth',
                         'geofence refuses/permits'):
                results.append(Result(
                    name, BLOCKED,
                    f'not run: pre-flight {reason!r} did not pass. Nothing '
                    f'is commanded from an unconfirmed bench.'))
        else:
            results.append(check_move_x(
                link, cam, dist_mm=args.move_mm,
                timeout_ms=args.move_timeout_ms,
                min_travel_cm=args.min_travel_cm))
            pose = cam.fix()
            if pose is None:
                results.append(Result('pose vs ground truth', BLOCKED,
                                      'no camera fix after the move'))
            else:
                results.append(check_pose_ground_truth(
                    pose, args.dot, tol_cm=args.dot_tol_cm))
            results.append(check_geofence(link, cam, drive=args.drive_in_bounds))
    finally:
        if cam is not None:
            cam.close()
        if link is not None:
            link.close()

    header = {
        'board': args.robot,
        'date': time.strftime('%Y-%m-%d'),
        'carrier': desc,
        'camera': f'{args.camera}, tag {tag}',
        'program': 'tests/calibration/consolidation_acceptance.py',
        'command': ' '.join(sys.argv),
        'dot': args.dot,
    }
    path = write_notes(capture / 'notes.md', header, results,
                       link.sent if link is not None else [])

    print()
    for r in results:
        print(r.line())
    print()
    print(f'captured to {path}')
    print(CAPTURE_REMINDER)
    failed = [r.name for r in results if r.status == FAIL]
    blocked = [r.name for r in results if r.status == BLOCKED]
    if failed:
        print('FAILED: ' + ', '.join(failed))
        return 1, results
    if blocked:
        print('BLOCKED (nothing failed, but these were not measured -- '
              'record them as UNVERIFIED): ' + ', '.join(blocked))
        return 2, results
    print('ALL CHECKS PASSED.')
    return 0, results


def build_parser():
    ap = argparse.ArgumentParser(
        prog='consolidation_acceptance', description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('robot', help='board name assigned for THIS session by '
                                  'the stakeholder (there is no standing '
                                  'ownership table)')
    carrier = ap.add_mutually_exclusive_group()
    carrier.add_argument('--wifi-tcp', metavar='NAME|IP', nargs='?',
                         const=_SELF, default=None,
                         help='WiFi TCP carrier (the default); an optional '
                              'NAME|IP overrides the robot name')
    carrier.add_argument('--radio', action='store_true',
                         help='the radio relay pool -- prefer this over WiFi '
                              'for sustained motion')
    carrier.add_argument('--serial', metavar='HOST:PORT',
                         help="an on-robot Pi's serial daemon")
    ap.add_argument('--camera', default=camlink.CAM,
                    help='camera name the aprilcam daemon serves (the daemon '
                         'itself is found by aprilcam Discovery)')
    ap.add_argument('--tag', type=int, default=None,
                    help='tag number (default: this robot\'s, from '
                         'field_calibration.json)')
    ap.add_argument('--no-register', action='store_true',
                    help='do not register the mount -- only when it has '
                         'already been registered this session')
    ap.add_argument('--dot', default='NE', choices=sorted(fieldlib.DOTS),
                    help='the known dot the robot is parked on for check (b)')
    ap.add_argument('--dot-tol-cm', type=float, default=5.0)
    ap.add_argument('--centre-tol-cm', type=float,
                    default=FIELD_CENTRE_TOL_CM)
    ap.add_argument('--move-mm', type=int, default=100,
                    help='the MOVE_X probe distance [mm]')
    ap.add_argument('--move-timeout-ms', type=int, default=8000)
    ap.add_argument('--min-travel-cm', type=float, default=5.0,
                    help='camera-measured floor below which the move is '
                         'reported as "the robot did not move"')
    ap.add_argument('--drive-in-bounds', action='store_true',
                    help="check (c)'s in-bounds half drives for real rather "
                         'than path-checking it')
    ap.add_argument('--capture-dir', default=None,
                    help='default: captures/consolidation-acceptance-'
                         '<robot>-<date>/')
    ap.add_argument('--dry-run', action='store_true',
                    help='print the plan and exit; opens no carrier, no '
                         'camera and no socket')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.dry_run:
        for line in plan_lines(args):
            print(line)
        return 0
    code, _results = run_session(args)
    return code


if __name__ == '__main__':
    sys.exit(main())
