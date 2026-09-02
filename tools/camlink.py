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
removes one; nothing here needs to re-register on every session for
the daemon to already know a tag's mount. Annotations are the
exception: those stay per-session, unlike mount registrations.
ensure_registered() is still called below, but only as cheap, harmless
idempotent insurance (a re-registration is a no-op if the daemon
already has it) -- not because the daemon would otherwise have
forgotten. An unregistered tag is reported RAW: no parallax, no lever
arm, no mount yaw. For vevov's tag that is 6.4 cm of parallax plus
3.6 cm of lever, and it looks perfectly plausible -- it is a position
on the field, just the wrong one. Verified against ground truth
2026-08-23 with the robot parked on the NE orange dot.

Units the daemon wants, all learned the hard way against that truth:
  mount_x / mount_y   CENTIMETRES (mm gives a 32 cm error)
  mount_z             centimetres, drives parallax
  mount_yaw_rad       tag heading relative to robot forward. vevov's
                      tag is mounted a quarter turn round, so -pi/2.
                      Leaving it 0 costs 4.2 cm.
With those set the daemon also corrects the REPORTED YAW, so yaw_rad is
the robot's heading directly -- no +90 fudge.
"""
import math
import sys

from aprilcam.client.discovery import Discovery
from aprilcam.client import daemon_client as dc

CAM = 'arducam-ov9782-usb-camera'

# tag -> (mount_x cm, mount_y cm, mount_z cm, mount_yaw_rad)
#
# mount_yaw_rad is -pi/2 on every robot-mounted entry below for the
# SAME reason: yaw_rad is atan2 along the tag's front-left -> front-
# right edge, while the drawn "hat" points outward from that edge --
# perpendicular to it. That 90.00 deg gap is a fixed AprilCam
# convention, identical for every tag on every robot, and is never
# re-measured. Only a sub-degree residual is physical -- how square the
# plate itself actually sits -- and it changes only if a plate is
# unbolted and remounted. tigez's -89.65 deg below is -90.00 deg of
# convention plus 0.35 deg of that physical mount skew.
MOUNTS = {
    53: (-3.61, -0.05, 11.8, -math.pi / 2),   # vevov, centre of rotation
    52: (-4.10, 0.05, 11.3, -math.pi / 2),    # tovez, same mounting style
    57: (-0.67, -0.02, 11.7, -math.pi / 2),   # tigez, same mounting style
    # Fixed calibration tags standing over known dots: height only.
    # They are permanent ground truth in every frame -- tag 10 sits over
    # NW (-50, 30), tag 11 over SW (-50, -30).
    10: (0.0, 0.0, 20.2, 0.0),
    11: (0.0, 0.0, 13.6, 0.0),
}
CHECK = {10: (-50.0, 30.0), 11: (-50.0, -30.0)}


class CamDown(RuntimeError):
    """The daemon is gone -- distinct from a tag simply not being seen."""


class Cam:
    """Tag reader. `read` returns (yaw_deg, x_cm, y_cm) or None."""

    def __init__(self, cam=CAM):
        self.cam = cam
        try:
            self.d = Discovery().connect()
        except Exception as e:
            raise CamDown(f'aprilcam daemon unreachable: {e}') from e
        self.ensure_registered()
        self._stream = None

    def ensure_registered(self):
        """Re-send every known mount to the daemon.

        Cheap idempotent insurance, not mandatory session setup: mount
        registrations already persist in the daemon and survive a
        restart, so this is a no-op in the common case where the
        daemon already has them. It only does real work the first time
        a tag in MOUNTS is registered at all.
        """
        for num, (mx, my, mz, myaw) in MOUNTS.items():
            self.d.register_tag(
                dc.TagId(family=dc.TagFamily.APRILTAG, number=num),
                dc.MountParameters(size_cm=None, mount_x=mx, mount_y=my,
                                   mount_z=mz, mount_yaw_rad=myaw))

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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', type=int, default=53)
    ap.add_argument('--hz', type=float, default=20.0,
                    help='ignored; the stream paces itself off the camera')
    ap.add_argument('--check', action='store_true',
                    help='verify the fixed calibration tags and exit')
    args = ap.parse_args()
    if args.check:
        cam = Cam()
        for tags in cam.frames():
            for num, (tx, ty) in CHECK.items():
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
