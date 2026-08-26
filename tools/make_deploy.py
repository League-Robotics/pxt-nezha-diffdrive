#!/usr/bin/env python3
"""Build a flashable hex from the repo, in a scratch copy.

`pxt build` in the repo does NOT put the test program in the hex:
`test.ts` lives in `testFiles`, and it has to stay there, because a
`files`-listed test would run inside every student project that
installs this extension.

So deploys go through a scratch copy where `test/test.ts` is promoted
into `files`. That copy used to be maintained by hand, and it drifted:
it omitted `testrig.ts` entirely, which is how that file sat
uncompilable without anyone noticing. Generating it from the repo's own
manifest is the fix -- there is nothing left to forget to copy.

`test/testrig.ts` (the zeguz OTOS rig harness) is a SEPARATE, mutually
exclusive on-robot program from `test/test.ts` (the playfield robot) --
each has its own top-level `basic.forever` loop and button handlers, so
the two must never both land in one scratch copy's `files`; that would
compile both programs' top-level code into a single hex. `testrig.ts`
therefore gets checked in its OWN scratch copy (`--testrig`), generated
from the same `pxt.json` `testFiles` list, never combined with the
primary deploy.

  uv run python tools/make_deploy.py            # build
  uv run python tools/make_deploy.py --flash    # build, then flash vevov
  uv run python tools/make_deploy.py --testrig  # build/type-check
                                                 # testrig.ts alone, in
                                                 # its own scratch copy

Two traps this script exists to avoid, both of which cost hours:

* `disablesVariants: ["mbdal"]` is dropped. In a top-level project it
  produces a hex that is DEAD ON THE DEVICE. The repo keeps it (it is
  an extension, where it is fine and skips a pointless V1 build); the
  deploy copy must not. The price is a V1 `TS9283 program too big`
  error, which is expected and harmless.
* That TS9283 error aborts packaging NONDETERMINISTICALLY, and when it
  does it DELETES the hex rather than leaving a stale one. The hex is
  removed up front and its existence checked afterwards, so a failed
  package can never be mistaken for a good build.

**Build checkpoint triage (sprint 008).** `build()` used to only check
"does a hex exist" -- no distinction between "a `.cpp` failed to
compile" and "packaging aborted for an unrelated, retriable reason".
Three real target-only defects escaped the host suite because nothing
in the per-ticket/per-sprint flow required a real build
(`clasi/issues/host-tests-compile-newer-standard-than-target.md`); this
script is now the standing per-sprint build-checkpoint tool, and it
judges on "did any `.cpp`/`.h` fail to compile" (a real GCC/Clang
diagnostic naming a source file and a line), not on the packaging
abort's error code, which varies run to run and is not the defect
signal itself. Two abort shapes are known-benign and retried once,
automatically, before being reported as anything:

* The legacy V1 `bbc-microbit-classic-gcc` variant's own hex-merge step
  failing after a successful compile (`srec_cat: ... contradictory ...
  value`) -- this variant is not used to flash this hardware; only the
  codal-microbit-v2 variant's hex matters.
* The nondeterministic packaging abort, always after a pxt-core
  cache-write `TypeError [ERR_INVALID_ARG_TYPE]`, seen as `TS9283`
  ("program too big"), `TS9043` ("hex file is not available"), or
  `TS9200` -- always succeeded on retry, every time it has been seen.

The retry is bounded, not infinite: if the same benign shape recurs on
the retry and still produces no hex, that IS reported as a failure --
the two shapes are expected to be transient, not chronic. See
`tools/DESIGN.md`'s "Build checkpoint triage" section for the full
decision table (what is a hard failure, what is retried, and why), and
`classify_attempt()` below, which is unit-tested against saved/
synthetic build-log fixtures in
`tests/tools/test_make_deploy_triage.py` -- this logic can fail loudly
if someone breaks it later, the same theme sprint 008 applies
everywhere else.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(REPO, '.tmp', 'deploy-head')
HEX = os.path.join(DEPLOY, 'built', 'mbcodal-binary.hex')

# testrig.ts's own scratch copy -- NEVER the same directory as DEPLOY.
# See sync_testrig()/build_testrig() and the module docstring's mutual-
# exclusivity note.
DEPLOY_TESTRIG = os.path.join(REPO, '.tmp', 'deploy-testrig')
HEX_TESTRIG = os.path.join(DEPLOY_TESTRIG, 'built', 'mbcodal-binary.hex')

ELITE = '/Volumes/Proj/proj/RobotProjects/radio-robot-elite'

# --- build-output triage -------------------------------------------------
#
# A genuine GCC/Clang compile diagnostic names a source file and a line,
# e.g.:
#   src/comms/wire_adapter.cpp:12:10: fatal error: heading_wrap.h: No such
#     file or directory
#   src/comms/wire_handler.cpp:214:37: error: no matching function for call
#     to 'Wire::Column::Column(<brace-enclosed initializer list>)'
# This also catches a `pxt.json` manifest omission: a missing header
# fails as "file not found" at the #include site, in the same
# file:line:diagnostic shape -- there is no separate manifest-checking
# code path here on purpose (see tools/DESIGN.md).
_COMPILE_ERROR_RE = re.compile(
    r'^\s*[^\s:]+\.(?:cpp|cc|cxx|h|hpp):\d+:(?:\d+:)?\s*'
    r'(?:fatal error|error):',
    re.MULTILINE,
)

# The legacy V1 bbc-microbit-classic-gcc variant's own hex-merge step
# fails after a successful compile -- srec_cat rejects two regions that
# disagree. This variant is not used to flash this hardware.
_V1_HEXMERGE_RE = re.compile(r'srec_cat:.*contradictory', re.IGNORECASE)

# The nondeterministic packaging abort, always after a pxt-core
# cache-write `TypeError [ERR_INVALID_ARG_TYPE]`; the abort code itself
# varies between runs and is not the defect signal.
_PACKAGING_ABORT_RE = re.compile(r'\bTS9283\b|\bTS9043\b|\bTS9200\b')

# classify_attempt() verdicts.
SUCCESS = 'success'
HARD_FAILURE = 'hard_failure'
BENIGN = 'benign'
UNKNOWN = 'unknown'


def classify_attempt(output, hex_exists):
    """Decide what one `pxt build` attempt means. Pure function, no
    subprocess -- unit-tested directly against saved/synthetic build
    logs (`tests/tools/test_make_deploy_triage.py`).

    Returns ``(verdict, reason)``. ``verdict`` is one of ``SUCCESS``,
    ``HARD_FAILURE``, ``BENIGN``, or ``UNKNOWN``.

    The rule, from the issue this triage closes: judge on "did any
    `.cpp`/`.h` fail to compile", not the packaging abort's error code.
    So a real compile diagnostic is checked FIRST and wins regardless
    of whether a hex happens to exist -- a hex from one build variant
    plus a compile error in another is still a hard failure, not a
    success. Only once no compile diagnostic is present does hex
    existence, then the two known-benign abort shapes, decide the rest.
    An output that matches none of these (no hex, no compile
    diagnostic, no known benign shape) is UNKNOWN -- treated as a
    failure and NOT retried, deliberately failing closed rather than
    risk silently retrying past a real, just-unrecognized defect. See
    tools/DESIGN.md for the honesty note this implies.
    """
    m = _COMPILE_ERROR_RE.search(output)
    if m:
        # Report the whole diagnostic line, not just the matched
        # prefix -- "compile error: <prefix>" alone drops the file
        # name and message text that make the failure actionable.
        line_start = output.rfind('\n', 0, m.start()) + 1
        line_end = output.find('\n', m.end())
        if line_end == -1:
            line_end = len(output)
        return HARD_FAILURE, 'compile error: ' + output[line_start:line_end].strip()
    if hex_exists:
        return SUCCESS, ''
    if _V1_HEXMERGE_RE.search(output):
        return (BENIGN,
                'legacy V1 hex-merge failure (srec_cat contradictory value)')
    if _PACKAGING_ABORT_RE.search(output):
        return (BENIGN,
                'nondeterministic packaging abort (TS9283/TS9043/TS9200)')
    return (UNKNOWN,
            'no hex, no compile diagnostic, no known benign shape matched')


def _select_promoted(manifest, promote_name):
    """Pure function: which `testFiles` entries get promoted into
    `files` for one scratch copy. Matches on exact basename, not
    `endswith()` -- `'test/testrig.ts'.endswith('test.ts')` is False
    (it ends in `'trig.ts'`), which is what let `testrig.ts` silently
    vanish from the old filter in the first place; basename equality
    is unambiguous instead of relying on a lucky non-collision. Kept
    separate from `_sync_scratch()`'s file-copying I/O so this
    selection logic is directly unit-testable against a manifest
    fixture with no files on disk and no repo checkout
    (`tests/tools/test_make_deploy_triage.py`)."""
    return [f for f in manifest.get('testFiles', [])
            if os.path.basename(f) == promote_name]


def _sync_scratch(deploy_dir, promote_name):
    """Generate a scratch copy of the repo at `deploy_dir`, fresh from
    `pxt.json` every call -- nothing here is hand-curated, so a
    declared `testFiles` entry cannot again silently go stale the way
    `testrig.ts` did (see module docstring). Promotes exactly the
    `testFiles` entry named `promote_name` (e.g. `'test.ts'` or
    `'testrig.ts'`) into `files`; every other `testFiles` entry is left
    out. `test.ts` and `testrig.ts` are independent, mutually exclusive
    on-robot programs and must never both be promoted into one scratch
    copy's `files` -- callers each promote exactly one (see `sync()` /
    `sync_testrig()`)."""
    manifest = json.load(open(os.path.join(REPO, 'pxt.json')))
    os.makedirs(deploy_dir, exist_ok=True)

    # node_modules by symlink (big); pxt_modules by copy (pxt writes it)
    link = os.path.join(deploy_dir, 'node_modules')
    if not os.path.islink(link):
        if os.path.exists(link):
            shutil.rmtree(link)
        os.symlink(os.path.join(REPO, 'node_modules'), link)
    dst = os.path.join(deploy_dir, 'pxt_modules')
    if not os.path.exists(dst):
        shutil.copytree(os.path.join(REPO, 'pxt_modules'), dst)

    # Every file the repo declares, at its declared path, plus the one
    # test program promoted so the hex actually has its button/RUN
    # handlers.
    files = list(manifest['files'])
    promoted = _select_promoted(manifest, promote_name)
    for rel in files + promoted:
        src = os.path.join(REPO, rel)
        out = os.path.join(deploy_dir, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(src, out)

    manifest['files'] = files + promoted
    manifest['testFiles'] = []
    manifest.pop('disablesVariants', None)      # see module docstring
    json.dump(manifest, open(os.path.join(deploy_dir, 'pxt.json'), 'w'),
              indent=4)
    return files + promoted


def sync():
    """The routine flashable deploy: `test.ts` promoted alone. Behavior
    unchanged from before this ticket."""
    return _sync_scratch(DEPLOY, 'test.ts')


def sync_testrig():
    """`testrig.ts`'s own scratch copy: `testrig.ts` promoted alone,
    NEVER together with `test.ts` (see module docstring / `_sync_scratch()`).
    This is what makes `testrig.ts` "built/type-checked as part of some
    routine, automated path" again -- run via `--testrig`, not a
    hand-maintained copy."""
    return _sync_scratch(DEPLOY_TESTRIG, 'testrig.ts')


def _run_pxt_build(deploy_dir=None, hex_path=None):
    """Run one `pxt build` attempt in `deploy_dir` against `hex_path`
    (both default to the primary flashable scratch, DEPLOY/HEX --
    `build_testrig()` passes DEPLOY_TESTRIG/HEX_TESTRIG instead),
    streaming its output live (a cloud build can take a while) while
    also capturing it for classify_attempt(). Removes any pre-existing
    hex first, so a build that aborts mid-package can never be mistaken
    for a stale-but-good one (see the TS9283 note in this file's module
    docstring)."""
    if deploy_dir is None:
        deploy_dir = DEPLOY
    if hex_path is None:
        hex_path = HEX
    if os.path.exists(hex_path):
        os.remove(hex_path)
    proc = subprocess.Popen(
        ['pxt', 'build'], cwd=deploy_dir,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lines = []
    for line in proc.stdout:
        print(line, end='')
        lines.append(line)
    proc.wait()
    return ''.join(lines)


def build(run_fn=None, hex_path=None, label=''):
    """Run one triage-checked build. `run_fn`/`hex_path` default to the
    primary flashable deploy (DEPLOY/HEX -- via the module-level
    `_run_pxt_build`, looked up here rather than bound as a default
    argument so tests that monkeypatch `make_deploy._run_pxt_build`
    still take effect), so every existing call site and test
    (`tests/tools/test_make_deploy_triage.py`) is unaffected;
    `build_testrig()` passes the testrig-scratch equivalents instead.
    `classify_attempt()` itself -- the triage -- is untouched by this;
    this only wires which build output/hex path it judges."""
    if run_fn is None:
        run_fn = _run_pxt_build
    if hex_path is None:
        hex_path = HEX
    output = run_fn()
    verdict, reason = classify_attempt(output, os.path.exists(hex_path))
    attempt = 1
    if verdict == BENIGN:
        print(f'\n[triage] {label}attempt 1: known-benign abort ({reason}) -- '
              'retrying once, per tools/DESIGN.md')
        output = run_fn()
        verdict, reason = classify_attempt(output, os.path.exists(hex_path))
        attempt = 2
        if verdict == BENIGN:
            # Bounded retry, not infinite: the shape is expected to be
            # transient, not chronic -- recurring on the retry IS now
            # a failure.
            verdict = HARD_FAILURE
            reason = f'benign abort recurred on retry ({reason}) -- retry exhausted'
    if verdict != SUCCESS:
        sys.exit(f'\n{label}BUILD FAILED on attempt {attempt}: {reason}\n'
                 'See the raw pxt output above for detail.')
    print(f'\n{label}hex: {hex_path}  ({os.path.getsize(hex_path)} bytes)  [attempt {attempt}]')


def build_testrig():
    """`testrig.ts`'s own build/type-check pass, on its own terms (see
    `sync_testrig()`) -- never combined with the primary `test.ts`
    deploy in one scratch copy. Reuses `build()`'s existing triage
    (retry-once-on-benign, fail closed on unknown) unchanged; this
    scratch hex is not meant to be flashed (Implementation Notes: no
    `flash()` support required here)."""
    build(run_fn=lambda: _run_pxt_build(DEPLOY_TESTRIG, HEX_TESTRIG),
          hex_path=HEX_TESTRIG, label='testrig ')


def flash(name):
    r = subprocess.run(['mbdeploy', 'deploy', name, '--hex', HEX],
                       cwd=ELITE)
    if r.returncode != 0:
        print('\nmbdeploy failed. The proven fallback is DAPLink mass '
              'storage: match the board UID in /Volumes/MICROBIT*/'
              'DETAILS.TXT and copy the hex onto that drive.')
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--flash', action='store_true')
    ap.add_argument('--robot', default='vevov')
    ap.add_argument('--testrig', action='store_true',
                     help="build/type-check test/testrig.ts alone, in "
                          "its own scratch copy -- never combined with "
                          "the primary test.ts deploy (see module "
                          "docstring); produces no flashable hex")
    a = ap.parse_args()
    if a.testrig:
        if a.flash:
            ap.error('--testrig produces no flashable hex; '
                      '--flash is not supported with it')
        for f in sync_testrig():
            print(f'  {f}')
        build_testrig()
        return
    for f in sync():
        print(f'  {f}')
    build()
    if a.flash:
        flash(a.robot)


if __name__ == '__main__':
    main()
