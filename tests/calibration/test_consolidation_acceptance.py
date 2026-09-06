"""tests/calibration/test_consolidation_acceptance.py -- the host-side
half of sprint 034 ticket 013.

The ticket's own Testing section: "the script's argument parsing, its
pre-flight checks and its refusal paths are unit-testable with an
injected fake link and fake camera, and **should be**, before it ever
sees a robot." This is that, and nothing in this file touches a robot,
a relay, the Shelly or an aprilcam daemon -- so **nothing here is a
MEASURED claim about hardware** (`.claude/rules/measurement-citations.md`).
What the program measures on the field goes into its capture file; what
is pinned here is that it asks the right questions and refuses in the
right places.

Two conventions carried from the existing suites rather than invented:

* the link double is the REAL `robotlink.Link` wrapped around a
  `FakePort` (`tests/tools/test_robotlink.py`'s pattern), not a
  hand-written stand-in. The point of check (a) is that the
  consolidated `link.Sequencer` attaches the id, so a fake that
  attached its own would test nothing;
* the refusal tests assert on **what the link received**, never on a
  return value -- `tests/tools/test_reposition.py` makes the argument:
  a refusal that has already sent the seed has still changed the robot.

This is the second `test_`-prefixed file under `tests/calibration/`
(after `test_turn_calibration_gates.py`) and, like it, is pure host
logic that the ordinary suite collects while the program around it
stays a person's tool -- see `tests/DESIGN.md`.

Run with::

    uv run pytest tests/calibration/test_consolidation_acceptance.py -q
"""
import ast
import math
import pathlib
import re
import sys

import pytest

# tests/calibration/... -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_TOOLS_DIR), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import consolidation_acceptance as ca  # noqa: E402  (path first)
import field as fieldlib  # noqa: E402
import robotlink  # noqa: E402


class FakePort:
    """A serial-port double for `robotlink.Link.p`: `write()` logs,
    `readline()` hands back canned raw lines once each and then `b''`
    forever ("nothing ready yet"). Same shape as
    `tests/tools/test_robotlink.py`'s."""

    def __init__(self, incoming=()):
        self.writes = []
        self._incoming = [line.encode() + b'\n' for line in incoming]

    def write(self, data):
        self.writes.append(data)

    def readline(self):
        if self._incoming:
            return self._incoming.pop(0)
        return b''

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


class FakeCam:
    """Scripted camera fixes. `fix()` walks `poses`, holding on the
    last; a `None` in the list is the camera losing the robot."""

    def __init__(self, *poses, tag=52, err=None):
        self._poses = list(poses) or [None]
        self.tag = tag
        self.err = err
        self.notag = 0
        self.closed = False

    def fix(self, n=8, stale_after=40):
        if len(self._poses) > 1:
            return self._poses.pop(0)
        return self._poses[0]

    def close(self):
        self.closed = True


def _link(replies=()):
    """A RecordingLink around a REAL `robotlink.Link` over a FakePort."""
    port = FakePort(replies)
    return ca.RecordingLink(robotlink.Link(port, radio=False)), port


def _args(*argv):
    return ca.build_parser().parse_args(list(argv))


# --------------------------------------------------------------- lights

def test_lights_pass_when_the_shelly_says_output_true():
    got = ca.check_lights(lambda _url: {'output': True})
    assert got.status == ca.PASS


def test_lights_blocked_when_the_field_is_dark():
    """The single most-repeated misdiagnosis on this rig: a dark field
    looks exactly like a broken camera. It must come back BLOCKED (a
    bench condition), never FAIL (a finding about the code)."""
    got = ca.check_lights(lambda _url: {'output': False})
    assert got.status == ca.BLOCKED
    assert 'DARK' in got.detail
    assert 'Switch.Set' in got.detail, 'the remedy must be in the message'


def test_lights_blocked_when_the_shelly_does_not_answer():
    def boom(_url):
        raise OSError('no route to host')
    got = ca.check_lights(boom)
    assert got.status == ca.BLOCKED


def test_lights_blocked_when_the_reply_has_no_output_key():
    got = ca.check_lights(lambda _url: {'src': 'shelly'})
    assert got.status == ca.BLOCKED


# ---------------------------------------------------------- field centre

def test_field_centre_blocked_when_tag_1_is_not_visible():
    got = ca.check_field_centre({53: (0.0, 10.0, 10.0)})
    assert got.status == ca.BLOCKED
    assert 'not in frame' in got.detail


