"""Fast overhead-camera access: one persistent gRPC stream.

Runs under the venv that actually has the aprilcam package -- resolved
ONCE, in tools/camproc.py's resolve_venv() (the APRILTAGS_VENV env var,
defaulting to the pipx aprilcam venv). Every tools/*.py camera spawn
site goes through that single resolution point now; this file's own
imports below only work under that interpreter, whichever process
spawns it.

THE DAEMON DOES THE CORRECTING, AND IT REMEMBERS.
Tag mount registrations persist across a daemon restart -- they are
written to the daemon's mounts registry on disk and reload
automatically at daemon startup. Only an explicit unregister_tag call
removes one.

**Sprint 029 (TL-02): `field_calibration.json` is the one calibration
of record.** Constructing `Cam` never registers anything -- the old
`MOUNTS` table and `Cam.__init__`'s unconditional `ensure_registered()`
call used to overwrite the daemon's PERSISTENT registry with a stale
table on every single tool start, silently discarding a fresh remount
(the 2026-09-02 tag-53 remount was overwritten this way before this
fix). Registration is now `register()` (or `--register` from the CLI),
called explicitly, once, when a mount has actually changed. An
unregistered tag is reported RAW: no parallax, no lever arm, no mount
yaw. For vevov's tag that is 6.4 cm of parallax plus 3.6 cm of lever,
and it looks perfectly plausible -- it is a position on the field, just
the wrong one. Verified against ground truth 2026-08-23 with the robot
parked on the NE orange dot.

Units the daemon wants, all learned the hard way against that truth:
  mount_x / mount_y   CENTIMETRES (mm gives a 32 cm error)
  mount_z             centimetres, drives parallax
  mount_yaw_rad       tag heading relative to robot forward. A tag
                      mounted a quarter turn round (every robot tag in
                      this fleet so far) needs -pi/2.
With those set the daemon also corrects the REPORTED YAW, so yaw_rad is
the robot's heading directly -- no +90 fudge.

**The +90 deg (mount_yaw_rad = -pi/2) is a fixed AprilCam convention,
never a measured value** -- see
`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`. Only the
sub-degree residual (how square the plate itself sits) is physical;
`field_calibration.json` stores that residual alone
(`mount_yaw_residual_deg`), and `mount_yaw_rad()` below is the ONE place
the -90 deg convention is added back in.
"""
import argparse
import json
import math
import pathlib
import sys

from aprilcam.client.discovery import Discovery
from aprilcam.client import daemon_client as dc

CAM = 'arducam-ov9782-usb-camera'

_HERE = pathlib.Path(__file__).resolve().parent
CALIBRATION_PATH = _HERE / 'field_calibration.json'

_TAG_FAMILIES = {'apriltag': dc.TagFamily.APRILTAG}


def load_calibration(path=CALIBRATION_PATH):
    """`field_calibration.json`'s parsed content -- the one calibration
    of record for tag mounts (TL-02) and radio addresses (see
    `robotlink.radio_address()`)."""
    return json.loads(pathlib.Path(path).read_text())


def mount_yaw_rad(residual_deg):
    """Daemon-facing `mount_yaw_rad` for a ROBOT-mounted tag: the fixed
    -90 deg front-edge-to-hat AprilCam convention plus `residual_deg`,
    the only physical, measurable part
    (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`: "Only a
    sub-degree residual is physical"). The -90 deg is never itself read
    from configuration or re-derived -- it is applied here, exactly
    once. Field furniture (fixed calibration tags) has no forward
    direction and does not go through this function -- see
    `Cam.register()`."""
    return -math.pi / 2 + math.radians(residual_deg)


class CamDown(RuntimeError):
    """The daemon is gone -- distinct from a tag simply not being seen."""


