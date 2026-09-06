"""tests/tools/test_angle_wrap_ownership.py -- sprint 034 ticket 009:
one owner for angle wrapping, `tools/field.py::wrap()`.

**Why this exists.** Sprint 005 consolidated eight functionally
identical `wrap()` implementations into `tools/field.py`. FOUR grew
back, and -- this is the part a "they're all the same function" reading
misses -- two of them DISAGREED about the boundary:

| where                                   | range          |
|-----------------------------------------|----------------|
| `tools/field.py::wrap`                  | `(-180, 180]`  |
| `tools/leg_analysis.py::_wrap_deg`      | `[-180, 180)`  |
| `tools/linefollow/stage.py::wrap`       | `[-180, 180)`  |
| `tests/calibration/turn_calibration.py::wrap` | `[-180, 180)` |

plus the same modulo idiom written inline in `linefollow/camlog.py`,
`follow.py`, `sensor_run.py` and `tests/calibration/field_dance.py`,
and a fourth spelling (`atan2(sin(x), cos(x))`) in
`tools/otos_levercal.py`. `leg_analysis._wrap_deg`'s own docstring
claimed `(-180, 180]` while its body returned the other interval, which
is how long a private copy can be wrong without anyone noticing.

On this fleet the disagreement is not academic: +/-180 is in the
standard `PIVOTS` list, so a 180 deg command is a value the boundary is
actually asked about. `field.wrap()` now documents the convention on
itself; this file is the guard that no fifth copy appears, because a
private copy is exactly as dangerous when it happens to agree -- the
next reader still has to check.

Text-based, not an import: several of the audited files connect to an
aprilcam daemon or open a serial link at module scope, so importing
them here would either hang or depend on whatever is running on the
host. Reading them as plain text needs neither.

Run with::

    uv run pytest tests/tools/test_angle_wrap_ownership.py
"""
import ast
import pathlib
import re

import pytest

# tests/tools/test_angle_wrap_ownership.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_OWNER = _REPO_ROOT / 'tools' / 'field.py'

#: The two trees this ticket consolidated. `tests/host/` and
#: `tests/system/` are deliberately NOT scanned: they are host-side
#: firmware harnesses that wrap RADIANS onto (-pi, pi] against the C++
#: kernel's own convention (`tests/host/test_motion_engine_reductions.py`
#: `_wrap_to_pi`), which is a different function answering a different
#: question, not a copy of this one.
_SCANNED_ROOTS = ('tools', 'tests/calibration')

#: A private definition: `def wrap`, `def _wrap`, `def wrap_deg`,
#: `def _wrap_deg`. Not `def unwrapped_turn` -- unwrapping a CONTINUOUS
#: sample stream onto a total is a real, separate operation that
#: legitimately calls `wrap()` in its loop.
_DEF_RE = re.compile(r'^\s*def\s+_?wrap', re.MULTILINE)

#: The modulo idiom, in any spacing: `(d + 180) % 360 - 180`,
#: `(d+180)%360-180`, `... % 360.0 - 180.0`.
_IDIOM_RE = re.compile(r'%\s*360(?:\.0)?\s*-\s*180')

#: Files allowed to NAME the retired idiom in prose. Only the owner:
#: `field.wrap()`'s docstring documents which boundary the idiom closes
#: and why this repo chose the other one, and a guard that forbade the
#: owner from explaining itself would delete the documentation this
#: ticket exists to write. (This guard file names it too, above.)
_IDIOM_PROSE_ALLOWED = {_OWNER, pathlib.Path(__file__).resolve()}


def _scanned_files():
    for root in _SCANNED_ROOTS:
        for path in sorted((_REPO_ROOT / root).rglob('*.py')):
            if '__pycache__' in path.parts:
                continue
            yield path


def _relative(paths):
    return sorted(str(p.relative_to(_REPO_ROOT)) for p in paths)


def test_field_defines_exactly_one_wrap():
    """The owner owns it once. Two `def wrap` in `field.py` itself
    would satisfy every other check in this file."""
    assert len(_DEF_RE.findall(_OWNER.read_text())) == 1


