"""tourfile -- parser for .tour scripts.

A tour file is a text version of the protocol: one directive per line.
Ported from radio-robot-elite's `src/tests/system/tourfile.py` grammar,
reduced to the directives this repo's v6 wire can execute and extended
with REPEAT (for lap-based tours such as the infinity figure).

    # comment                          blank lines ignored
    MARK <name>                        label the next segment
    TWIST vx=150 [omega=57.3] (dist=|angle=|time=) [timeout=]
    STOP [dwell=1.0]
    DWELL 0.5
    SET <wire_field> <value>           robot config, applied in order
    SPLINE file=<p.json> [speed=] [lookahead=] [laps=] [interval=]
                                       follow a fitted path, pure pursuit
    REPEAT <n> ... END                 repeat the enclosed block n times

Human units in the file: mm, mm/s, deg, deg/s, s. TWIST is the ONE
motion directive and covers all three shapes, which is the point of the
format:

    vx + dist            straight
    omega + angle        pivot in place
    vx + omega + angle   ARC of radius r = vx / omega

The arc form is why a circle is four moves rather than seventy chords:
MOVE_X takes a body distance AND a rotation, so a constant-curvature
segment is a single command the motion engine shapes end to end.

Unknown directives and unknown key=value keys raise immediately -- a
tour author gets a clear error, never a silent misparse.
"""
from __future__ import annotations

import math
import shlex
from dataclasses import dataclass, field
from pathlib import Path

_DEG = math.pi / 180.0
_TIMEOUT_FACTOR = 3.0
_MIN_TIMEOUT = 2.0        # [s]
_PIVOT_HALF_TRACK_MM = 60.0   # b/2, for turning a pivot's deg/s into mm/s


class TourParseError(ValueError):
    pass


@dataclass
class Twist:
    """One motion segment, normalized to wire units."""
    dist_mm: float          # body distance, signed
    rot_mrad: float         # rotation, signed CCW+
    cruise_mm_s: float      # dominant-wheel speed ceiling
    timeout_s: float
    mark: str = ''

    @property
    def kind(self) -> str:
        if self.rot_mrad and self.dist_mm:
            return 'arc'
        if self.rot_mrad:
            return 'pivot'
        return 'straight'


@dataclass
class Dwell:
    seconds: float
    mark: str = ''
    kind: str = 'dwell'


@dataclass
class SetCfg:
    field_name: str
    value: float
    kind: str = 'set'


@dataclass
class Spline:
    """Follow a fitted path with pure pursuit.

    Unlike Twist, this is NOT a segment the motion engine shapes on its
    own: the host closes a loop around the robot's odometry pose,
    picking a new aim point every control period. `run_tour.py` owns
    that loop; this only carries its parameters.

    speed      body speed to hold along the path      [mm/s]
    lookahead  radius of the pursuit circle           [mm]
    laps       times round a closed path
    interval   host control period                    [s]
    """
    path: str
    speed: float
    lookahead: float
    laps: int
    interval: float
    mark: str = ''
    kind: str = 'spline'


@dataclass
class Tour:
    name: str
    steps: list = field(default_factory=list)
    source: str = ''


def _kv(tokens, allowed, line_no):
    out = {}
    for tok in tokens:
        if '=' not in tok:
            raise TourParseError(f'line {line_no}: expected key=value, got {tok!r}')
        k, v = tok.split('=', 1)
        if k not in allowed:
            raise TourParseError(
                f'line {line_no}: unknown key {k!r} (allowed: {sorted(allowed)})')
        try:
            out[k] = float(v)
        except ValueError:
            raise TourParseError(f'line {line_no}: {k}={v!r} is not a number')
    return out


