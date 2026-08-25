"""Camera-subprocess lifecycle: interpreter resolution, spawn, `ERR`
surfacing, staleness invalidation.

Every tool that needs the overhead camera gets it through this module's
`Cam` class instead of hand-rolling a `subprocess.Popen([VENV, CAMLINK,
...])` plus a polling thread of its own -- this repo used to carry
seven near-identical copies of exactly that (`tour_run.py`,
`tour_square.py`, `tour_closedloop.py`, `tour_watch.py`,
`tour_practice.py`'s `CamProc`, `pivot_truth.py`'s `CamStream`,
`turn_sweep.py`'s `CamStream`) -- see
`clasi/sprints/005-retrofit-bench-tooling-onto-the-v6-telemetry-stream/
issues/tools-link-layer-consolidation.md` (code review R-24/R-26).

**Interpreter resolution (R-24).** The AprilTags venv path is resolved
ONCE, here, via `resolve_venv()` (the `APRILTAGS_VENV` environment
variable, falling back to the historically-correct hardcoded default
below). No other `tools/*.py` file may hardcode this path -- six of
the seven copied scaffolds this module replaces pointed at a STALE
venv where `import aprilcam` no longer works (only `tour_run.py`'s
copy had the right one), a silent 2-way fork this module ends by being
the only place the path is written down. Unset, the default matches
what a bench operator's existing invocation already assumed, so this
is a silent migration, not one that requires anyone to change how they
already run these tools.

**`latest`/camera-sample tuple order.** `tools/field.py`'s own
docstring documents the canonical order this module follows:
`(x_cm, y_cm, yaw_deg)` for a single fix (`Cam.latest`, `Cam.fix()`),
`(t, x_cm, y_cm, yaw_deg)` for a timestamped sample (`Cam.samples`,
`Cam.since()`) -- unifying `tour_run.py`'s original `(x, y, yaw)` and
`tour_practice.py`'s `(yaw, x, y)`.

**`ERR` surfacing and stale-pose invalidation (R-26a).**
`camlink.py`'s subprocess prints an `ERR ...` line (see its `CamDown`)
and exits when the daemon dies. Previously every spawn site read
`stderr=subprocess.DEVNULL` and several never checked for an `ERR` line
on stdout at all, so a dead camera read as "robot invisible" rather
than "instrument is gone." This class always captures a leading `ERR`
line into `self.err` -- and, critically, the moment it does, `.latest`
and `.fix()` stop returning the last good sample and return `None`
instead. A caller (`place()`/`fix()`-style repositioning code) cannot
re-seed the robot's world frame from a frozen, pre-death pose after a
mid-session camera death.
"""
import os
import subprocess
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
CAMLINK = os.path.join(_HERE, 'camlink.py')

# The interpreter that actually has the aprilcam package installed
# (confirmed working -- see camlink.py's own docstring). This is
# tour_run.py's original value; six of the seven Cam scaffolds this
# module replaces instead hardcoded a STALE path
# (.../AprilTags/.venv/bin/python3, where `import aprilcam` now fails).
_DEFAULT_VENV = '/Volumes/Cache/User-Eric/.local/pipx/venvs/aprilcam/bin/python'


def resolve_venv():
    """The AprilTags interpreter path, resolved ONCE.

    `APRILTAGS_VENV` overrides it; unset, this returns the same path
    every bench operator's invocation already assumed -- a silent
    migration, not one that requires anyone to change how they already
    run these tools.
    """
    return os.environ.get('APRILTAGS_VENV', _DEFAULT_VENV)


class Cam:
    """Overhead camera in its own subprocess (`camlink.py`, run under
    the AprilTags venv -- pyserial and aprilcam do not coexist in one
    interpreter here; see `robotlink.py`'s and `camlink.py`'s own
    docstrings).

    `latest` / `fix()` return `(x_cm, y_cm, yaw_deg)` or `None`.
    Timestamped samples (`.samples`, `.since()`) are
    `(t, x_cm, y_cm, yaw_deg)`. See the module docstring for the
    `ERR`-surfacing and stale-pose-invalidation contract.

    `respawn=True` (`tour_square.py`'s original behavior) restarts the
    subprocess if it dies instead of giving up, recording each death's
    timestamp in `.deaths` so a caller can flag scores computed across
    a respawn window as untrustworthy.
    """

    def __init__(self, tag=None, hz=20.0, venv=None, camlink=CAMLINK,
                 respawn=False, _spawn=True):
        self.tag = tag
        self.hz = hz
        self.venv = venv or resolve_venv()
        self.camlink = camlink
        self.respawn = respawn
        self._latest = None
        self.samples = []
        self.err = None
        self.notag = 0
        self.deaths = []
        self._stopping = False
        self.lock = threading.Lock()
        self.p = None
        self._thread = None
        if _spawn:
            self.p = self._spawn_process()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            deadline = time.time() + 15.0
            while (time.time() < deadline and self._latest is None
                   and not self.err):
                time.sleep(0.2)

    def _spawn_process(self):
        cmd = [self.venv, self.camlink, '--hz', str(self.hz)]
        if self.tag is not None:
            cmd += ['--tag', str(self.tag)]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True,
                                 bufsize=1)

    def _run(self):
        while True:
            for line in self.p.stdout:
                if self._handle_line(line):
                    if not self.respawn:
                        return
                    break
            if not self.respawn or self._stopping:
                return
            with self.lock:
                self.deaths.append(time.time())
            time.sleep(0.5)
            self.p = self._spawn_process()

    def _handle_line(self, line):
        """Process one raw stdout line from `camlink.py`. Returns True
        if this line marked the stream dead (an `ERR` line).

        Deliberately free of any subprocess/thread dependency -- a test
        can call it directly against a `Cam(_spawn=False)` instance and
        assert on `.latest`/`.err`/`.samples` afterward, no real camera
        or subprocess required.
        """
        line = line.strip()
        if line.startswith('ERR'):
            with self.lock:
                self.err = line
                self._latest = None       # R-26a: invalidate on death
            return True
        if line in ('NOTAG', ''):
            with self.lock:
                self.notag += 1
            return False
        try:
            yaw, x, y = (float(v) for v in line.split())
        except ValueError:
            return False
        with self.lock:
            self.notag = 0
            self._latest = (x, y, yaw)
            self.samples.append((time.time(), x, y, yaw))
        return False

    @property
    def latest(self):
        with self.lock:
            return None if self.err else self._latest

    def fix(self, n=8, stale_after=40):
        """Median of up to `n` samples ~0.06s apart, or `None`.

        `None` once the stream has died (`.err` set -- checked both
        before and after sampling, so a death mid-window is not
        missed) or once `stale_after` consecutive NOTAG/blank lines
        have arrived with no tag seen (~2s at the default) -- either
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
        med = lambda i: sorted(v[i] for v in vals)[len(vals) // 2]
        return med(0), med(1), med(2)

    def since(self, t0):
        with self.lock:
            return [s for s in self.samples if s[0] >= t0]

    def close(self):
        self._stopping = True
        if self.p is not None:
            self.p.terminate()
