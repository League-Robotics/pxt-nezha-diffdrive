"""tests/tools/test_deleted_tools_stay_deleted.py -- pins sprint 034
ticket 003's deletions against copy-paste resurrection.

**Why this exists.** Three bench tools were deleted outright, not
because they were untidy but because each was a trap for the next
operator:

- the ground-truth checker spawned five subprocesses per fix against a
  hard-coded `127.0.0.1:5280` and read v1 JSON keys (`id`,
  `orientation_yaw`, `world_xy`) the v2 client does not emit, so its
  `cam_yaw()` returned `None` and it exited with "camera cannot see tag
  53" -- sending the operator to the lights and the camera for what was
  a tool defect. `pivot_truth.py` measures the same thing through the
  v2 client.
- two tour variants `tools/DESIGN.md` itself called "earlier variants
  kept for reference": nothing imported either, one hard-coded a Shelly
  URL, and one was the camera-in-the-loop experiment this repo's
  doctrine now forbids.

A deleted file is only half-deleted while a docstring, a DESIGN.md
bullet or a test import still names it: the next session reads the
reference as an instruction, runs a file that is not there, and the
same defect class this sprint exists to fix comes straight back. So
this guard asserts both halves -- the paths are gone, AND no file under
`tools/` or `tests/` mentions them.

**Scope, and what is deliberately NOT scanned.** Only `tools/` and
`tests/`. `docs/` (in particular `docs/code-review/**`) and
`clasi/sprints/done/**` are DATED HISTORICAL RECORDS: a 2026-08-23 code
review that cites `tools/<file>.py:183` is a true statement about the
tree as it stood that day, and rewriting it to keep a grep quiet would
destroy the audit trail this repo's
`.claude/rules/measurement-citations.md` depends on -- the one thing
that lets a reader tell a real measurement from an invented one. Those
trees are read-only for this guard by design, not by oversight.

Run with::

    uv run pytest tests/tools/test_deleted_tools_stay_deleted.py
"""
import pathlib

import pytest

# tests/tools/test_deleted_tools_stay_deleted.py -> tools -> tests -> root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Stems of the deleted tools. Stems, not filenames: a reference in a
#: docstring or a Python `import` line drops the `.py`, and those are
#: exactly the references that read as live instructions.
DELETED_STEMS = ('truth_check', 'tour_square', 'tour_closedloop')

#: Only these two trees are scanned -- see the module docstring for why
#: `docs/` and `clasi/sprints/done/` are excluded.
SCANNED_ROOTS = ('tools', 'tests')

#: Text-ish suffixes worth scanning. Anything else under the two roots
#: (recorded CSVs, PNGs, captures) is data, not instruction.
_TEXT_SUFFIXES = {'.py', '.md', '.txt', '.json', '.cfg', '.toml', '.sh',
                  '.ts', '.tour'}


def _scanned_files():
    for root in SCANNED_ROOTS:
        for path in sorted((_REPO_ROOT / root).rglob('*')):
            if not path.is_file():
                continue
            if path.suffix not in _TEXT_SUFFIXES:
                continue
            if '__pycache__' in path.parts:
                continue
            if path == pathlib.Path(__file__).resolve():
                continue    # this guard names them on purpose
            yield path


@pytest.mark.parametrize('stem', DELETED_STEMS)
def test_the_deleted_tool_file_is_still_gone(stem):
    assert not (_REPO_ROOT / 'tools' / f'{stem}.py').exists(), (
        f'tools/{stem}.py is back; sprint 034 ticket 003 deleted it '
        f'because it was a trap, not because it was untidy')


@pytest.mark.parametrize('stem', DELETED_STEMS)
def test_no_tool_or_test_references_the_deleted_name(stem):
    hits = [str(p.relative_to(_REPO_ROOT)) for p in _scanned_files()
            if stem in p.read_text(errors='replace')]
    assert hits == [], (
        f'{stem!r} is named by {hits} -- that file no longer exists, so '
        f'the reference is an instruction to run something that is not '
        f'there. Reword the reference (the deletion rationale belongs '
        f'in tests/tools/test_deleted_tools_stay_deleted.py) rather '
        f'than restoring the file.')