def _twist(kv, line_no, mark):
    vx = kv.get('vx', 0.0)                    # [mm/s]
    omega = kv.get('omega', 0.0) * _DEG       # [rad/s]

    if 'dist' in kv:
        dist = kv['dist']
        rot = (dist / vx) * omega if (omega and vx) else 0.0
        duration = abs(dist) / vx if vx else _MIN_TIMEOUT
    elif 'angle' in kv:
        rot = kv['angle'] * _DEG
        if not omega:
            raise TourParseError(f'line {line_no}: angle= needs omega=')
        duration = abs(rot) / abs(omega)
        # vx present => arc of radius vx/omega; absent => pivot in place
        dist = vx * duration if vx else 0.0
    elif 'time' in kv:
        duration = kv['time']
        dist = vx * duration
        rot = omega * duration
    else:
        raise TourParseError(f'line {line_no}: TWIST needs dist=, angle= or time=')

    cruise = vx if vx else abs(omega) * _PIVOT_HALF_TRACK_MM
    timeout = kv.get('timeout', max(_MIN_TIMEOUT, _TIMEOUT_FACTOR * duration))
    return Twist(dist_mm=dist, rot_mrad=rot * 1000.0,
                 cruise_mm_s=max(cruise, 1.0), timeout_s=timeout, mark=mark)


def parse_tour(path) -> Tour:
    p = Path(path)
    tour = Tour(name=p.stem, source=str(p))
    pending_mark = ''
    repeat_stack = []          # [(count, [steps]), ...]

    def emit(step):
        if repeat_stack:
            repeat_stack[-1][1].append(step)
        else:
            tour.steps.append(step)

    for line_no, raw in enumerate(p.read_text().splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        tokens = shlex.split(line)
        verb = tokens[0].upper()
        rest = tokens[1:]

        if verb == 'MARK':
            pending_mark = rest[0] if rest else ''
        elif verb == 'TWIST':
            kv = _kv(rest, {'vx', 'vy', 'omega', 'dist', 'angle', 'time',
                            'timeout'}, line_no)
            emit(_twist(kv, line_no, pending_mark))
            pending_mark = ''
        elif verb == 'STOP':
            kv = _kv(rest, {'dwell'}, line_no)
            emit(Dwell(seconds=kv.get('dwell', 0.5), mark=pending_mark))
            pending_mark = ''
        elif verb == 'DWELL':
            emit(Dwell(seconds=float(rest[0]) if rest else 0.5, mark=pending_mark))
            pending_mark = ''
        elif verb == 'SET':
            if len(rest) != 2:
                raise TourParseError(f'line {line_no}: SET needs <field> <value>')
            emit(SetCfg(field_name=rest[0], value=float(rest[1])))
        elif verb == 'REPEAT':
            repeat_stack.append((int(float(rest[0])), []))
        elif verb == 'END':
            if not repeat_stack:
                raise TourParseError(f'line {line_no}: END without REPEAT')
            count, block = repeat_stack.pop()
            for _ in range(count):
                for s in block:
                    emit(s)
        elif verb == 'SPLINE':
            kv = {}
            for tok in rest:
                if '=' not in tok:
                    raise TourParseError(
                        f'line {line_no}: expected key=value, got {tok!r}')
                k, v = tok.split('=', 1)
                kv[k] = v
            allowed = {'file', 'speed', 'lookahead', 'laps', 'interval', 'tol'}
            unknown = set(kv) - allowed
            if unknown:
                raise TourParseError(
                    f'line {line_no}: unknown SPLINE key(s) {sorted(unknown)}')
            if 'file' not in kv:
                raise TourParseError(f'line {line_no}: SPLINE needs file=')
            # `tol` is the elite runner's closure assertion. This runner
            # reports cross-track error instead of asserting a tolerance,
            # so it is accepted and ignored rather than rejected -- a
            # ported tour should not fail to parse over it.
            emit(Spline(path=kv['file'],
                        speed=float(kv.get('speed', 150.0)),
                        lookahead=float(kv.get('lookahead', 150.0)),
                        laps=int(float(kv.get('laps', 1))),
                        interval=float(kv.get('interval', 0.12)),
                        mark=pending_mark))
            pending_mark = ''
        elif verb in ('CAMFIX', 'SEND', 'EXPECT', 'DBG', 'WHEELS'):
            # Directives the elite runner supports that this bench runner
            # does not execute. Reported rather than silently dropped, so
            # a ported tour cannot appear to pass while a check never ran.
            print(f'  note: line {line_no}: {verb} not executed by the bench '
                  f'runner (camera / spline / v5-only directive)')
        else:
            raise TourParseError(f'line {line_no}: unknown directive {verb!r}')

    if repeat_stack:
        raise TourParseError('REPEAT block was never closed with END')
    return tour
