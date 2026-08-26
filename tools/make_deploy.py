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

  uv run python tools/make_deploy.py            # build (vevov, ch 4)
  uv run python tools/make_deploy.py --flash    # build, then flash vevov
  uv run python tools/make_deploy.py --robot tovez --flash
                                                 # build for tovez's own
                                                 # radio channel, then
                                                 # flash tovez
  uv run python tools/make_deploy.py --testrig  # build/type-check
                                                 # testrig.ts alone, in
                                                 # its own scratch copy

`--robot` selects more than the flash target: after `sync()` populates
the scratch copy, this script reads the target robot's own
`connection.radio_channel` from radio-robot-lib's canonical per-robot
config (`radio-robot-lib/config/robots/<robot>.json`) and substitutes
it into the SCRATCH COPY's `src/comms/radio_transport.h` before
`build()` runs -- see `_inject_radio_channel()` below. This repo's own
checked-in source is never touched, so it keeps one fixed default
(vevov's own channel, 4); a build invoked with no `--robot` is
therefore byte-equivalent to a build invoked with `--robot vevov`, both
before and after this behavior existed. No robot->channel table lives
in this repo -- radio-robot-lib's JSON is the only place a channel
number is read from, and a missing/unreadable/incomplete config fails
the build loudly rather than falling back to any default.

The same seam also carries the target robot's own NAME into the
SCRATCH COPY's `src/comms/protocol.cpp` `kProfile` constant -- see
`_inject_profile()` below. Unlike the channel, this ENDS the "no
`--robot` is byte-equivalent to before" property: `protocol.cpp`'s
checked-in `kProfile` is deliberately an un-baked placeholder, not any
fleet robot's name (see that file's own comment), so every build --
including the `DEFAULT_ROBOT` one -- now differs from the checked-in
source once baked. That is the fix: before this existed, `kProfile`
was a hand-written constant frozen fleet-wide at `"tovez"`, so every
board (including vevov) reported `"tovez"` over the wire `ID` verb.
`_inject_profile()` confirms the target robot has a real config file in
radio-robot-lib before baking (same loud-failure posture as
`_read_robot_radio_channel()`), but reads no field out of it -- the
value baked is the config's own filename stem, per the reference design
in `radio-robot-elite/src/firm/main.cpp`.

The same scratch-copy substitution mechanism also carries this repo's
own version (read from `pyproject.toml`'s `0.YYYYMMDD.n`, reformatted
to the on-device `DD.RR` banner string) and the target robot's name
into `test/test.ts`'s scratch copy, so the boot banner it displays can
report which build and which robot a flashed hex actually is -- see
`_inject_boot_banner()` below. `test.ts` cannot read `pyproject.toml`
at build time (no filesystem access once compiled), so this is the
only place that string can come from.

Two traps this script exists to avoid, both of which cost hours:

* `disablesVariants: ["mbdal"]` is dropped. In a top-level project it
  produces a hex that is DEAD ON THE DEVICE. The repo keeps it (it is
  an extension, where it is fine and skips a pointless V1 build); the
  deploy copy must not.
* Packaging can still abort NONDETERMINISTICALLY (the `TS9283`/
  `TS9043`/`TS9200` shape below), and when it does it DELETES the hex
  rather than leaving a stale one. The hex is removed up front and its
  existence checked afterwards, so a failed package can never be
  mistaken for a good build.

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
signal itself. One abort shape is known-benign and retried once,
automatically, before being reported as anything:

* The nondeterministic packaging abort, always after a pxt-core
  cache-write `TypeError [ERR_INVALID_ARG_TYPE]`, seen as `TS9283`
  ("program too big"), `TS9043` ("hex file is not available"), or
  `TS9200` -- always succeeded on retry, every time it has been seen.

The retry is bounded, not infinite: if the same benign shape recurs on
the retry and still produces no hex, that IS reported as a failure --
the shape is expected to be transient, not chronic.

