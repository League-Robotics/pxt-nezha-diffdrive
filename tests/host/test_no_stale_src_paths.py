"""tests/host/test_no_stale_src_paths.py -- a recurrence guard for
stale path references: prose (comments, docs) that names a `src/<path>`
file which no longer exists at that path, or a bare `main.ts` mention
in live source. `main.ts` was retired in sprint 012 (split across
`blocks/*.ts`); `src/` was regrouped into five dependency-layer
subdirectories (`core/`, `comms/`, `motion/`, `platform/`, `blocks/`)
in sprint 013. Sprint 013 ticket 006 was scoped as a "final sweep --
repo-wide stale-path verification" and 40+ stale references survived
it anyway, because the sweep was manual and left no mechanical guard
behind. This test is that guard.

Modeled directly on `test_pxt_manifest_completeness.py`: no compiler,
reads files as text, runs in milliseconds.

**What this catches.** Two independent, textually cheap checks:

1. Any `src/<path>.{h,cpp,ts}`-shaped substring in `src/`, `docs/`, or
   `tools/` prose must name a file that actually exists on disk,
   relative to the repo root. Sprint 013's own known offenders were
   exactly this shape: `src/otos_port.h` (moved to
   `src/platform/otos_port.h`), `src/wire_adapter.cpp` (moved to
   `src/comms/wire_adapter.cpp`), and so on -- a reader who copies the
   quoted path into their editor gets a "file not found," or worse,
   silently reads the wrong file if a same-named one exists elsewhere.
2. A bare `main.ts` mention (no `src/` prefix, since these are
   mid-sentence file mentions, e.g. "main.ts's block API") anywhere in
   `src/**/*.{h,cpp,ts}` or `tools/*.py`. `main.ts` does not exist in
   this tree at any path, so there is no "does it exist" check to run
   -- any live-source mention is definitionally stale. This check is
   intentionally scoped narrower than check 1: `docs/**/*.md` may
   legitimately describe the sprint-012 split in past tense (e.g.
   `src/DESIGN.md` sections 1 and 9 say "sprint 012: split from a
   single `main.ts`"), so `docs/` is excluded from this half of the
   guard -- a markdown design doc recounting history is not the same
   defect class as a C++/TS comment asserting a currently-reachable
   file.

**False-positive shapes, handled deliberately:**

- **Dated audit snapshots** (`docs/code-review/<YYYY-MM-DD>/...`) are
  excluded from check 1. These are point-in-time review reports that
  quote old paths as findings (e.g. "`motion_engine.h:135` cites
  `src/otos_port.h`, should be `src/platform/otos_port.h`") -- the
  quoted path is the historical evidence, not a live claim that the
  file is reachable there today. Rewriting these would corrupt the
  audit record; `docs/code-review/guidelines.md` itself (undated, the
  live standard) is NOT excluded by this rule, since the exclusion
  matches on a `YYYY-MM-DD` directory segment, not the whole
  `docs/code-review/` tree.
- **External-repo path prefixes** (`src/firm/`, `src/protocol/`) are
  excluded from check 1. This project's own `src/` has no `firm/` or
  `protocol/` subdirectory; these prefixes appear only in prose citing
  the upstream `League-Robotics/radio-robot` kernel repo's own tree
  (`src/firm/diffdrive/...`, vendored into this repo's
  `src/core/diffdrive.{h,cpp}`) and `radio-robot-lib`'s own tree
  (`src/protocol/adapter.h`, cited by `wire_handler.h` as the library
  this project's `Column` type parallels but does not share). A path
  scanner has no way to know "this `src/...` is a DIFFERENT repo's
  root" from text alone; an explicit, narrow prefix allowlist is more
  auditable than trying to infer it, and -- unlike a per-line
  allowlist -- doesn't rot when a comment's wording changes.
- **Fenced code blocks** (inside ` ``` `) are stripped before scanning
  markdown files. A path shown as part of a multi-line illustrative
  example (a hypothetical directory layout, a sample command) is not a
  claim that the path exists; a single-backtick inline path mention
  (the style this project actually uses for real citations, e.g.
  `` `src/heading_wrap.h` ``) is still scanned.

**What this deliberately does NOT do.** A stretch goal considered for
this ticket was extending the same idea to dangling *function* name
references (a comment citing `foo()` where no `foo` is defined or
called anywhere in the tree) -- the exact shape of the `formatDiag()`
defect this ticket also fixed by hand. A prototype (comment-stripped
code corpus, checked for `name\\(` anywhere in real code) found only 5
candidates out of 240 call-like mentions in comments across `src/` and
`tools/` -- but all 5 were false positives, and not the same kind of
false positive twice: `poseX()/Y()/heading()` shorthand (a `Y` picked
up mid-abbreviation, not a name), `uBit.init()` and
`NRF52I2C::waitForStop()` (real CODAL/nrf52 platform API, just not
defined in this repo), `onXxx()` (a deliberate generic placeholder
standing in for "any of the six `onWheelsV()`-shaped handlers"), and a
mention of the now-retired `formatDiag()` correctly reworded to say so
in the past tense. A stable allowlist for this check would need to grow
every time an engineer writes exactly the kind of comment this
project's own comment standard wants more of -- a measured hardware
quirk citing a vendor API by name (`nezha_port.cpp`'s bus-hang guard
citing `NRF52I2C::waitForStop()` is the canonical example). That cost
falls on the valuable comments, not the noise, so this check was not
shipped; the path-existence and bare-`main.ts` checks below are.

Run with::

    uv run pytest tests/host/test_no_stale_src_paths.py
"""

