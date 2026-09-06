"""The documented list of `pxt.h`-bound translation units must match the
tree. `tests/DESIGN.md` "Translation units nothing on the host compiles"
names every `.cpp` under `src/` that no host test can compile and says
what gates it instead; this re-derives that set from the source and
fails when the two disagree, so a ninth such file cannot land silently
uncovered.

Include resolution follows the real PXT build's rule -- an
`#include "X"` in a file at directory D resolves as `(D / X)`, with no
project-root `-I` -- the same rule
`test_include_paths_match_target.py` enforces over the whole tree.
`pxt.h` itself is the deliberate exception: it is not authored under
`src/` at all, it arrives with the `core` dependency declared in
`pxt.json`, and reaching it is exactly what disqualifies a file from
being host-compilable.

Run with::

    uv run pytest tests/host/test_pxt_bound_exclusion_is_current.py
"""

import pathlib
import re

import pytest

# tests/host/test_pxt_bound_exclusion_is_current.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_DESIGN_DOC = _REPO_ROOT / "tests" / "DESIGN.md"

_SECTION_HEADING = "## Translation units nothing on the host compiles"

# A real preprocessor directive line only -- `#` must be the first
# non-whitespace character, so a commented-out include does not count.
_INCLUDE_RE = re.compile(r'^\s*#include\s+"([^"]+)"', re.M)

# The first cell of a table row, when it is a single backticked path:
# `| \`comms/protocol.cpp\` | ... | ... |`.
_ROW_FIRST_CELL_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def _reaches_pxt_h(start: pathlib.Path) -> bool:
    """True if `start` includes "pxt.h" directly, or through any header
    reachable from it by the target's own quote-include rule."""
    seen: set[pathlib.Path] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            text = current.read_text()
        except OSError:
            continue
        for include in _INCLUDE_RE.findall(text):
            if include == "pxt.h":
                return True
            resolved = current.parent / include
            if resolved.is_file():
                stack.append(resolved)
    return False


def _pxt_bound_sources_in_tree() -> set[str]:
    """Every `.cpp` under `src/` that reaches `pxt.h`, as a path
    relative to `src/`."""
    return {
        str(cpp.relative_to(_SRC_DIR))
        for cpp in _SRC_DIR.rglob("*.cpp")
        if _reaches_pxt_h(cpp)
    }


def _documented_exclusions() -> set[str]:
    """The first column of the exclusion table in tests/DESIGN.md."""
    text = _DESIGN_DOC.read_text()
    start = text.find(_SECTION_HEADING)
    assert start != -1, (
        f"{_DESIGN_DOC} has no section titled {_SECTION_HEADING!r}. That "
        f"section is the documented exclusion this test holds against the "
        f"tree (sprint 034 ticket 011); without it nothing records why "
        f"these files are uncompiled."
    )
    end = text.find("\n## ", start + len(_SECTION_HEADING))
    section = text[start : end if end != -1 else len(text)]

    documented = set()
    for line in section.splitlines():
        match = _ROW_FIRST_CELL_RE.match(line)
        if match:
            documented.add(match.group(1))
    return documented


def test_documented_exclusion_matches_the_tree():
    """The table names exactly the `pxt.h`-bound `.cpp` files that
    exist, no more and no fewer."""
    in_tree = _pxt_bound_sources_in_tree()
    documented = _documented_exclusions()

    undocumented = sorted(in_tree - documented)
    stale = sorted(documented - in_tree)

    assert not undocumented, (
        f"{sorted(undocumented)} reach pxt.h and so are compiled by "
        f"nothing on the host, but {_DESIGN_DOC.name}'s "
        f"{_SECTION_HEADING!r} table does not name them. Add a row saying "
        f"what binds each to the target and what gates it instead -- or "
        f"extract the host-portable half into a header the C++11 gate "
        f"already covers, which is what the rest of that table's "
        f"right-hand column records."
    )
    assert not stale, (
        f"{sorted(stale)} are named in {_DESIGN_DOC.name}'s "
        f"{_SECTION_HEADING!r} table but no longer reach pxt.h (or no "
        f"longer exist). If one became host-portable, drop its row and "
        f"add it to test_cxx11_syntax_gate.py's compile list instead."
    )


def test_documented_exclusions_are_absent_from_the_cxx11_gate():
    """Neither list may claim a file the other one claims. A file in
    the C++11 gate is compiled on the host; a file in the exclusion
    table is compiled by nothing."""
    import test_cxx11_syntax_gate

    gated = {
        str(source.resolve())
        for source in test_cxx11_syntax_gate._CXX11_PORTABLE_SOURCES
    }
    overlap = sorted(
        name
        for name in _documented_exclusions()
        if str((_SRC_DIR / name).resolve()) in gated
    )
    assert not overlap, (
        f"{overlap} appear both in tests/DESIGN.md's exclusion table and "
        f"in test_cxx11_syntax_gate.py's compile list. Exactly one of "
        f"those is right."
    )


@pytest.mark.parametrize(
    "name", sorted(_documented_exclusions()), ids=lambda n: n
)
def test_each_documented_exclusion_exists(name):
    """A row naming a file that is not there is worse than no row: it
    reads as coverage of something that moved."""
    assert (_SRC_DIR / name).is_file(), (
        f"tests/DESIGN.md names src/{name} as pxt.h-bound, but that file "
        f"does not exist."
    )