**Sprint 014: V1 is no longer built at all.**
`PXT_COMPILE_SWITCHES=csv-mbcodal` (set unconditionally in
`_run_pxt_build()`'s subprocess environment) selects
`appTargetVariant=mbcodal` before any variant-dependency filtering
runs, so the legacy V1 `bbc-microbit-classic-gcc` variant is never
compiled under this script -- see
`clasi/issues/never-build-the-v1-mbdal-variant.md` for the measured
mechanism. Its old hex-merge failure (`srec_cat: ... contradictory ...
value`) is therefore no longer a known-benign shape: if it is ever seen
again, `classify_attempt()` reports it as `UNKNOWN` (a hard failure,
no retry), because it can now only mean the switch silently failed to
take effect, not an expected, transient trap. See
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
# Single-variant output path: PXT_COMPILE_SWITCHES=csv-mbcodal (see
# _run_pxt_build()) makes pxt-core produce built/binary.hex, not the
# old multi-variant built/mbcodal-binary.hex. See build()'s block-
# marker assertion below -- this filename alone does not prove which
# kind of hex (plain V2 vs. universal V1+V2) actually landed here.
HEX = os.path.join(DEPLOY, 'built', 'binary.hex')

# testrig.ts's own scratch copy -- NEVER the same directory as DEPLOY.
# See sync_testrig()/build_testrig() and the module docstring's mutual-
# exclusivity note.
DEPLOY_TESTRIG = os.path.join(REPO, '.tmp', 'deploy-testrig')
HEX_TESTRIG = os.path.join(DEPLOY_TESTRIG, 'built', 'binary.hex')

ELITE = '/Volumes/Proj/proj/RobotProjects/radio-robot-elite'

# radio-robot-lib's own per-robot config tree -- the fleet's one
# canonical source for facts like a robot's assigned radio channel
# (see _read_robot_radio_channel() below). A sibling checkout, same
# convention as ELITE above.
RADIO_ROBOT_LIB = '/Volumes/Proj/proj/RobotProjects/radio-robot-lib'

# Matches sync()/main()'s own pre-existing default -- factored out so
# _inject_radio_channel()'s tests and main()'s argparse default cannot
# drift apart.
DEFAULT_ROBOT = 'vevov'

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
    existence, then the known-benign abort shape, decide the rest.
    An output that matches none of these (no hex, no compile
    diagnostic, no known benign shape) is UNKNOWN -- treated as a
    failure and NOT retried, deliberately failing closed rather than
    risk silently retrying past a real, just-unrecognized defect. This
    is also where a resurrected legacy V1 `bbc-microbit-classic-gcc`
    hex-merge failure (`srec_cat: ... contradictory ... value`) now
    lands: under `PXT_COMPILE_SWITCHES=csv-mbcodal` V1 is never built,
    so that shape is no longer an expected, retry-worthy trap -- it can
    only mean the switch silently failed to take effect, which must
    fail hard, not retry
    (`clasi/issues/never-build-the-v1-mbdal-variant.md`). See
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
    if _PACKAGING_ABORT_RE.search(output):
        return (BENIGN,
                'nondeterministic packaging abort (TS9283/TS9043/TS9200)')
    return (UNKNOWN,
            'no hex, no compile diagnostic, no known benign shape matched')


# `built/binary.hex` is ambiguous by filename alone once
# PXT_COMPILE_SWITCHES=csv-mbcodal is in play: a universal (V1+V2) hex
# from the old multi-variant build and a plain V2 hex from the
# single-variant build are byte-for-byte different artifacts that share
# this one path. A universal hex brackets each variant's program data
# with a `:0400000A` extended-linear-address record (one pair per
# variant); a plain single-variant hex has none. See build()'s use of
# this below and tools/DESIGN.md.
_UNIVERSAL_HEX_BLOCK_MARKER = ':0400000A'


def _count_universal_hex_blocks(hex_text):
    """Pure function, no I/O: counts `:0400000A` universal-hex
    block-start markers in a hex file's already-read text. 0 means a
    plain V2 hex; a nonzero count means a universal hex slipped through
    -- PXT_COMPILE_SWITCHES=csv-mbcodal did not take effect. Mirrors
    classify_attempt()/_select_promoted()'s separation of pure logic
    from the I/O that feeds it, so this is directly unit-testable
    against fixture text with no build, no subprocess, no filesystem
    (`tests/tools/test_make_deploy_triage.py`)."""
    return hex_text.count(_UNIVERSAL_HEX_BLOCK_MARKER)


# --- hex size floor and translation-unit presence check --------------------
#
# Both close the same gap: `classify_attempt()` and
# `_count_universal_hex_blocks()` judge a build from its LOG and its
# hex's INTEL-HEX CONTENT, but a build served entirely (or partly) from
# a stale `.tmp/deploy-head/built/dockercodal` cache can print a clean
# log, exit 0, and still produce a real, well-formed, but SHORT hex --
# nothing above catches that.
#
# Measured `built/binary.hex` sizes for a genuine, fully-compiled build,
# read with `stat -f%z` (not inferred from the log), across a series of
# build checkpoints over time: 1,423,241 / 1,434,671 / 1,442,546 /
# 1,442,996 / 1,448,621 / 1,463,606 / 1,463,516 bytes -- a tight,
# slowly-growing band: measured low 1,423,241, measured high 1,463,606.
# The stale-cache defect this check exists to catch has produced a hex
# of 1,046,410 bytes -- 27% short of the band, clean exit, nothing in
# the log to flag it. The floor below is set roughly midway between
# that truncated hex and the band's low end -- about 250 KB above the
# former, about 120 KB below the latter -- so it has real margin on
# both sides without having to track the band's slow growth release
# over release.
MIN_HEX_SIZE_BYTES = 1_300_000

# The ten nezha-diffdrive translation units, as `find src -name
# '*.cpp'` reports them (repo-relative, forward slashes). A literal
# list, not a filesystem scan performed at check time: a real build log
# is checked against what this repo is KNOWN to compile, so an 11th
# `.cpp` file added without updating this list shows up as a gap
# between what was expected and what compiled, worth noticing, rather
# than the check silently widening to match whatever happens to be on
# disk.
EXPECTED_CPP_FILES = [
    'src/comms/protocol.cpp',
    'src/comms/radio_transport.cpp',
    'src/comms/serial_transport.cpp',
    'src/comms/wire_adapter.cpp',
    'src/comms/wire_handler.cpp',
    'src/core/diffdrive.cpp',
    'src/motion/motion_engine.cpp',
    'src/platform/nezha_port.cpp',
    'src/platform/otos_port.cpp',
    'src/shims.cpp',
]


def _check_hex_size(size_bytes, floor=MIN_HEX_SIZE_BYTES):
    """Pure function, no I/O: True iff `size_bytes` (an already-read
    `os.path.getsize()` result) meets `floor`. Mirrors
    `_count_universal_hex_blocks()`'s separation of pure logic from the
    I/O that feeds it -- `build()` reads the hex's size and hands the
    plain int here, so this is directly unit-testable with no temp
    files and no filesystem
    (`tests/tools/test_make_deploy_triage.py`)."""
    return size_bytes >= floor


def _check_translation_units(output, expected_files=EXPECTED_CPP_FILES):
    """Pure function, no subprocess: which of `expected_files` do NOT
    appear in any of `output`'s `Building CXX object` lines. Returns a
    list of missing files -- empty means every expected file was seen.

    Matches on substring against the real log line shape, e.g.:
      `[ 93%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/
       nezha-diffdrive/src/comms/protocol.cpp.obj`
    -- the expected repo-relative path (`src/comms/protocol.cpp`) is a
    substring of the `.obj` path CMake prints, so no path-shape
    parsing is needed, only `in`.

    Deliberately checks "is each EXPECTED file found", never the
    reverse ("is each FOUND line one of the expected files"): the
    reverse is vacuously true when nothing at all was built (an empty
    found-set is trivially a subset of anything), which is exactly the
    stale-cache shape this check exists to catch -- a build log with
    ZERO `Building CXX object` lines must come back with all ten files
    listed as missing, not as an empty, satisfied check."""
    build_lines = '\n'.join(
        line for line in output.splitlines() if 'Building CXX object' in line
    )
    return [f for f in expected_files if f not in build_lines]


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


# --- per-robot build-time injection ---------------------------------------
#
# The scratch copy sync() just populated (DEPLOY) is the injection seam:
# it keeps the repo's own checked-in src/ robot-agnostic while still
# letting the actual build carry one robot's own facts. main() calls
# _inject_radio_channel(), _inject_profile(), and _inject_boot_banner()
# AFTER sync(), BEFORE build() -- see main()'s own call site, below.


def _robot_config_path(robot):
    return os.path.join(RADIO_ROBOT_LIB, 'config', 'robots', f'{robot}.json')


def _read_robot_radio_channel(robot):
    """Read `connection.radio_channel` from radio-robot-lib's own
    per-robot config for `robot` -- the fleet's one canonical source of
    per-robot truth, already consulted by other tooling. No table of
    robot->channel lives in this repo; this function is the only place
    a channel number is read from, and it always goes through this one
    file.

    FAILS LOUDLY (sys.exit, naming both the robot and the exact path
    tried) on a missing file, unreadable JSON, or a JSON file with no
    `radio_channel` field -- a silent fallback here is the exact defect
    this function exists to close: it is how one robot ended up
    transmitting on another robot's channel with nothing in the build
    log to say so."""
    path = _robot_config_path(robot)
    if not os.path.exists(path):
        sys.exit(f"make_deploy: no radio config for robot '{robot}' -- "
                  f"tried {path}")
    try:
        with open(path) as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"make_deploy: could not read radio config for robot "
                  f"'{robot}' at {path}: {exc}")
    channel = config.get('connection', {}).get('radio_channel')
    if channel is None:
        sys.exit(f"make_deploy: robot config at {path} has no "
                  f"connection.radio_channel for robot '{robot}'")
    return channel


