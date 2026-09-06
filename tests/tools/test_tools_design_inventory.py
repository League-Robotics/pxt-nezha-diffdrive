"""tests/tools/test_tools_design_inventory.py -- `tools/DESIGN.md` must
name every file under `tools/`.

**The defect this catches.** A subsystem design doc decays the same way
a manifest does: a tool lands, nobody adds a doc entry, and the omission
is invisible because nothing reads the doc looking for gaps. The
2026-09-02 review found `tools/DESIGN.md` had become a sprint log with
no entry for a third of the directory -- and the count it quoted was
already wrong by the time the fix was ticketed, because four more tools
and two subdirectories had arrived in the meantime. An undocumented tool
is not merely untidy: the next operator either re-implements what is
already there (this repo has had four `wrap()`s, four link layers, two
`Cam`s and two repositioning loops) or runs it without knowing what it
assumes.

Modelled on `tests/host/test_pxt_manifest_completeness.py`, which does
the same thing for `pxt.json`'s `files` list: read the tree, read the
list, compare. No import, no subprocess, no robot.

**Both directions.** A file on disk with no entry is the decay this
guard exists to stop. An inventory row naming a file that is not there
is the same drift pointing the other way -- a doc that sends a reader to
a path that no longer exists is worse than one that says nothing, and
`tests/tools/test_deleted_tools_stay_deleted.py` only pins the four
specific tools sprint 034 ticket 003 removed.

**Exclusions, with their reasons.** `__pycache__` holds build products,
not source. `__init__.py` is package plumbing with no behaviour of its
own to describe -- there are none under `tools/` today, and if one
appears it should not force a doc entry that would say nothing. Nothing
else is excluded: a script that is a shim, a data file the tools read,
or a one-off chart helper still gets its line, because "what is this
for" is exactly the question a reader has about those.

Run with::

    uv run pytest tests/tools/test_tools_design_inventory.py
"""
import pathlib
import re

import pytest

# tests/tools/test_tools_design_inventory.py -> tools -> tests -> root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
_DESIGN_MD = _TOOLS_DIR / "DESIGN.md"

#: Files that need an entry but are not `*.py`. `field_calibration.json`
#: is the fleet's calibration of record -- data the tools read, and the
#: one non-Python file under `tools/` whose contents change behaviour.
EXTRA_DOCUMENTED_FILES = ("field_calibration.json",)

#: See the module docstring for why each of these is excluded.
EXCLUDED_NAMES = ("__init__.py",)
EXCLUDED_DIRS = ("__pycache__",)


def _documented_files():
    """Every file that must be named in `tools/DESIGN.md`, as a path
    relative to `tools/` (e.g. `field.py`, `linefollow/chart.py`)."""
    found = [
        p.relative_to(_TOOLS_DIR).as_posix()
        for p in _TOOLS_DIR.rglob("*.py")
        if p.is_file()
        and p.name not in EXCLUDED_NAMES
        and not any(d in p.parts for d in EXCLUDED_DIRS)
    ]
    found += [f for f in EXTRA_DOCUMENTED_FILES if (_TOOLS_DIR / f).exists()]
    return sorted(found)


def _names(rel, text):
    """Does `text` name `rel` as a whole path?

    The boundary matters both ways. Without a left boundary
    `robotlink.py` would satisfy `link.py`; without a right one
    `field.py` would satisfy nothing useful. `/` is deliberately NOT a
    boundary character on the left, so writing the fuller
    `tools/linefollow/chart.py` still counts as naming
    `linefollow/chart.py`.
    """
    return re.search(r"(?<![\w.\-])" + re.escape(rel) + r"(?!\w)", text) \
        is not None


def _inventory_table_paths(text):
    """The first cell of every inventory table row, when it is a single
    backticked path -- e.g. ``| `linefollow/chart.py` | ... |``."""
    return [
        m.group(1)
        for m in re.finditer(r"^\|\s*`([^`|]+)`\s*\|", text, re.MULTILINE)
    ]


@pytest.mark.parametrize("rel", _documented_files())
def test_every_tools_file_is_named_in_design_md(rel):
    """A file under `tools/` that `tools/DESIGN.md` does not name is an
    undocumented tool: the next reader either re-implements it or runs
    it without knowing what it assumes."""
    text = _DESIGN_MD.read_text()
    assert _names(rel, text), (
        f"tools/{rel} exists but tools/DESIGN.md never names it. Add a "
        f"row to the Inventory section saying, in one line, what it is "
        f"for -- not what sprint added it."
    )


def test_no_inventory_row_names_a_missing_file():
    """Every path in an inventory table row must exist. A doc that
    sends a reader to a path that is not there is worse than one that
    says nothing."""
    text = _DESIGN_MD.read_text()
    missing = [
        rel
        for rel in _inventory_table_paths(text)
        if not (_TOOLS_DIR / rel).exists()
    ]
    assert missing == [], (
        f"tools/DESIGN.md's inventory names file(s) that do not exist "
        f"under tools/: {missing}"
    )


def test_the_inventory_is_not_silently_empty():
    """A regex that stops matching would make every other assertion in
    this file pass vacuously, which is the failure mode this repo keeps
    finding in its own guards."""
    rows = _inventory_table_paths(_DESIGN_MD.read_text())
    assert len(rows) >= len(_documented_files()), (
        f"tools/DESIGN.md's inventory tables parsed to {len(rows)} rows "
        f"for {len(_documented_files())} documented files -- the table "
        f"format changed and this guard is no longer reading it."
    )
