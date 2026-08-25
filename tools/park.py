"""Park the robot on a world pose using forward AND reverse motion.

A differential drive is symmetric: it reverses exactly as well as it
drives forward. Ignoring that costs rotation, and on this robot
rotation is where the error lives -- camera-measured on vevov
2026-08-25, four commanded 90 deg pivots turned 363.7 deg physical for
360.4 deg believed (~0.8 deg of over-rotation each) while travel was
accurate to 0.5% over the same 320 cm. So the planner's objective is
not "shortest path", it is **least total rotation**.

Three ideas, in the order they matter:

1. **Reverse instead of turning around.** To reach a point behind you,
   back into it. Approaching nose-first costs |bearing| of rotation;
   tail-first costs |bearing - 180|. Whenever the target is more than
   90 deg off the nose, reversing is strictly cheaper -- and a 180 deg
   turn-around, the single most expensive thing a pivot-and-go planner
   does, disappears entirely.

2. **Absorb heading error into the next move, never pivot it away.**
   A few degrees of residual is not worth a pivot: the pivot itself
   injects more error than it removes, and it costs settle time. Aim
   at the target from where you are ACTUALLY pointing. This is the
   project's standing rule (`camera-is-diagnostics-not-control`: errors
   are corrected on the next hop, not the current one).

3. **Finish on a translation, not a rotation.** A pivot's angular error
   lands directly in the final heading with nothing left to correct it.
   A translation's error is ~0.5%. So once the heading is right, close
   the remaining gap by driving -- forward or backward -- along it.

Pure geometry: no I/O, no link, no camera. `plan()` returns primitive
moves that a caller executes however it likes, which is what makes the
whole thing testable without a robot.
"""
import math

# One wrap() for the whole repo. Sprint 005 consolidated eight
# functionally-identical copies of this into field.py; adding a ninth
# here -- with its own half-open-interval convention, at that -- is
# exactly the drift that cleanup existed to stop.
from field import wrap

# A move is ('pivot', degrees) or ('drive', cm). Negative cm is reverse.
PIVOT, DRIVE = 'pivot', 'drive'


def _leg(pose, target_xy, reverse):
    """Turn-then-drive reaching `target_xy`, nose-first or tail-first."""
    x, y, h = pose
    tx, ty = target_xy
    dist = math.hypot(tx - x, ty - y)
    bearing = math.degrees(math.atan2(ty - y, tx - x))
    # Backing in means pointing the TAIL at the target, i.e. facing the
    # opposite way and driving negative.
    face = wrap(bearing + 180.0) if reverse else bearing
    return wrap(face - h), (-dist if reverse else dist), face


def plan(pose, target, pos_tol=0.5, head_tol=1.0, cross_tol=0.4):
    """Moves to bring `pose` to `target`. Both are (x_cm, y_cm, heading_deg).

    Returns a list of ('pivot', deg) / ('drive', cm) tuples, in order.
    An empty list means already parked to tolerance.

    `cross_tol` is the cross-track slack below which the position error
    is treated as purely along-track and closed by a straight drive
    with NO pivot at all -- idea 3 above. Widening it trades final
    position accuracy for rotational stability; it should stay well
    under `pos_tol`.
    """
    x, y, h = pose
    tx, ty, th = target
    dist = math.hypot(tx - x, ty - y)
    herr = wrap(th - h)

    if dist <= pos_tol and abs(herr) <= head_tol:
        return []

    # --- position already good: this is a HEADING job, nothing else ---
    # Falling through to the approach logic here is a trap. The bearing
    # to a target you are already standing on is pure noise, so the
    # planner cheerfully aims at it, drives a fraction of a centimetre,
    # and turns back. Measured on hardware: 0.24 cm from target with 6
    # deg of heading error, it planned TWO pivots totalling 106 deg to
    # do a job one 6 deg pivot does.
    if dist <= pos_tol:
        return [(PIVOT, herr)]

    # --- the no-pivot case: already aimed, just not there yet ---------
    # Decompose the offset in the frame of the TARGET heading. If the
    # cross-track part is negligible the gap is pure along-track, and a
    # single drive closes it without touching the heading at all. This
    # is the cheapest possible correction and the one to prefer.
    if abs(herr) <= head_tol:
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        along = c * (tx - x) + s * (ty - y)
        cross = -s * (tx - x) + c * (ty - y)
        if abs(cross) <= cross_tol:
            return [] if abs(along) <= pos_tol else [(DRIVE, along)]

    # --- otherwise: pick the approach that rotates least --------------
    options = []
    for reverse in (False, True):
        turn1, drive, face = _leg(pose, (tx, ty), reverse)
        turn2 = wrap(th - face)
        # Rotation is the error source, so rank on total rotation --
        # NOT on path length, which is identical for both options.
        options.append((abs(turn1) + abs(turn2), turn1, drive, turn2))
    _, turn1, drive, turn2 = min(options, key=lambda o: o[0])

    moves = []
    # Idea 2: a residual small enough to be absorbed is not worth a
    # pivot. Below head_tol the aim is good enough, and driving from
    # the CURRENT heading is more accurate than pivoting to a nominal
    # one first.
    if abs(turn1) > head_tol:
        moves.append((PIVOT, turn1))
    if abs(drive) > pos_tol:
        moves.append((DRIVE, drive))
    if abs(turn2) > head_tol:
        moves.append((PIVOT, turn2))
    return moves


def rotation_cost(moves):
    """Total degrees of commanded rotation -- the quantity to minimise."""
    return sum(abs(v) for kind, v in moves if kind == PIVOT)


def apply(pose, moves, slip=1.0, travel=1.0):
    """Simulate `moves` from `pose`. Returns the resulting pose.

    `slip` scales every commanded rotation (1.009 reproduces vevov's
    measured over-rotation) and `travel` scales every drive, so a plan
    can be scored against a MODEL of the robot's real errors instead of
    against a perfect one. Used by the tests to show that the reverse
    branch actually reduces accumulated heading error.
    """
    x, y, h = pose
    for kind, v in moves:
        if kind == PIVOT:
            h = wrap(h + v * slip)
        else:
            d = v * travel
            x += d * math.cos(math.radians(h))
            y += d * math.sin(math.radians(h))
    return x, y, h