# Matches radio_transport.h's own single kChannel declaration. kGroup
# (fleet-wide, never parameterised) and kTransmitPower are deliberately
# outside this pattern's reach -- see this section's own top comment.
_K_CHANNEL_RE = re.compile(r'(static constexpr int kChannel = )\d+(;)')


def _inject_radio_channel(deploy_dir, robot):
    """Substitute `deploy_dir`'s own copy of
    `src/comms/radio_transport.h`'s `kChannel` constant with `robot`'s
    configured radio channel (`_read_robot_radio_channel()`, above).
    Mutates ONLY the scratch copy at `deploy_dir` -- the repo's own
    checked-in `src/comms/radio_transport.h` is never touched, which is
    what keeps a build invoked with no `--robot` byte-equivalent to
    today's (`DEFAULT_ROBOT`, vevov, is already on channel 4, the
    checked-in value)."""
    channel = _read_robot_radio_channel(robot)
    path = os.path.join(deploy_dir, 'src', 'comms', 'radio_transport.h')
    text = open(path).read()
    new_text, n = _K_CHANNEL_RE.subn(rf'\g<1>{channel}\g<2>', text)
    if n != 1:
        sys.exit(f"make_deploy: expected exactly one kChannel constant in "
                  f"{path}, found {n} -- radio_transport.h's shape has "
                  f"changed, update _K_CHANNEL_RE")
    with open(path, 'w') as f:
        f.write(new_text)
    return channel


