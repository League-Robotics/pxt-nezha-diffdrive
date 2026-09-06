"""Fast overhead-camera access: one persistent gRPC stream, in this
interpreter.

`Cam` is the ONE camera class every bench tool uses, and it reads the
aprilcam daemon directly -- no camera subprocess, no second interpreter
to bridge: `aprilcam[daemon]` is a declared dependency of this
project's own venv (`pyproject.toml`), so `import aprilcam` and
`import serial` both work here. A background reader thread publishes
one sample per real camera frame, and `latest`/`fix()` carry the
stale-pose-invalidation contract (see `Cam`).

THE DAEMON DOES THE CORRECTING, AND IT REMEMBERS.
Tag mount registrations persist across a daemon restart -- they are
written to the daemon's mounts registry on disk and reload
automatically at daemon startup. Only an explicit unregister_tag call
removes one.

**`field_calibration.json` is the one calibration of record (TL-02).**
Constructing `Cam` registers nothing. Registration is explicit --
`register()`, or `--register` from the CLI -- called once, when a mount
has actually changed. Registering on every tool start would overwrite
the daemon's persistent registry with a stale mount and silently
discard a fresh remount (a 2026-09-02 tag-53 remount was lost that way).

REGISTERED vs RAW -- settle which one you are reading before trusting a
heading. A REGISTERED tag's `yaw_rad` IS the robot's heading, already
corrected: read it straight, add nothing. An UNREGISTERED tag is
reported RAW -- no parallax, no lever arm, no mount yaw. For vevov's
tag that is 6.4 cm of parallax plus 3.6 cm of lever, and it looks
perfectly plausible -- it is a position on the field, just the wrong
one. Verified against ground truth 2026-08-23 with the robot parked on
the NE orange dot.

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
import threading
import time

from aprilcam.client.discovery import Discovery
from aprilcam.client import daemon_client as dc

CAM = 'arducam-ov9782-usb-camera'

#: The tag a `Cam` follows when the caller names none -- the value the
#: `--tag` flag has always defaulted to.
DEFAULT_TAG = 53

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
    """The overhead camera, read in THIS process.

    Two ways to read it, and they are not interchangeable:

    * `frames()` -- the raw generator, one dict per real camera frame.
      Nothing is cached; the caller drives the loop.
    * the FOLLOWED TAG surface -- `latest`, `fix()`, `samples`,
      `since()`, `err`, `notag` -- fed by a background reader thread
      that follows `tag` and publishes one sample per real frame. This
      is what the bench tools use, and it is the surface the deleted
      camera-subprocess wrapper used to provide.

    Tuple order follows `tools/field.py`'s documented convention: a
    single fix (`latest`, `fix()`) is `(x_cm, y_cm, yaw_deg)`; a
    timestamped sample (`samples`, `since()`) is
    `(t, x_cm, y_cm, yaw_deg)`.

    **A dead stream invalidates the cached pose.** The moment the
    reader thread sees the daemon go away it records the failure in
    `err` and drops `_latest`, so `latest`/`fix()` return `None` rather
    than the last good sample. A caller re-seeding the robot's world
    frame cannot do it from a frozen, pre-death pose.

    **Daemon gone vs tag not in frame are different answers.** An
    unreachable daemon raises `CamDown` at construction, or lands in
    `err` if the stream dies later; a tag simply not in frame only
    advances `notag`, leaving `err` `None` -- a dead instrument must
    never read as "the robot is invisible".

    Construction NEVER touches the daemon's mount registry -- see
    `register()` for the explicit, opt-in path that does (TL-02).
    `client` is an injected daemon client for tests; omitted, this
    connects for real via `Discovery().connect()`. `stream=False`
    leaves the reader thread unstarted, for a caller that only wants
    `frames()` or `register()`.
    """

    def __init__(self, tag: int | None = None, cam: str = CAM, client=None,
                 stream: bool = True, wait: float = 15.0) -> None:
        self.tag = DEFAULT_TAG if tag is None else tag
        self.cam = cam
        self.lock = threading.Lock()
        self.samples: list[tuple[float, float, float, float]] = []
        self.err: str | None = None
        self.notag = 0
        self._latest: tuple[float, float, float] | None = None
        self._stopping = False
        self._thread: threading.Thread | None = None
        if client is not None:
            self.d = client
        else:
            try:
                self.d = Discovery().connect()
            except Exception as e:
                raise CamDown(f'aprilcam daemon unreachable: {e}') from e
        if stream:
            self.start(wait=wait)

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

        Returns the `Cam` used, so a caller can keep reading afterward
        (with `frames()`, or by calling `start()` on it -- registering
        is not itself a reason to spend 15 s waiting for a first
        sample, so the reader thread is left unstarted).
        Raises `SystemExit` (not a bare KeyError) naming the exact
        problem when `target`/its fields are missing -- this is an
        operator-facing CLI path.
        """
        cal = calibration if calibration is not None else load_calibration()
        cam = cls(client=client, stream=False)
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

    # --- the followed-tag surface, fed by the reader thread ----------

    def start(self, wait: float = 15.0) -> 'Cam':
        """Start the background reader thread, once. Returns `self`.

        Blocks up to `wait` seconds for a first sample or a stream
        death, so a caller can test `latest`/`err` on the next line
        instead of sleeping a fixed amount and hoping.
        """
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        deadline = time.time() + wait
        while time.time() < deadline and self.latest is None and not self.err:
            time.sleep(0.05)
        return self

    def _run(self) -> None:
        """Consume `frames()` until the stream dies or `close()`.

        A `CamDown` here is the instrument dying, not the robot leaving
        frame, so it is recorded in `err` (which invalidates `latest`)
        rather than raised into a thread nobody is joining.
        """
        try:
            for tags in self.frames():
                if self._stopping:
                    return
                self._publish(tags.get(self.tag))
        except CamDown as e:
            with self.lock:
                self.err = str(e)
                self._latest = None

    def _publish(self, reading: tuple[float, float, float] | None) -> None:
        """Record ONE real camera frame. `reading` is this Cam's tag as
        `(yaw_deg, x_cm, y_cm)`, or `None` if that tag had no world fix
        in this frame.

        One call per frame the camera actually produced, and no
        synthesised samples in between: polling faster than the camera
        used to make ~70% of samples repeats, and anything scoring
        per-sample motion then measured the camera's frame rate instead
        of the robot's. A frame with no fix advances `notag` and is
        skipped -- never published as a pose of zeros.
        """
        with self.lock:
            if reading is None:
                self.notag += 1
                return
            yaw, x, y = reading
            self.notag = 0
            self._latest = (x, y, yaw)
            self.samples.append((time.time(), x, y, yaw))

    @property
    def latest(self) -> tuple[float, float, float] | None:
        with self.lock:
            return None if self.err else self._latest

    def fix(self, n: int = 8,
            stale_after: int | None = 40
            ) -> tuple[float, float, float] | None:
        """Median of up to `n` samples ~0.06s apart, or `None`.

        `None` once the stream has died (`err` set -- checked both
        before and after sampling, so a death mid-window is not
        missed) or once `stale_after` consecutive frames have arrived
        with no tag in them (~10s at the default and ~4 Hz) -- either
        way, never a frozen pre-death/pre-loss value.
        """
        vals = []
        for _ in range(n):
            with self.lock:
                if self.err:
                    return None
                if stale_after is not None and self.notag > stale_after:
                    return None
                r = self._latest
            if r:
                vals.append(r)
            time.sleep(0.06)
        with self.lock:
            if self.err:
                return None
        if not vals:
            return None

        def med(i: int) -> float:
            return sorted(v[i] for v in vals)[len(vals) // 2]

        return med(0), med(1), med(2)

    def since(self, t0: float) -> list[tuple[float, float, float, float]]:
        with self.lock:
            return [s for s in self.samples if s[0] >= t0]

    def close(self) -> None:
        """Stop following the tag. The reader thread is a daemon
        thread blocked in the daemon's stream, so this asks it to stop
        at the next frame rather than killing it."""
        self._stopping = True


def _watch(tag_id: int) -> None:
    """Print one tag's pose per camera frame, for a HUMAN at a
    terminal (Ctrl-C to stop).

    Not a protocol -- nothing parses these lines. The machine-readable
    `yaw x y` / `NOTAG` / `ERR` stream this used to print existed only
    so a second interpreter could read the camera; every consumer now
    constructs `Cam` in its own process (sprint 034 ticket 008).
    """
    cam = Cam(tag=tag_id, stream=False)
    for tags in cam.frames():
        r = tags.get(tag_id)
        if r is None:
            print(f'tag {tag_id}: not in frame', flush=True)
        else:
            print(f'tag {tag_id}: yaw {r[0]:8.2f} deg  '
                  f'({r[1]:7.2f},{r[2]:7.2f}) cm', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', type=int, default=DEFAULT_TAG)
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
        cam = Cam(stream=False)
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
    _watch(args.tag)
