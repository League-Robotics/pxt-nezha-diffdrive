"""tests/host/test_pxt_manifest_completeness.py -- a recurrence guard for
a manifest-omission defect: `pxt.json`'s `files` list controls exactly
what PXT copies into a build (local yotta/ninja for the legacy V1
variant, the cloud codal-microbit-v2 compile for the shipping one).
A `src/*.h`/`*.cpp` file that exists, compiles, and is `#include`d by
shipped code, but is missing from `files`, silently never reaches
either build -- the failure only ever shows up as a build-time "file
not found" from whichever *other* file includes it, at build time, not
at any point tests/host/ can see.

**What this catches, and why nothing else does.** Sprint 007 ticket 006
found `pxt.json`'s `files` list omitted three headers sprint 006 added
(`src/heading_wrap.h`, `src/encoder_glitch_armor.h`,
`src/encoder_pose_source.h`) -- all three exist, compile (each has its
own `tests/host/*_syntax_check.cpp` translation unit, covered by
`test_cxx11_syntax_gate.py`), and are `#include`d by shipped `.cpp`/`.h`
files, so this project could not produce a hex at all until the
manifest was fixed. `test_cxx11_syntax_gate.py` compiles named
translation units directly and never reads `pxt.json`, so a manifest
omission is invisible to it -- a file can be perfectly valid C++11 and
still never ship. This test reads `pxt.json` itself instead of
compiling anything, so it is cheap (no compiler invocation) and catches
the actual defect class: manifest drift, not source-file correctness.

**Scope, deliberately narrow.** This only compares `src/*.h`/`*.cpp`
against `pxt.json`'s `files` array -- not `testFiles` (a file there is
deliberately excluded from `files`; see `test/testrig.ts`'s own
promotion story in `tools/make_deploy.py`), and not `test/*.ts` (no
comparable defect has been observed there). It flags in both
directions: a file on disk that `files` omits (the sprint 006 defect),
and an entry in `files` naming a file that no longer exists on disk (a
stale manifest referencing a deleted or renamed file) -- both are the
same underlying problem, a `files` list that has drifted from `src/`'s
actual contents.

This does not replace `test_cxx11_syntax_gate.py`: that gate proves a
file compiles at the target's language standard; this one proves a
file that compiles is actually reachable by the build. Filed against
the broader defect class in `host-tests-compile-newer-standard-than-
target.md` (sprint 008) is the *language-standard* gap; this test is a
narrow, unrelated, much cheaper down payment on the *manifest* gap that
gate cannot see.

Run with::

    uv run pytest tests/host/test_pxt_manifest_completeness.py
"""

import json
import pathlib

# tests/host/test_pxt_manifest_completeness.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_PXT_JSON = _REPO_ROOT / "pxt.json"

# Source file suffixes PXT actually compiles/bundles from src/. src/
# also holds DESIGN.md (documentation, not manifest-listed by design)
# -- deliberately not in this list.
_SOURCE_SUFFIXES = (".h", ".cpp", ".ts")


def _load_manifest_files():
    manifest = json.loads(_PXT_JSON.read_text())
    return manifest["files"]


def _src_files_on_disk():
    return sorted(
        f"src/{p.relative_to(_SRC_DIR).as_posix()}"
        for p in _SRC_DIR.rglob("*")
        if p.is_file() and p.suffix in _SOURCE_SUFFIXES
    )


def test_every_src_file_is_manifest_listed():
    """Every `src/*.h`/`*.cpp`/`*.ts` file on disk must appear in
    `pxt.json`'s `files` array. A file that exists, compiles, and is
    `#include`d by shipped code but is missing here never reaches
    either build target -- the exact defect this ticket found for
    `heading_wrap.h`, `encoder_glitch_armor.h`, and
    `encoder_pose_source.h`."""
    files_listed = set(_load_manifest_files())
    on_disk = _src_files_on_disk()
    missing = [f for f in on_disk if f not in files_listed]
    assert not missing, (
        f"src/ file(s) exist on disk but are missing from pxt.json's "
        f"files[] -- PXT will never copy them into a build: {missing}"
    )


def test_no_manifest_entry_is_stale():
    """Every `src/...`-prefixed entry in `pxt.json`'s `files` array
    must name a file that actually exists. A stale entry (naming a
    deleted or renamed file) is the same manifest-drift defect class
    in the other direction."""
    files_listed = _load_manifest_files()
    stale = [
        f
        for f in files_listed
        if f.startswith("src/") and not (_REPO_ROOT / f).exists()
    ]
    assert not stale, (
        f"pxt.json's files[] names file(s) that do not exist on disk: "
        f"{stale}"
    )