# Matches protocol.cpp's own single kProfile declaration. kDrivetrain
# and kVersion sit right next to it in the same anonymous namespace but
# are deliberately outside this pattern's reach -- this substitutes the
# quoted string literal following the literal text `kProfile = `, and
# nothing else that also happens to be a quoted `constexpr const char*`.
_K_PROFILE_RE = re.compile(
    r'(constexpr const char\* kProfile = ")[^"]*(";)')


def _read_robot_profile(robot):
    """Confirm radio-robot-lib's own per-robot config for `robot`
    exists and is readable JSON -- the same fleet-canonical file
    `_read_robot_radio_channel()` reads. Unlike that function, no field
    is read out of it: per the reference design
    (`radio-robot-elite/src/firm/main.cpp`, `Config::kRobotProfileName`
    "baked from the robot JSON's own ... filename stem"), the profile
    baked into a build IS the robot JSON's own filename stem -- `robot`
    itself.

    Still consulted, not skipped: this exists so a typo'd or
    unconfigured `--robot` FAILS LOUDLY (sys.exit, naming both the
    robot and the exact path tried) here, on a missing file or
    unreadable JSON, exactly like `_read_robot_radio_channel()` does --
    rather than silently baking a plausible-looking but unconfigured
    name into `kProfile`. A silent fallback here is the exact defect
    this function exists to close (this repo's own `kProfile` bug: a
    hand-written `"tovez"` constant baked fleet-wide, so every board --
    including vevov -- reported `"tovez"` over the wire `ID` verb)."""
    path = _robot_config_path(robot)
    if not os.path.exists(path):
        sys.exit(f"make_deploy: no robot config for robot '{robot}' -- "
                  f"tried {path}")
    try:
        with open(path) as f:
            json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"make_deploy: could not read robot config for robot "
                  f"'{robot}' at {path}: {exc}")