import pathlib
import re

# tests/host/test_no_stale_src_paths.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# `src/<path>.{h,cpp,ts}`-shaped substrings. Deliberately excludes
# `.md` (so `src/DESIGN.md` self-references never match) and requires
# a real source suffix, so prose that merely contains the word "src"
# (e.g. "source", "src=") never matches.
_PATH_PATTERN = re.compile(r"src/[A-Za-z0-9_./-]*\.(?:h|cpp|ts)")

# A dated snapshot directory anywhere under docs/code-review/ -- see
# the module docstring's "dated audit snapshots" note. Matches
# docs/code-review/2026-08-26/... but not docs/code-review/guidelines.md.
_DATED_AUDIT_DIR = re.compile(r"^docs/code-review/\d{4}-\d{2}-\d{2}/")

# Path prefixes naming a DIFFERENT repository's tree -- see the module
# docstring's "external-repo path prefixes" note.
_EXTERNAL_REPO_PREFIXES = ("src/firm/", "src/protocol/")

# Roots and suffixes check 1 (path existence) scans.
_PATH_CHECK_SCAN = {
    "src": (".h", ".cpp", ".ts", ".md"),
    "docs": (".md",),
    "tools": (".py", ".md"),
}

_MAIN_TS_PATTERN = re.compile(r"\bmain\.ts\b")

# Roots and suffixes check 2 (bare main.ts) scans -- live source only,
# no docs/. See the module docstring for why.
_MAIN_TS_CHECK_SCAN = {
    "src": (".h", ".cpp", ".ts"),
    "tools": (".py",),
}


def _strip_fenced_code_blocks(text: str) -> str:
    """Blank out the contents of ``` fenced blocks, preserving line
    numbers, so an illustrative example path isn't asserted to exist."""
    out_lines = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out_lines.append("")
            continue
        out_lines.append("" if in_fence else line)
    return "\n".join(out_lines)


def _iter_scan_files(scan_map):
    for root_name, suffixes in scan_map.items():
        root = _REPO_ROOT / root_name
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in suffixes:
                yield p


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def test_every_src_path_reference_exists_on_disk():
    """Every `src/<path>.{h,cpp,ts}`-shaped reference in `src/`,
    `docs/`, or `tools/` prose must name a file that exists on disk --
    otherwise a reader (or a future refactor) is trusting a path that
    silently stopped being true. See the module docstring for the
    three false-positive shapes this deliberately excludes."""
    failures = []
    for p in _iter_scan_files(_PATH_CHECK_SCAN):
        rel = p.relative_to(_REPO_ROOT).as_posix()
        if _DATED_AUDIT_DIR.match(rel):
            continue
        text = p.read_text(errors="ignore")
        if p.suffix == ".md":
            text = _strip_fenced_code_blocks(text)
        for m in _PATH_PATTERN.finditer(text):
            match = m.group(0)
            if any(match.startswith(pref) for pref in _EXTERNAL_REPO_PREFIXES):
                continue
            if not (_REPO_ROOT / match).exists():
                failures.append(f"{rel}:{_line_of(text, m.start())}: {match}")
    assert not failures, (
        "stale `src/<path>` reference(s) -- the named file does not exist "
        "on disk:\n" + "\n".join(failures)
    )


def test_no_bare_main_ts_mentions_in_live_source():
    """`main.ts` was retired in sprint 012 -- it does not exist at any
    path in this tree, so a bare mention (no `src/` prefix) in a live
    `.h`/`.cpp`/`.ts` or `tools/*.py` comment is always stale. `docs/`
    is deliberately out of scope for this check; see the module
    docstring."""
    failures = []
    for p in _iter_scan_files(_MAIN_TS_CHECK_SCAN):
        rel = p.relative_to(_REPO_ROOT).as_posix()
        text = p.read_text(errors="ignore")
        for m in _MAIN_TS_PATTERN.finditer(text):
            failures.append(f"{rel}:{_line_of(text, m.start())}")
    assert not failures, (
        "bare `main.ts` reference(s) in live source -- main.ts was retired "
        "in sprint 012 and does not exist at any path in this tree:\n"
        + "\n".join(failures)
    )