def test_field_centre_blocked_when_the_stream_is_dead():
    """A dead instrument is a different answer from an invisible tag,
    and `one_frame()` returns None for it."""
    got = ca.check_field_centre(None)
    assert got.status == ca.BLOCKED
    assert 'stream is dead' in got.detail


def test_field_centre_passes_at_the_origin():
    got = ca.check_field_centre({1: (0.0, 0.4, -0.5)})
    assert got.status == ca.PASS


def test_field_centre_fails_when_the_world_frame_is_off():
    got = ca.check_field_centre({1: (0.0, 9.0, 0.0)})
    assert got.status == ca.FAIL


# --------------------------------------------------------------- PING

def test_ping_passes_on_a_pong():
    link, _port = _link(['pong 51487'])
    assert ca.check_ping(link, wait=0.05, tries=1).status == ca.PASS


def test_ping_fails_when_nothing_answers():
    link, _port = _link([])
    got = ca.check_ping(link, wait=0.02, tries=1)
    assert got.status == ca.FAIL


def test_ping_is_sent_bare_never_with_an_id():
    """`PING` is unsequenced (`.claude/rules/playfield-testing.md`); a
    verb given an id the robot does not sequence burns the id and
    stalls the stream."""
    link, port = _link(['pong 1'])
    ca.check_ping(link, wait=0.05, tries=1)
    assert port.writes == [b'PING\n']


# --------------------------------------------------- check (a): MOVE_X