def _inject_profile(deploy_dir, robot):
    """Substitute `deploy_dir`'s own copy of `src/comms/protocol.cpp`'s
    `kProfile` constant with `robot`'s own fleet name (after confirming
    `robot` is a real, configured fleet member via
    `_read_robot_profile()`, above). Mutates ONLY the scratch copy at
    `deploy_dir` -- the same scratch-copy-only substitution
    `_inject_radio_channel()` performs for `kChannel`; see that
    function's own docstring for why that is what keeps the repo's own
    checked-in `protocol.cpp` robot-agnostic.

    Unlike the channel injection, this ENDS sprint 022's "a build with
    no --robot is byte-equivalent to before" property for this file:
    `protocol.cpp`'s checked-in `kProfile` default is deliberately not
    any fleet robot's own name (see that file's own comment), so every
    build -- including the `DEFAULT_ROBOT` one -- now differs from the
    checked-in source once baked. That is intentional: an
    unparameterized build must not be able to impersonate a robot on
    the fleet, which a byte-equivalent-to-checked-in default would
    allow."""
    _read_robot_profile(robot)
    path = os.path.join(deploy_dir, 'src', 'comms', 'protocol.cpp')
    text = open(path).read()
    new_text, n = _K_PROFILE_RE.subn(rf'\g<1>{robot}\g<2>', text)
    if n != 1:
        sys.exit(f"make_deploy: expected exactly one kProfile constant in "
                  f"{path}, found {n} -- protocol.cpp's shape has "
                  f"changed, update _K_PROFILE_RE")
    with open(path, 'w') as f:
        f.write(new_text)
    return robot


# This repo's own version source -- pyproject.toml's [project] version,
# `0.YYYYMMDD.n`. Read with a plain regex, not a TOML parser dependency,
# since only this one field is ever needed.
_PYPROJECT = os.path.join(REPO, 'pyproject.toml')
_PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _read_repo_version():
    """Read this repo's own `0.YYYYMMDD.n` version straight out of
    `pyproject.toml` -- deliberately NOT `pxt.json`'s own `1.0.10`-style
    version, which has no day-of-month digit pair in its minor and does
    not fit the `DD.RR` banner format (see `format_boot_version()`,
    below). FAILS LOUDLY if the file is missing or has no `version =
    "..."` line, same posture as `_read_robot_radio_channel()`."""
    if not os.path.exists(_PYPROJECT):
        sys.exit(f"make_deploy: repo version file not found: {_PYPROJECT}")
    text = open(_PYPROJECT).read()
    m = _PYPROJECT_VERSION_RE.search(text)
    if not m:
        sys.exit(f'make_deploy: no version = "..." line found in '
                  f'{_PYPROJECT}')
    return m.group(1)