def test_field_wrap_documents_its_boundary_convention():
    """The convention is the whole point of having one owner: a reader
    must be able to learn, from the function, what happens at exactly
    +/-180 without running it."""
    text = _OWNER.read_text()
    head = text[text.index('def wrap('):]
    doc = head[:head.index('"""', head.index('"""') + 3)]
    assert '(-180, 180]' in doc, (
        'field.wrap() must state its interval in its own docstring')
    assert 'wrap(180) == +180' in doc and 'wrap(-180) == +180' in doc, (
        'field.wrap() must say what it returns at exactly +/-180 -- that '
        'is the value the four retired copies disagreed about')


def test_no_other_file_defines_its_own_wrap():
    offenders = [p for p in _scanned_files()
                 if p != _OWNER and _DEF_RE.search(p.read_text())]
    assert _relative(offenders) == [], (
        f'{_relative(offenders)} define a private wrap(). There is one, '
        f'in tools/field.py, and it documents its boundary convention; '
        f'import it (`from field import wrap`) instead. A private copy '
        f'is a hazard even when it agrees -- three of the four that '
        f'sprint 034 ticket 009 retired closed the OTHER end of the '
        f'interval, and one of them said so incorrectly in its own '
        f'docstring.')


def test_no_file_writes_the_modulo_idiom_inline():
    """The copies that had no `def` at all -- four inline uses across
    `tools/linefollow/` and `tests/calibration/field_dance.py`. These
    are the easiest to miss and the easiest to re-add."""
    offenders = [p for p in _scanned_files()
                 if p not in _IDIOM_PROSE_ALLOWED
                 and _IDIOM_RE.search(p.read_text())]
    assert _relative(offenders) == [], (
        f'{_relative(offenders)} write the angle-wrap modulo idiom '
        f'inline. It closes the opposite end of the interval from '
        f'field.wrap(); call `wrap()` instead.')


@pytest.mark.parametrize('rel', [
    'tools/leg_analysis.py',
    'tools/park.py',
    'tools/reposition.py',
    'tools/otos_levercal.py',
    'tools/tour_run.py',
    'tools/linefollow/stage.py',
    'tools/linefollow/camlog.py',
    'tools/linefollow/follow.py',
    'tools/linefollow/sensor_run.py',
    'tests/calibration/turn_calibration.py',
    'tests/calibration/field_dance.py',
])
def test_every_converted_file_imports_the_shared_wrap(rel):
    """The other half of "no private copy": each file that used to have
    one now actually imports the shared function, rather than having
    dropped the wrap entirely. `otos_levercal.py` is in this list
    because its `atan2(sin, cos)` spelling was folded in too -- it
    already agreed with `field.wrap()` (`atan2`'s range IS `(-pi, pi]`),
    which is precisely why it would otherwise have survived unnoticed
    as a lookalike."""
    # Parsed, not grepped: several of these use the parenthesised
    # multi-line `from field import (a, b, wrap)` form, where a
    # line-anchored regex sees the import and the name on different
    # lines. `ast.parse()` reads the file without executing it, so the
    # module-scope daemon connections stay untouched.
    tree = ast.parse((_REPO_ROOT / rel).read_text())
    imported = any(
        isinstance(node, ast.ImportFrom) and node.module == 'field'
        and any(alias.name == 'wrap' for alias in node.names)
        for node in ast.walk(tree))
    assert imported, (
        f'{rel} must import the shared wrap from tools/field.py')


def test_otos_levercal_no_longer_hand_rolls_atan2_sin_cos():
    """The fourth spelling. Left alone it reads as a different
    operation, so the next reader re-derives whether it agrees."""
    text = (_REPO_ROOT / 'tools' / 'otos_levercal.py').read_text()
    assert not re.search(r'atan2\(\s*math\.sin\(', text), (
        'otos_levercal.py hand-rolls a wrap as atan2(sin(x), cos(x)); '
        'call field.wrap() so the boundary has one owner')
