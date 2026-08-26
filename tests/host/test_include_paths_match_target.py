"""tests/host/test_include_paths_match_target.py -- mechanical gate:
every `#include "..."` under `src/` must resolve relative to its OWN
including file's directory, exactly like the real PXT build's include
resolution. PXT stages every file at its own `pxt.json`-relative path
(it never flattens `src/` into one directory) and never passes a
project-root `-I`, so the C/C++ preprocessor's quote-include search only
ever checks the including file's own directory -- there is no
project-root base to qualify an include against.

This is a pure filesystem check with no compiler dependency, in the
spirit of `test_cxx11_syntax_gate.py` and
`test_pxt_manifest_completeness.py`. It covers EVERY `#include` under
`src/`, including files no host test compiles at all (the pxt.h-bound
ones: protocol.cpp/radio_transport.cpp/serial_transport.cpp/
nezha_port.{h,cpp}/otos_port.{h,cpp}/shims.cpp) -- test_kernel_harness.py's
compile_shared_lib() (sprint 017 ticket 009) only proves the rule for
the handful of production sources some host test actually links; this
gate proves it for the whole tree, cheaply and deterministically.

Filed against host-harness-masks-include-path-errors.md
(clasi/sprints/017-.../issues/), which documents the rule and the three
observed failure shapes:

    | includer                        | target                   | correct form              |
    |----------------------------------|--------------------------|----------------------------|
    | src/otos_port.h (root-level)     | src/core/diffdrive.h     | "core/diffdrive.h"        |
    | src/core/diffdrive.cpp           | src/core/diffdrive.h     | "diffdrive.h"             |
    | src/motion/motion_engine.h       | src/core/diffdrive.h     | "../core/diffdrive.h"     |

One rule predicts all three: for an `#include "X"` in a file at
directory D, `(D / X)` must resolve to a file that exists.

`pxt.h` is the one deliberate exception: it is not authored under
`src/` at all -- it ships with the `core` dependency declared in
`pxt.json` (see `pxt_modules/core/pxt.h`) and PXT resolves it through
that dependency's own include path, a real and separate mechanism from
the project-root `-I` this gate is about. `test_cxx11_syntax_gate.py`'s
own docstring notes the same files depend on pxt.h and are out of reach
of a host-only check for the same reason.

Run with::

    uv run pytest tests/host/test_include_paths_match_target.py
"""

import pathlib
import re

import pytest

# tests/host/test_include_paths_match_target.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"

# A real preprocessor directive line only: `#` must be the first
# non-whitespace character. This deliberately does NOT match e.g.
# src/comms/radio_transport.h's `// #include "wire_handler.h" (the same
# layering reason...)` comment, since that line's first non-whitespace
# characters are `//`, not `#`.
_INCLUDE_RE = re.compile(r'^\s*#include\s+"([^"]+)"')

_CXX_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}

# Headers that ship with a declared pxt.json dependency (not authored
# under src/) and are resolved through that dependency's own include
# path in a real build -- see module docstring.
_EXTERNAL_HEADERS = {"pxt.h"}


def _iter_cxx_files():
    return sorted(p for p in _SRC_DIR.rglob("*") if p.suffix in _CXX_SUFFIXES)


def _iter_quote_includes(path):
    """Yield (line_number, included_path_text) for every #include "..."
    directive in `path`."""
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        match = _INCLUDE_RE.match(line)
        if match:
            yield lineno, match.group(1)


def _collect_cases():
    cases = []
    for source in _iter_cxx_files():
        for lineno, included in _iter_quote_includes(source):
            if included in _EXTERNAL_HEADERS:
                continue
            cases.append((source, lineno, included))
    return cases


_CASES = _collect_cases()


@pytest.mark.parametrize(
    "source,lineno,included",
    _CASES,
    ids=[
        f"{s.relative_to(_SRC_DIR).as_posix()}:{ln}:{inc}"
        for s, ln, inc in _CASES
    ],
)
def test_include_resolves_relative_to_including_file(source, lineno, included):
    """The real PXT build resolves `#include "X"` relative to the
    including file's OWN directory -- there is no project-root -I in a
    real build. Assert that `(source.parent / included)` actually exists
    on disk: the same rule host-harness-masks-include-path-errors.md's
    CORRECTION section establishes, and the one
    test_kernel_harness.py's compile_shared_lib() now enforces at
    compile time (sprint 017 ticket 009) for the production sources some
    host test links. This test adds zero-compiler coverage of EVERY
    include under src/, including files no host test compiles at all.
    """
    resolved = (source.parent / included).resolve()
    assert resolved.is_file(), (
        f'{source.relative_to(_REPO_ROOT)}:{lineno}: #include "{included}" '
        f"does not resolve relative to its own directory "
        f"({source.parent / included}) -- the real PXT build has no "
        f"project-root -I, so this include would fail a real build even "
        f"if it happens to compile host-side under a more permissive "
        f"search path."
    )


def test_at_least_one_include_was_checked():
    """A guard against the parser itself silently finding nothing --
    the same concern test_pxt_manifest_completeness.py's own docstring
    raises about a check that trivially always passes because it
    iterates zero items."""
    assert len(_CASES) > 0