def format_boot_version(version):
    """Pure function: this repo's own `0.YYYYMMDD.n` version string ->
    the on-device boot-banner format -- the last two digits of the
    minor (the day of the month) then a dot then the revision,
    zero-padded to two digits. `0.20260826.5` -> `26.05`. Public (no
    leading underscore) and pure, like `classify_attempt()`, so it is
    directly unit-testable with no file I/O.

    Raises `ValueError` (not `sys.exit` -- this function is pure; the
    caller decides how to fail) if `version` is not shaped like
    `MAJOR.YYYYMMDD.REVISION`."""
    parts = version.split('.')
    if len(parts) != 3:
        raise ValueError(
            f'expected MAJOR.YYYYMMDD.REVISION, got {version!r}')
    _major, minor, revision = parts
    if len(minor) < 2 or not minor.isdigit():
        raise ValueError(
            f'minor version is not day-of-month-shaped: {minor!r}')
    if not revision.isdigit():
        raise ValueError(f'revision is not numeric: {revision!r}')
    day = minor[-2:]
    return f'{day}.{int(revision):02d}'


# Matches test.ts's own BOOT_VERSION/BOOT_ROBOT placeholder
# declarations (see that file's own top-of-file comment for why they
# exist as substitutable placeholders at all).
_BOOT_VERSION_RE = re.compile(r'(const BOOT_VERSION = )"[^"]*"')
_BOOT_ROBOT_RE = re.compile(r'(const BOOT_ROBOT = )"[^"]*"')


def _inject_boot_banner(deploy_dir, robot):
    """Substitute `deploy_dir`'s own copy of `test/test.ts`'s
    `BOOT_VERSION`/`BOOT_ROBOT` placeholder constants with this build's
    actual version (`_read_repo_version()` + `format_boot_version()`,
    above) and target robot name. Same mechanism as
    `_inject_radio_channel()`: a scratch-copy-only text substitution:
    the repo's own checked-in `test/test.ts` keeps its placeholder
    values, since `test.ts` cannot read `pyproject.toml` itself."""
    version = format_boot_version(_read_repo_version())
    path = os.path.join(deploy_dir, 'test', 'test.ts')
    text = open(path).read()
    text, n1 = _BOOT_VERSION_RE.subn(rf'\g<1>"{version}"', text)
    text, n2 = _BOOT_ROBOT_RE.subn(rf'\g<1>"{robot}"', text)
    if n1 != 1 or n2 != 1:
        sys.exit(f"make_deploy: expected exactly one BOOT_VERSION and one "
                  f"BOOT_ROBOT placeholder in {path}, found {n1} and {n2} "
                  f"-- test.ts's shape has changed, update _BOOT_VERSION_RE"
                  f"/_BOOT_ROBOT_RE")
    with open(path, 'w') as f:
        f.write(text)
    return version