def test_move_x_line_carries_a_sequence_id():
    """The consolidated `Sequencer` attaches it -- an unsequenced line
    parses as #0 on the robot and is dropped in silence."""
    link, port = _link(['ack 1 0 none', 'status ready=1 done=1'])
    ca.check_move_x(link, FakeCam((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
                    dist_mm=100, wait=0.05, tries=1, done_wait=0.05,
                    done_timeout=1.0, settle_s=0.0, sleep=lambda _s: None)
    sent = [w.decode().strip() for w in port.writes]
    assert sent[0] == 'MOVE_X 100 0 0 8000 #1', sent


def test_move_x_passes_when_the_camera_confirms_travel():
    link, _port = _link(['ack 1 0 none', 'status ready=1 done=1'])
    got = ca.check_move_x(link, FakeCam((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
                          dist_mm=100, wait=0.05, tries=1, done_wait=0.05,
                          done_timeout=1.0, settle_s=0.0,
                          sleep=lambda _s: None)
    assert got.status == ca.PASS, got.detail
    assert got.data['travel_cm'] == pytest.approx(10.0)


def test_move_x_fails_when_the_camera_shows_no_displacement():
    """THE case this check exists for: acked, `STATUS` healthy, odometry
    would report the full commanded distance -- and the robot is
    switched off. Only an external instrument can tell."""
    link, _port = _link(['ack 1 0 none', 'status ready=1 done=1'])
    got = ca.check_move_x(link, FakeCam((0.0, 0.0, 0.0), (0.02, 0.0, 0.0)),
                          dist_mm=100, wait=0.05, tries=1, done_wait=0.05,
                          done_timeout=1.0, settle_s=0.0,
                          sleep=lambda _s: None)
    assert got.status == ca.FAIL
    assert 'switched off' in got.detail
    assert 'Odometry cannot detect its own failure to move' in got.detail


def test_move_x_fails_when_the_id_is_never_acked():
    link, _port = _link([])
    got = ca.check_move_x(link, FakeCam((0.0, 0.0, 0.0)), dist_mm=100,
                          wait=0.02, tries=1, done_wait=0.02,
                          done_timeout=0.05, settle_s=0.0,
                          sleep=lambda _s: None)
    assert got.status == ca.FAIL
    assert 'no ack/nack/err' in got.detail


def test_move_x_fails_on_a_nack_rather_than_calling_it_motion():
    link, _port = _link(['nack 1 0 gap'])
    got = ca.check_move_x(link, FakeCam((0.0, 0.0, 0.0)), dist_mm=100,
                          wait=0.05, tries=1, done_wait=0.02,
                          done_timeout=0.05, settle_s=0.0,
                          sleep=lambda _s: None)
    assert got.status == ca.FAIL
    assert 'refused, not executed' in got.detail


def test_move_x_blocked_and_silent_when_the_path_leaves_the_field():
    """The mandatory pre-flight path check, from a MEASURED start pose,
    ahead of the first byte -- not the geofence as an afterthought."""
    hx, _hy = fieldlib.usable_half_extent()
    link, port = _link(['ack 1 0 none'])
    got = ca.check_move_x(link, FakeCam((hx - 1.0, 0.0, 0.0)), dist_mm=300,
                          wait=0.05, tries=1, settle_s=0.0,
                          sleep=lambda _s: None)
    assert got.status == ca.BLOCKED
    assert 'REFUSING' in got.detail
    assert port.writes == [], 'nothing may go out after a refusal'


def test_move_x_blocked_without_a_measured_start_pose():
    link, port = _link(['ack 1 0 none'])
    got = ca.check_move_x(link, FakeCam(None), sleep=lambda _s: None)
    assert got.status == ca.BLOCKED
    assert port.writes == []


# ----------------------------------- check (b): the registered heading

def test_registered_heading_does_not_add_90():
    """A registered tag's yaw already IS the robot's heading. Adding
    the convention again passes every pivot check (deltas cancel a
    constant offset) and rotates every absolute bearing by 90 deg."""
    assert ca.registered_heading((0.0, 0.0, 37.0)) == pytest.approx(37.0)
    assert ca.registered_heading((0.0, 0.0, 37.0)) != pytest.approx(127.0)


def test_registered_heading_only_wraps():
    assert ca.registered_heading((0.0, 0.0, 200.0)) == pytest.approx(-160.0)
    assert ca.registered_heading((0.0, 0.0, 180.0)) == pytest.approx(180.0)


def test_the_program_never_calls_robot_heading_from_tag_yaw():
    """A source-level guard, because the double-add is a call that
    LOOKS right: `robot_heading_from_tag_yaw()` is for a RAW tag only,
    and everything this program reads is registered.

    Parsed, not grepped -- the module names the function repeatedly in
    prose, which is where the rule is explained and is exactly what a
    reader should find there."""
    tree = ast.parse((_HERE / 'consolidation_acceptance.py').read_text())
    calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
             and (getattr(n.func, 'attr', None) or getattr(n.func, 'id', None))
             == 'robot_heading_from_tag_yaw']
    assert calls == [], f'called at line(s) {calls}'
    imported = [a.name for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) for a in n.names]
    assert 'robot_heading_from_tag_yaw' not in imported


def test_pose_from_cam_samples_averages_without_adding_90():
    pose = ca.pose_from_cam_samples([(0.0, 10.0, 5.0, 90.0),
                                     (0.1, 10.0, 5.0, 90.0)])
    assert pose[0] == pytest.approx(10.0)
    assert pose[1] == pytest.approx(5.0)
    assert pose[2] == pytest.approx(90.0)


def test_double_add_signature_names_a_90_degree_bearing_error():
    note = ca.double_add_signature(88.0)
    assert note is not None
    assert '+90 applied twice' in note


def test_double_add_signature_is_silent_on_a_small_bearing_error():
    assert ca.double_add_signature(3.0) is None


def test_double_add_signature_is_silent_when_rotation_is_wrong_too():
    """Both wrong is just wrong -- the signature is specifically a
    ~90 deg bearing error WHILE pivots look fine."""
    assert ca.double_add_signature(90.0, turn_err_deg=60.0) is None


def test_pose_vs_ground_truth_passes_on_the_dot():
    got = ca.check_pose_ground_truth((50.4, 29.6, 180.0), 'NE')
    assert got.status == ca.PASS


def test_pose_vs_ground_truth_fails_off_the_dot():
    got = ca.check_pose_ground_truth((42.0, 30.0, 0.0), 'NE')
    assert got.status == ca.FAIL


def test_pose_vs_ground_truth_blocked_for_an_unknown_dot():
    got = ca.check_pose_ground_truth((0.0, 0.0, 0.0), 'MIDDLE')
    assert got.status == ca.BLOCKED


# ------------------------------------------------ check (c): the geofence

def test_geofence_refuses_the_out_of_bounds_target_and_sends_nothing():
    link, port = _link(['OCAL:seeded', 'GOTO:end', 'FACE:end'])
    got = ca.check_geofence(link, FakeCam((0.0, 0.0, 0.0)))
    assert got.status == ca.PASS, got.detail
    assert link.sent == [], link.sent
    assert port.writes == [], port.writes


def test_geofence_out_of_bounds_target_is_derived_from_the_field():
    """Derived from `field.usable_half_extent()`, so it cannot drift
    away from the gate it is meant to trip."""
    hx, _hy = fieldlib.usable_half_extent()
    assert ca.default_out_of_bounds_target()[0] > hx


def test_geofence_fails_if_the_out_of_bounds_target_is_permitted():
    """The failure mode the whole check exists for: nothing in the
    path. Simulated by handing it a target that IS in bounds."""
    link, _port = _link([])
    got = ca.check_geofence(link, FakeCam((0.0, 0.0, 0.0)),
                            out_target=(0.0, 0.0))
    assert got.status == ca.FAIL
    assert 'NOT refused' in got.detail


def test_geofence_accepts_a_legitimate_in_bounds_target():
    """A gate that refuses everything passes the first half and makes
    the field unusable, so the permissive half is pinned too."""
    link, _port = _link([])
    got = ca.check_geofence(link, FakeCam((45.0, 25.0, 0.0)))
    assert got.status == ca.PASS
    assert got.data['in_dot'] == 'NE'


def test_geofence_fails_when_a_legitimate_target_is_refused():
    link, _port = _link([])
    got = ca.check_geofence(link, FakeCam((0.0, 0.0, 0.0)),
                            in_target=(200.0, 0.0))
    assert got.status == ca.FAIL
    assert 'LEGITIMATE' in got.detail


def test_geofence_blocked_without_a_camera_fix():
    link, _port = _link([])
    got = ca.check_geofence(link, FakeCam(None))
    assert got.status == ca.BLOCKED
    assert link.sent == []


def test_nearest_dot_picks_the_nearest():
    assert ca.nearest_dot((-48.0, -28.0))[0] == 'SW'


# ------------------------------------------------------ the wire helpers

def test_send_sequenced_reuses_one_id_across_retries():
    """A resend that takes a fresh id presents as a numeric gap, and
    the firmware stalls the stream on a gap deliberately."""
    link, port = _link([])
    wire, ident, reply, _seen = ca.send_sequenced(link, 'MOVE_X 50 0 0 5000',
                                                  tries=3, wait=0.02)
    assert reply is None
    assert ident == 1
    assert wire == 'MOVE_X 50 0 0 5000 #1'
    assert [w.decode().strip() for w in port.writes] == [wire] * 3


def test_send_sequenced_ignores_an_ack_for_a_different_id():
    link, _port = _link(['ack 9 0 none'])
    _wire, ident, reply, _seen = ca.send_sequenced(link, 'MOVE_X 50 0 0 5000',
                                                   tries=1, wait=0.05)
    assert ident == 1
    assert reply is None


def test_parse_status_reads_a_status_line():
    got = ca.parse_status('status ready=1 connL=1 next=4 done=3 reason=none')
    assert got['done'] == '3'
    assert got['ready'] == '1'


def test_parse_status_ignores_anything_else():
    assert ca.parse_status('ack 3 0 none') == {}


def test_projected_end_uses_the_measured_heading():
    x, y = ca.projected_end((0.0, 0.0, 90.0), 10.0)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(10.0)


# --------------------------------------------- arguments and the dry run

def test_wifi_tcp_is_the_default_carrier():
    kind, target, _desc = ca.carrier_spec(_args('tovez'))
    assert kind == 'wifi-tcp'
    assert target == 'tovez'


def test_wifi_tcp_takes_an_optional_override():
    _kind, target, _desc = ca.carrier_spec(_args('tovez', '--wifi-tcp',
                                                 '192.168.1.196'))
    assert target == '192.168.1.196'


def test_radio_and_serial_carriers_are_selectable():
    assert ca.carrier_spec(_args('tovez', '--radio'))[0] == 'radio'
    kind, target, _d = ca.carrier_spec(_args('tovez', '--serial',
                                             'nada.local:9000'))
    assert (kind, target) == ('serial', 'nada.local:9000')


def test_carriers_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _args('tovez', '--radio', '--serial', 'h:1')


def test_robot_name_is_required():
    with pytest.raises(SystemExit):
        _args('--dry-run')


def test_default_capture_dir_names_the_board_and_the_date():
    assert (ca.default_capture_dir('tigez', today='20260906')
            == 'captures/consolidation-acceptance-tigez-20260906')


def test_dry_run_opens_nothing(monkeypatch):
    """`--dry-run` must reach neither a carrier, nor a camera, nor a
    socket -- it is what an operator reads before the robot is on the
    field."""
    def boom(*_a, **_kw):
        raise AssertionError('--dry-run opened something')

    monkeypatch.setattr(ca, 'open_carrier', boom)
    monkeypatch.setattr(ca, 'open_camera', boom)
    monkeypatch.setattr(ca, 'run_session', boom)
    monkeypatch.setattr(ca.socket, 'create_connection', boom)
    monkeypatch.setattr(ca.camlink.Cam, 'register', boom)
    assert ca.main(['tovez', '--dry-run']) == 0


def test_the_plan_names_every_command_that_would_go_out():
    text = '\n'.join(ca.plan_lines(_args('tovez', '--dry-run')))
    assert 'MOVE_X 100 0 0 8000' in text
    assert 'PING' in text
    assert 'PathRefused' in text
    assert 'wire_acceptance.py --wifi-tcp tovez' in text
    assert 'git add -f' in text


# ---------------------------------------------------------- the capture

def test_notes_carry_the_board_date_carrier_commands_and_readings(tmp_path):
    results = [ca.Result('MOVE_X moves the robot', ca.PASS, 'moved 10.02 cm',
                         {'travel_cm': 10.02})]
    path = ca.write_notes(tmp_path / 'notes.md',
                          {'board': 'tovez', 'date': '2026-09-06',
                           'carrier': 'WiFi TCP tovez:7654'},
                          results, ['MOVE_X 100 0 0 8000 #1'],
                          now='2026-09-06 11:00:00')
    text = path.read_text()
    assert 'tovez' in text
    assert '2026-09-06' in text
    assert 'WiFi TCP tovez:7654' in text
    assert 'MOVE_X 100 0 0 8000 #1' in text
    assert '10.02' in text


def test_notes_are_appended_never_overwritten(tmp_path):
    """A bench session is several runs, and the one that gets
    overwritten is always the one that recorded the failure."""
    path = tmp_path / 'sub' / 'notes.md'
    ca.write_notes(path, {'board': 'tovez'}, [], ['first'],
                   now='2026-09-06 11:00:00')
    ca.write_notes(path, {'board': 'tovez'}, [], ['second'],
                   now='2026-09-06 12:00:00')
    text = path.read_text()
    assert 'first' in text and 'second' in text


def test_notes_carry_the_gitignore_reminder(tmp_path):
    path = ca.write_notes(tmp_path / 'notes.md', {'board': 'tovez'}, [], [],
                          now='2026-09-06 11:00:00')
    assert 'git add -f' in path.read_text()


# ------------------------------------------------------ the pre-flight gate

def test_preflight_blocks_on_any_non_pass():
    assert ca.preflight_blocks([ca.Result('a', ca.PASS, ''),
                                ca.Result('b', ca.BLOCKED, '')])
    assert ca.preflight_blocks([ca.Result('a', ca.FAIL, '')])
    assert not ca.preflight_blocks([ca.Result('a', ca.PASS, '')])


def test_a_blocked_preflight_leaves_the_three_checks_unrun(monkeypatch):
    """Nothing is commanded from an unconfirmed bench: a dark field
    must stop the session before a carrier is opened at all."""
    def boom(*_a, **_kw):
        raise AssertionError('a check ran after a blocked pre-flight')

    monkeypatch.setattr(ca, 'check_move_x', boom)
    monkeypatch.setattr(ca, 'check_geofence', boom)
    args = _args('tovez', '--tag', '52', '--capture-dir', 'IGNORED')
    args.capture_dir = None
    code, results = ca.run_session(
        args, open_link=boom, open_cam=boom,
        get_json=lambda _url: {'output': False})
    assert code == 2
    names = {r.name: r.status for r in results}
    assert names['lights'] == ca.BLOCKED
    assert names['MOVE_X moves the robot'] == ca.BLOCKED
    assert names['geofence refuses/permits'] == ca.BLOCKED


def test_every_measured_claim_in_the_module_names_its_artifact():
    """This program produces the artifact a future MEASURED citation
    points at; it must not assert an unsourced one of its own
    (`.claude/rules/measurement-citations.md`: "if a comment, doc, or
    ticket asserts something was measured, it must name the artifact
    that backs it").

    A claim is `MEASURED <board> <date>`; the word used as an adjective
    ("a freshly MEASURED start pose") is not one. Each claim must name
    an artifact within the sentence that follows it."""
    src = (_HERE / 'consolidation_acceptance.py').read_text()
    artifacts = ('captures/', 'reports/', 'rules/', '.log', '.csv', '.json')
    unsourced = []
    for m in re.finditer(r'MEASURED[^\n]{0,40}\n?[^\n]{0,40}?'
                         r'\d{4}-\d{2}-\d{2}', src):
        window = src[m.start():m.start() + 400]
        if not any(a in window for a in artifacts):
            unsourced.append(window.splitlines()[0])
    assert unsourced == [], unsourced


def test_geometry_constants_come_from_field_not_a_local_copy():
    """Half the defects this sprint closed were a second copy of a
    constant. The field's limits, its margin and its dots have one
    owner."""
    src = (_HERE / 'consolidation_acceptance.py').read_text()
    assert '67.15' not in src and '44.65' not in src
    assert math.isclose(fieldlib.MARGIN, 12.0)