class Cam:
    """Tag reader. `read` returns (yaw_deg, x_cm, y_cm) or None.

    Construction NEVER touches the daemon's mount registry -- see
    `register()` for the explicit, opt-in path that does (TL-02).
    `client` is an injected daemon client for tests; omitted, this
    connects for real via `Discovery().connect()`.
    """

    def __init__(self, cam=CAM, client=None):
        self.cam = cam
        if client is not None:
            self.d = client
        else:
            try:
                self.d = Discovery().connect()
            except Exception as e:
                raise CamDown(f'aprilcam daemon unreachable: {e}') from e
        self._stream = None

    def _register_one(self, number, family_name, mount_x, mount_y, mount_z,
                       yaw_rad):
        """The ONE call site of `register_tag()` in this file (both for
        a robot mount, via `register()`, and for field furniture)."""
        family = _TAG_FAMILIES[family_name]
        self.d.register_tag(
            dc.TagId(family=family, number=number),
            dc.MountParameters(size_cm=None, mount_x=mount_x, mount_y=mount_y,
                                mount_z=mount_z, mount_yaw_rad=yaw_rad))

    @classmethod
    def register(cls, target, calibration=None, client=None):
        """Register ONE robot's tag mount, or the fixed field
        furniture, with the aprilcam daemon -- the only path in this
        file that calls `register_tag()` (TL-02). Never called by
        `__init__`.

        `target` is a robot name (a key under `field_calibration.json`'s
        `robots`) or the literal string `'field'`, which registers
        every entry under that file's `field.tags` instead (the fixed
        ground-truth tags `--check` verifies against -- field furniture,
        not a robot, so no forward direction and no +90 deg convention
        applies; their yaw is registered as 0).

        Returns the `Cam` used, so a caller can keep reading afterward.
        Raises `SystemExit` (not a bare KeyError) naming the exact
        problem when `target`/its fields are missing -- this is an
        operator-facing CLI path.
        """
        cal = calibration if calibration is not None else load_calibration()
        cam = cls(client=client)
        if target == 'field':
            tags = cal.get('field', {}).get('tags', {})
            if not tags:
                raise SystemExit(
                    f"camlink: no field.tags entries in {CALIBRATION_PATH}")
            for num, spec in tags.items():
                cam._register_one(
                    int(num), spec.get('tag_family', 'apriltag'),
                    spec.get('mount_x_cm', 0.0), spec.get('mount_y_cm', 0.0),
                    spec['mount_z_cm'], 0.0)
            return cam
        entry = cal.get('robots', {}).get(target)
        if entry is None:
            known = sorted(cal.get('robots', {}))
            raise SystemExit(
                f"camlink: no robot {target!r} in {CALIBRATION_PATH} -- "
                f"known robots: {known}, or 'field' for the fixed "
                f"calibration tags")
        cam._register_one(
            entry['tag_number'], entry.get('tag_family', 'apriltag'),
            entry['mount_x_cm'], entry['mount_y_cm'], entry['mount_z_cm'],
            mount_yaw_rad(entry.get('mount_yaw_residual_deg', 0.0)))
        return cam

    def frames(self):
        """Yield {tag_number: (yaw_deg, x_cm, y_cm)} per camera frame.

        One yield per REAL frame, so there are no duplicate samples to
        confuse a duty-cycle or speed calculation -- polling faster than
        the camera used to make ~70% of samples repeats, and anything
        scoring per-sample motion then measured the camera's frame rate
        instead of the robot's.
        """
        try:
            for frame in self.d.stream_tags(self.cam):
                out = {}
                for t in frame.tags or ():
                    if t.tag.family.value != 'apriltag':
                        continue
                    w = t.world
                    if w is None or w.x is None:
                        continue
                    out[t.tag.number] = (math.degrees(t.yaw_rad),
                                         float(w.x), float(w.y))
                yield out
        except Exception as e:
            raise CamDown(f'aprilcam stream died: {e}') from e


def _stream(tag_id, hz):
    """Print `yaw_deg x_cm y_cm` lines forever, for another process.

    The camera library and pyserial live in DIFFERENT interpreters (the
    aprilcam venv has no pyserial), so the camera runs as its own
    process and streams lines; the robot-driving process reads them.
    """
    cam = Cam()
    try:
        for tags in cam.frames():
            r = tags.get(tag_id)
            if r is None:
                # Say NOTAG rather than nothing: a consumer that only
                # sees silence cannot tell a dead daemon from a
                # motionless robot, and once read a stopped daemon as a
                # lost robot.
                print('NOTAG', flush=True)
            else:
                print(f'{r[0]:.3f} {r[1]:.3f} {r[2]:.3f}', flush=True)
    except CamDown as e:
        print(f'ERR {e}', flush=True)
        return


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', type=int, default=53)
    ap.add_argument('--hz', type=float, default=20.0,
                    help='ignored; the stream paces itself off the camera')
    ap.add_argument('--check', action='store_true',
                    help='verify the fixed calibration tags and exit')
    ap.add_argument('--register', metavar='ROBOT|field', default=None,
                    help="register ROBOT's tag mount (or the fixed "
                         "field tags, with 'field') from "
                         "field_calibration.json, then exit -- the only "
                         "path that writes to the daemon's persistent "
                         "mount registry")
    args = ap.parse_args()
    if args.register:
        Cam.register(args.register)
        print(f'registered {args.register!r} from {CALIBRATION_PATH}')
        sys.exit(0)
    if args.check:
        cal = load_calibration()
        check_tags = cal.get('field', {}).get('tags', {})
        cam = Cam()
        for tags in cam.frames():
            for num_str, spec in check_tags.items():
                num = int(num_str)
                tx, ty = spec['truth_x_cm'], spec['truth_y_cm']
                r = tags.get(num)
                if r is None:
                    print(f'tag {num}: NOT VISIBLE')
                else:
                    print(f'tag {num}: ({r[1]:7.2f},{r[2]:7.2f}) truth '
                          f'({tx:6.1f},{ty:6.1f})  err '
                          f'{math.hypot(r[1] - tx, r[2] - ty):.2f} cm')
            break
        sys.exit(0)
    _stream(args.tag, args.hz)