def _run_pxt_build(deploy_dir=None, hex_path=None):
    """Run one `pxt build` attempt in `deploy_dir` against `hex_path`
    (both default to the primary flashable scratch, DEPLOY/HEX --
    `build_testrig()` passes DEPLOY_TESTRIG/HEX_TESTRIG instead),
    streaming its output live (a cloud build can take a while) while
    also capturing it for classify_attempt(). Removes any pre-existing
    hex first, so a build that aborts mid-package can never be mistaken
    for a stale-but-good one (see the TS9283 note in this file's module
    docstring).

    Sets an explicit subprocess environment (sprint 014,
    `clasi/issues/never-build-the-v1-mbdal-variant.md`) rather than
    relying on the caller's shell:

    * `PXT_COMPILE_SWITCHES=csv-mbcodal` is forced unconditionally --
      never overridable by the ambient environment. V1 (`mbdal`) is
      categorically unsupported hardware for this project, so there is
      no legitimate reason for this to ever be anything else. This is
      what makes `pxt-core` select `appTargetVariant=mbcodal` up front
      and never build V1 at all.
    * `PXT_FORCE_LOCAL` defaults to `'1'` (local Docker compile) but
      honors an already-set ambient value -- e.g. `PXT_FORCE_LOCAL=0`
      opts back into the MakeCode cloud compiler. This is what makes a
      bare `uv run python tools/make_deploy.py` compile locally with no
      env-var prefix required.
    """
    if deploy_dir is None:
        deploy_dir = DEPLOY
    if hex_path is None:
        hex_path = HEX
    if os.path.exists(hex_path):
        os.remove(hex_path)
    env = dict(os.environ)
    env['PXT_COMPILE_SWITCHES'] = 'csv-mbcodal'
    env.setdefault('PXT_FORCE_LOCAL', '1')
    proc = subprocess.Popen(
        ['pxt', 'build'], cwd=deploy_dir, env=env,
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
    this only wires which build output/hex path it judges.

    After a SUCCESS verdict, before the hex is ever reported as ready,
    also asserts it is a plain V2 hex, not a universal (V1+V2) one --
    see `_count_universal_hex_blocks()` and the module docstring's
    "Sprint 014" note. `built/binary.hex` is ambiguous by filename
    alone; a nonzero block count means
    `PXT_COMPILE_SWITCHES=csv-mbcodal` silently failed to take effect,
    which is a hard failure, not a shape `build()` can treat as
    flashable.

    Also asserts the hex meets `MIN_HEX_SIZE_BYTES` and that all
    `EXPECTED_CPP_FILES` compiled (`_check_hex_size()` /
    `_check_translation_units()`, above) -- closing the gap where a
    build served entirely or partly from a stale
    `.tmp/deploy-head/built/dockercodal` cache prints a clean log,
    exits 0, and still produces a real but short/under-compiled hex."""
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
    with open(hex_path) as f:
        block_count = _count_universal_hex_blocks(f.read())
    if block_count != 0:
        sys.exit(
            f'\n{label}BUILD FAILED: {hex_path} is a universal (V1+V2) hex '
            f'({block_count} :0400000A block markers) instead of a plain V2 '
            "hex -- PXT_COMPILE_SWITCHES=csv-mbcodal did not take effect. "
            "See tools/DESIGN.md's \"Build checkpoint triage\" section."
        )

    # Scratch-copy dir this hex was built in (hex_path is always
    # <deploy_dir>/built/binary.hex) -- named in the recovery message
    # below so it points at the actual stale directory, not a guess.
    deploy_dir = os.path.dirname(os.path.dirname(hex_path))

    hex_size = os.path.getsize(hex_path)
    if not _check_hex_size(hex_size):
        sys.exit(
            f'\n{label}BUILD FAILED: {hex_path} is {hex_size} bytes, below '
            f'the {MIN_HEX_SIZE_BYTES}-byte floor -- likely served wholly '
            'or partly from a stale build cache rather than a genuine '
            'compile. Wipe the stale scratch copy and rebuild: Python '
            f'shutil.rmtree({deploy_dir!r}) (rm -rf may be sandbox-denied), '
            "then rerun this script. See tools/DESIGN.md's \"Build "
            'checkpoint triage" section.'
        )

    missing = _check_translation_units(output)
    if missing:
        if len(missing) == len(EXPECTED_CPP_FILES):
            what = ("zero 'Building CXX object' lines found in the "
                     "captured build output -- nothing was compiled, most "
                     "likely served entirely from a stale build cache")
        else:
            what = ("missing 'Building CXX object' lines for: " +
                     ', '.join(missing))
        sys.exit(
            f'\n{label}BUILD FAILED: not all nezha-diffdrive translation '
            f'units were compiled ({what}). Wipe the stale scratch copy and '
            f'rebuild: Python shutil.rmtree({deploy_dir!r}) (rm -rf may be '
            "sandbox-denied), then rerun this script. See tools/DESIGN.md's "
            '"Build checkpoint triage" section.'
        )

    print(f'\n{label}hex: {hex_path}  ({hex_size} bytes)  [attempt {attempt}]')


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
    ap.add_argument('--robot', default=DEFAULT_ROBOT,
                     help="target robot name -- selects the flash "
                          "target, the radio channel, and the wire ID "
                          "profile compiled into the hex (channel read "
                          "from radio-robot-lib's "
                          "config/robots/<robot>.json; profile is that "
                          "config's own filename stem; both substituted "
                          "into the scratch copy before build)")
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
    _inject_radio_channel(DEPLOY, a.robot)
    _inject_profile(DEPLOY, a.robot)
    _inject_boot_banner(DEPLOY, a.robot)
    build()
    if a.flash:
        flash(a.robot)


if __name__ == '__main__':
    main()
