"""tests/tools/test_make_deploy_triage.py -- pins the triage logic
`tools/make_deploy.py` uses to decide whether a real `pxt build`
attempt succeeded, hard-failed, or hit a known-benign abort worth
retrying.

**Why this exists.** Sprint 008's centerpiece issue
(`clasi/issues/host-tests-compile-newer-standard-than-target.md`) is
that nothing in the per-ticket/per-sprint flow required a real target
build, so three target-only defects escaped a fully green host suite.
The fix is `tools/make_deploy.py`'s new triage in `build()` -- but
*that* logic has no test of its own unless something like this file
exists: a human reading raw compiler output was the failure mode this
sprint closes everywhere else, and `classify_attempt()` is exactly the
kind of "quietly stops doing its job" code this project's whole "tests
that can fail" theme targets. This module never invokes a real
compiler or the network -- it feeds `classify_attempt()` saved/
synthetic build-log text and asserts the verdict, so it runs in
milliseconds as part of the ordinary `uv run pytest` suite.

The synthetic logs below mirror shapes actually observed this session
(see `tools/make_deploy.py`'s module docstring and `tools/DESIGN.md`'s
"Build checkpoint triage" section): the legacy V1
`bbc-microbit-classic-gcc` hex-merge `srec_cat` failure, the
nondeterministic `TS9283`/`TS9043`/`TS9200` packaging abort following a
pxt-core cache-write `TypeError`, and a real GCC-style compile
diagnostic shaped like the `Wire::Column` NSDMI/aggregate-init defect
that started this whole issue.

Run with::

    uv run pytest tests/tools/test_make_deploy_triage.py
"""

import json
import pathlib
import sys

import pytest

# tests/tools/test_make_deploy_triage.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import make_deploy  # noqa: E402  (path must be set up first)


# --- synthetic/saved build-log fixtures -----------------------------------

CLEAN_SUCCESS_LOG = """\
Using target microbit with build engine yotta
### Compiling in codal-microbit-v2
Linking cpp...
Package built successfully.
"""

# Mirrors the confirmed Wire::Column defect (NSDMI + aggregate-init
# under C++11 -- see clasi/issues/host-tests-compile-newer-standard-
# than-target.md and src/DESIGN.md sec 4/11): a real GCC diagnostic
# naming a source file and line.
COMPILE_ERROR_LOG = """\
Using target microbit with build engine yotta
### Compiling in codal-microbit-v2
src/wire_adapter.cpp: In member function 'const Wire::Snapshot& diffDrive::WireAdapter::buildSnapshot()':
src/wire_adapter.cpp:539:45: error: no matching function for call to 'diffDrive::Wire::Column::Column(<brace-enclosed initializer list>)'
   539 |     columns_[i++] = {"seq", (int32_t)seq_, false};
       |                                             ^
error TS9271: C++ build failed
"""

# A pxt.json manifest omission surfaces the same way -- a missing
# header fails "file not found" at its #include site, in the same
# file:line:diagnostic shape a compile error takes. There is
# deliberately no separate manifest-checking code path in
# classify_attempt() -- this IS how that class is caught.
MANIFEST_OMISSION_LOG = """\
Using target microbit with build engine yotta
### Compiling in codal-microbit-v2
src/wire_adapter.cpp:14:10: fatal error: heading_wrap.h: No such file or directory
   14 | #include "heading_wrap.h"
      |          ^~~~~~~~~~~~~~~~
compilation terminated.
error TS9271: C++ build failed
"""

# The legacy V1 variant's own hex-merge step, quoted verbatim from
# tools/make_deploy.py's module docstring and this ticket.
V1_HEXMERGE_LOG = """\
Using target microbit with build engine yotta
### Compiling in bbc-microbit-classic-gcc
Linking cpp...
srec_cat: pxt-microbit-app.hex: 9220: contradictory 0x0003C000 value: was 0xE0, wants 0xFF
error TS9270: hex file merge for bbc-microbit-classic-gcc failed
### Compiling in codal-microbit-v2
Linking cpp...
Package built successfully.
"""

# The nondeterministic packaging abort, three observed shapes, all
# following a pxt-core cache-write TypeError.
PACKAGING_ABORT_LOG_9283 = """\
Using target microbit with build engine yotta
### Compiling in codal-microbit-v2
Linking cpp...
TypeError [ERR_INVALID_ARG_TYPE]: The "data" argument must be of type string or an instance of Buffer, TypedArray, or DataView. Received undefined
    at Object.writeFileSync (node:fs:2223:5)
error TS9283: program too big
"""

PACKAGING_ABORT_LOG_9043 = """\
Using target microbit with build engine yotta
### Compiling in codal-microbit-v2
Linking cpp...
TypeError [ERR_INVALID_ARG_TYPE]: The "data" argument must be of type string or an instance of Buffer, TypedArray, or DataView. Received undefined
    at Object.writeFileSync (node:fs:2223:5)
error TS9043: hex file is not available, please connect to internet and try again
"""

PACKAGING_ABORT_LOG_9200 = """\
Using target microbit with build engine yotta
### Compiling in codal-microbit-v2
Linking cpp...
TypeError [ERR_INVALID_ARG_TYPE]: The "data" argument must be of type string or an instance of Buffer, TypedArray, or DataView. Received undefined
    at Object.writeFileSync (node:fs:2223:5)
error TS9200: could not package hex
"""

# No hex, no compile diagnostic, no known-benign shape -- e.g. a
# network failure unrelated to any documented abort.
UNRECOGNIZED_FAILURE_LOG = """\
Using target microbit with build engine yotta
Error: connect ETIMEDOUT 140.82.112.3:443
    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1601:16)
"""

# Synthetic hex-file text fixtures for _count_universal_hex_blocks()
# (sprint 014). Not meant to be flashable -- close enough to real
# Intel-hex shape to exercise the `:0400000A` extended-linear-address
# block-marker count, which is all the counting function looks at. A
# universal (V1+V2) hex brackets EACH variant's program data with one
# such marker; a plain single-variant hex (csv-mbcodal's own output)
# has none.
PLAIN_V2_HEX_FIXTURE = """\
:020000040000FA
:10000000AABBCCDDEEFF00112233445566778899C2
:00000001FF
"""

UNIVERSAL_HEX_FIXTURE = """\
:0400000A0000F0FA
:10000000AABBCCDDEEFF0011223344556677889912
:0400000A0001F0F9
:10000000112233445566778899AABBCCDDEEFF0034
:00000001FF
"""


# --- fixtures for the hex size floor / translation-unit presence check ----
#
# A build served (wholly or partly) from a stale build cache can print
# a clean log and still produce a real, well-formed, but too-short hex
# with none of its own `.cpp` files rebuilt -- neither classify_attempt()
# nor _count_universal_hex_blocks() catches that; MIN_HEX_SIZE_BYTES and
# EXPECTED_CPP_FILES (make_deploy.py) close the gap.


def _building_cxx_line(rel_path):
    """One synthetic `Building CXX object` log line, in the real shape
    confirmed against captured build evidence: `[ NN%] Building CXX
    object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/<rel_path>.obj`.
    The expected repo-relative path is a substring of the `.obj` path
    CMake actually prints, which is what `_check_translation_units()`
    matches against."""
    return (f'[ 93%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/'
            f'nezha-diffdrive/{rel_path}.obj')


# A synthetic log naming ALL ten nezha-diffdrive translation units, on
# top of an otherwise-ordinary clean build log -- what
# _check_translation_units() must accept as complete, and what a
# genuinely successful build() call should see.
GENUINE_CLEAN_BUILD_LOG = CLEAN_SUCCESS_LOG + '\n'.join(
    _building_cxx_line(f) for f in make_deploy.EXPECTED_CPP_FILES
) + '\n'


def _padded_plain_v2_hex(min_size=None):
    """PLAIN_V2_HEX_FIXTURE, padded with filler bytes that never spell
    out the `:0400000A` universal-hex marker, until it reaches at least
    `min_size` (default MIN_HEX_SIZE_BYTES) bytes. Lets a test satisfy
    the size-floor check without embedding a real ~1.3 MB fixture in
    this file -- _check_hex_size() only ever looks at a byte count, not
    real Intel-hex structure."""
    if min_size is None:
        min_size = make_deploy.MIN_HEX_SIZE_BYTES
    pad = 'X' * max(0, min_size - len(PLAIN_V2_HEX_FIXTURE))
    return PLAIN_V2_HEX_FIXTURE + pad


# --- classify_attempt() ----------------------------------------------------


def test_clean_success_with_hex_is_success():
    verdict, reason = make_deploy.classify_attempt(
        CLEAN_SUCCESS_LOG, hex_exists=True
    )
    assert verdict == make_deploy.SUCCESS
    assert reason == ""


def test_compile_error_is_hard_failure():
    verdict, reason = make_deploy.classify_attempt(
        COMPILE_ERROR_LOG, hex_exists=False
    )
    assert verdict == make_deploy.HARD_FAILURE
    assert "wire_adapter.cpp:539" in reason


def test_compile_error_wins_even_if_a_hex_exists():
    """A hex from one build variant does not excuse a compile error in
    another -- classify_attempt() must check for a real diagnostic
    before it ever looks at hex_exists. This is the exact case
    tools/make_deploy.py's own module docstring warns about: a
    packaging step can produce artifacts independent of whether every
    translation unit actually compiled cleanly."""
    verdict, reason = make_deploy.classify_attempt(
        COMPILE_ERROR_LOG, hex_exists=True
    )
    assert verdict == make_deploy.HARD_FAILURE
    assert "error" in reason


def test_manifest_omission_is_hard_failure_via_the_same_path():
    """No dedicated pxt.json-reading code exists in classify_attempt()
    -- a manifest omission is caught because it fails the same way a
    real compile error does (a file:line diagnostic at the #include
    site), the same class test_pxt_manifest_completeness.py's own
    docstring describes."""
    verdict, reason = make_deploy.classify_attempt(
        MANIFEST_OMISSION_LOG, hex_exists=False
    )
    assert verdict == make_deploy.HARD_FAILURE
    assert "heading_wrap.h" in reason


def test_v1_hexmerge_failure_is_now_unknown_not_benign():
    """Regression pin (sprint 014): under
    PXT_COMPILE_SWITCHES=csv-mbcodal, V1 never builds, so its old
    hex-merge failure is no longer an expected, retry-worthy shape --
    it can now only mean the switch silently failed to take effect,
    which must fail hard, not retry. See sprint.md's Design Rationale
    and clasi/issues/never-build-the-v1-mbdal-variant.md."""
    verdict, reason = make_deploy.classify_attempt(
        V1_HEXMERGE_LOG, hex_exists=False
    )
    assert verdict == make_deploy.UNKNOWN


def test_packaging_abort_9283_is_benign():
    verdict, reason = make_deploy.classify_attempt(
        PACKAGING_ABORT_LOG_9283, hex_exists=False
    )
    assert verdict == make_deploy.BENIGN


def test_packaging_abort_9043_is_benign():
    verdict, reason = make_deploy.classify_attempt(
        PACKAGING_ABORT_LOG_9043, hex_exists=False
    )
    assert verdict == make_deploy.BENIGN


def test_packaging_abort_9200_is_benign():
    verdict, reason = make_deploy.classify_attempt(
        PACKAGING_ABORT_LOG_9200, hex_exists=False
    )
    assert verdict == make_deploy.BENIGN


def test_unrecognized_failure_is_unknown_not_benign():
    """An abort that matches none of the documented shapes must not be
    silently retried as though it were known-benign -- it fails closed
    as UNKNOWN, a hole worth stating plainly: a real, new failure mode
    reports as a failure here (safe), but so would a genuinely benign
    shape nobody has documented yet (an honest cost, not a false
    positive)."""
    verdict, reason = make_deploy.classify_attempt(
        UNRECOGNIZED_FAILURE_LOG, hex_exists=False
    )
    assert verdict == make_deploy.UNKNOWN


def test_no_hex_and_clean_output_is_unknown():
    """Belt-and-suspenders: no hex and literally no error text at all
    (e.g. a truncated log) must not be misread as success."""
    verdict, reason = make_deploy.classify_attempt("", hex_exists=False)
    assert verdict == make_deploy.UNKNOWN


# --- _count_universal_hex_blocks() (sprint 014) -----------------------------
#
# Pure function, no I/O -- directly unit-testable against fixture text,
# mirroring classify_attempt()/_select_promoted()'s separation of pure
# logic from the I/O that feeds it. build()'s own use of this (read the
# hex, hard-fail on a nonzero count) is exercised further down by the
# integration-level test alongside the other build() wiring tests.


def test_count_universal_hex_blocks_is_zero_for_plain_v2_hex():
    assert make_deploy._count_universal_hex_blocks(PLAIN_V2_HEX_FIXTURE) == 0


def test_count_universal_hex_blocks_counts_both_markers_in_a_universal_hex():
    assert make_deploy._count_universal_hex_blocks(UNIVERSAL_HEX_FIXTURE) == 2


# --- _check_hex_size() (hex size floor) -------------------------------------
#
# Pure function, no I/O -- see make_deploy.py's own comment above
# MIN_HEX_SIZE_BYTES for the measured band and why the floor sits where
# it does.


def test_check_hex_size_rejects_a_hex_below_the_floor():
    assert make_deploy._check_hex_size(make_deploy.MIN_HEX_SIZE_BYTES - 1) is False


def test_check_hex_size_accepts_a_hex_at_the_floor():
    assert make_deploy._check_hex_size(make_deploy.MIN_HEX_SIZE_BYTES) is True


def test_check_hex_size_accepts_a_hex_above_the_floor():
    assert make_deploy._check_hex_size(make_deploy.MIN_HEX_SIZE_BYTES + 1) is True


def test_check_hex_size_rejects_the_actual_truncated_size_measured():
    """Regression pin: the actual byte count observed from the
    stale-cache defect this check exists to catch must fail -- it sits
    well below MIN_HEX_SIZE_BYTES, not just barely under it."""
    assert make_deploy._check_hex_size(1_046_410) is False


# --- _check_translation_units() (translation-unit presence check) ----------
#
# Pure function, no subprocess. The critical case: a build output with
# ZERO `Building CXX object` lines (a build served entirely from a
# stale cache) must report every expected file missing, not an empty,
# vacuously-satisfied list -- see make_deploy.py's own docstring for
# why the check is written expected-found, never found-in-expected.


def test_check_translation_units_passes_when_all_ten_present():
    assert make_deploy._check_translation_units(GENUINE_CLEAN_BUILD_LOG) == []


def test_check_translation_units_names_a_single_missing_file():
    present = [f for f in make_deploy.EXPECTED_CPP_FILES
               if f != 'src/shims.cpp']
    log = CLEAN_SUCCESS_LOG + '\n'.join(
        _building_cxx_line(f) for f in present
    )
    assert make_deploy._check_translation_units(log) == ['src/shims.cpp']


def test_check_translation_units_names_every_missing_file():
    present = make_deploy.EXPECTED_CPP_FILES[:3]
    expected_missing = make_deploy.EXPECTED_CPP_FILES[3:]
    log = CLEAN_SUCCESS_LOG + '\n'.join(
        _building_cxx_line(f) for f in present
    )
    assert make_deploy._check_translation_units(log) == expected_missing


def test_check_translation_units_zero_lines_reports_all_ten_missing():
    """The specific shape that keeps recurring: a build served entirely
    from a stale cache logs no `Building CXX object` lines at all. This
    must fail exactly like any other missing-subset case, naming all
    ten files, not be special-cased as 'nothing needed rebuilding,
    therefore fine' -- own test, not incidental to the missing-file
    tests above."""
    missing = make_deploy._check_translation_units(CLEAN_SUCCESS_LOG)
    assert missing == make_deploy.EXPECTED_CPP_FILES
    assert len(missing) == 10


# --- testFiles promotion (the build-hygiene half of this ticket) ----------
#
# Regression coverage for the defect this ticket closes: sync()'s old
# filter was `f.endswith('test.ts')` -- `'test/testrig.ts'.endswith(
# 'test.ts')` is False (it ends in `'trig.ts'`), so `testrig.ts` never
# got promoted into any scratch build's `files`, and nothing built/
# type-checked it. `_select_promoted()` is the pure selection logic
# extracted from `_sync_scratch()`'s file-copying I/O, so it is
# directly testable against a `pxt.json`-shaped fixture with no repo
# checkout and no subprocess.

PXT_JSON_FIXTURE = {
    "files": ["src/main.ts"],
    "testFiles": ["test/test.ts", "test/testrig.ts"],
}


def test_testrig_is_selected_for_its_own_scratch_variant():
    """The ticket's own acceptance criterion: given a pxt.json fixture
    listing both test.ts and testrig.ts in testFiles, testrig.ts is
    included in what gets promoted (built/type-checked) when its own
    variant is requested."""
    promoted = make_deploy._select_promoted(PXT_JSON_FIXTURE, "testrig.ts")
    assert promoted == ["test/testrig.ts"]


def test_test_ts_promotion_excludes_testrig_ts():
    """The hard safety constraint from sprint.md's Migration Concerns:
    test.ts and testrig.ts are two independent, mutually exclusive
    on-robot programs and must never both be promoted into one scratch
    build's files -- combining them would compile both programs'
    top-level code (and both basic.forever loops) into a single hex.
    The primary deploy's own selection must never include testrig.ts."""
    promoted = make_deploy._select_promoted(PXT_JSON_FIXTURE, "test.ts")
    assert promoted == ["test/test.ts"]
    assert "test/testrig.ts" not in promoted


def test_selection_matches_exact_basename_not_a_lucky_suffix():
    """Regression for the actual mechanism of the bug: an
    endswith('test.ts') filter rejects 'test/testrig.ts' only by luck
    of spelling (it ends in 'trig.ts', not 'test.ts') -- and the same
    endswith() filter would WRONGLY accept a file merely ending in that
    substring, e.g. 'test/nested/oldtest.ts'. Basename equality gets
    both cases right where endswith() got one right by accident and the
    other wrong."""
    manifest = {"testFiles": ["test/testrig.ts", "test/nested/oldtest.ts"]}
    assert make_deploy._select_promoted(manifest, "test.ts") == []
    assert make_deploy._select_promoted(manifest, "testrig.ts") == [
        "test/testrig.ts"
    ]


def test_sync_and_sync_testrig_never_share_a_promoted_file(tmp_path, monkeypatch):
    """Integration-level regression, exercising the real file-copying
    code path (no network, no `pxt build`): sync() promotes only
    test.ts into its own scratch copy's files; sync_testrig() promotes
    only testrig.ts into a SEPARATE scratch copy's files. Neither
    scratch copy's generated pxt.json ever contains both -- the
    mutual-exclusivity constraint from sprint.md's Migration Concerns,
    verified against generated output, not just the pure selector."""
    repo = tmp_path / "repo"
    (repo / "test").mkdir(parents=True)
    (repo / "pxt_modules").mkdir()
    (repo / "node_modules").mkdir()
    (repo / "main.ts").write_text("// main\n")
    (repo / "test" / "test.ts").write_text("// test.ts\n")
    (repo / "test" / "testrig.ts").write_text("// testrig.ts\n")
    manifest = {
        "files": ["main.ts"],
        "testFiles": ["test/test.ts", "test/testrig.ts"],
        "disablesVariants": ["mbdal"],
    }
    (repo / "pxt.json").write_text(json.dumps(manifest))

    deploy = tmp_path / "deploy-head"
    deploy_rig = tmp_path / "deploy-testrig"
    monkeypatch.setattr(make_deploy, "REPO", str(repo))
    monkeypatch.setattr(make_deploy, "DEPLOY", str(deploy))
    monkeypatch.setattr(make_deploy, "DEPLOY_TESTRIG", str(deploy_rig))

    primary_files = make_deploy.sync()
    rig_files = make_deploy.sync_testrig()

    assert "test/test.ts" in primary_files
    assert "test/testrig.ts" not in primary_files
    assert "test/testrig.ts" in rig_files
    assert "test/test.ts" not in rig_files

    primary_manifest = json.loads((deploy / "pxt.json").read_text())
    assert primary_manifest["files"] == primary_files
    assert primary_manifest["testFiles"] == []

    rig_manifest = json.loads((deploy_rig / "pxt.json").read_text())
    assert rig_manifest["files"] == rig_files
    assert rig_manifest["testFiles"] == []

    # Every promoted/declared file actually landed on disk at its
    # declared relative path in EACH scratch copy -- not just named in
    # the returned list.
    assert (deploy / "test" / "test.ts").exists()
    assert not (deploy / "test" / "testrig.ts").exists()
    assert (deploy_rig / "test" / "testrig.ts").exists()
    assert not (deploy_rig / "test" / "test.ts").exists()


# --- build()'s retry-then-report wiring ------------------------------------


def test_build_retries_once_on_benign_then_succeeds(monkeypatch, capsys, tmp_path):
    """The documented shape: attempt 1 hits a benign abort, attempt 2
    succeeds -- build() must retry automatically and not raise. Attempt
    1 uses the nondeterministic-packaging-abort shape, not the old V1
    hex-merge one -- under sprint 014's triage, V1 hex-merge is UNKNOWN
    (hard failure, no retry), not benign, so it can no longer stand in
    for "a benign shape" here. The block-marker check reads the hex's
    actual content, so attempt 2 writes a real temp hex file
    (0-marker, plain-V2 fixture, padded to the size floor) rather than
    relying on a faked os.path.exists(); the log on attempt 2 names all
    ten translation units, so the presence check also passes."""
    hex_path = tmp_path / "binary.hex"
    attempts = {"n": 0}

    def fake_run():
        attempts["n"] += 1
        if attempts["n"] == 1:
            return PACKAGING_ABORT_LOG_9283
        hex_path.write_text(_padded_plain_v2_hex())
        return GENUINE_CLEAN_BUILD_LOG

    monkeypatch.setattr(make_deploy, "_run_pxt_build", fake_run)
    monkeypatch.setattr(make_deploy, "HEX", str(hex_path))

    make_deploy.build()  # must not raise / sys.exit

    assert attempts["n"] == 2
    out = capsys.readouterr().out
    assert "retrying once" in out
    assert "[attempt 2]" in out


def test_build_reports_failure_when_benign_shape_recurs(monkeypatch):
    """The bounded-retry acceptance criterion: if the benign shape
    recurs on the retry and still produces no hex, build() must exit
    non-zero rather than retry forever or report the recurrence as
    just another benign abort."""
    monkeypatch.setattr(make_deploy, "_run_pxt_build",
                         lambda: PACKAGING_ABORT_LOG_9283)
    monkeypatch.setattr(make_deploy.os.path, "exists",
                         lambda path: False if path == make_deploy.HEX else True)

    with pytest.raises(SystemExit):
        make_deploy.build()


def test_build_reports_hard_failure_immediately_no_retry(monkeypatch):
    """A genuine compile error must fail on attempt 1 -- build() must
    not spend a retry on it (retries are reserved for the two
    documented benign shapes only)."""
    calls = {"n": 0}

    def fake_run():
        calls["n"] += 1
        return COMPILE_ERROR_LOG

    monkeypatch.setattr(make_deploy, "_run_pxt_build", fake_run)
    monkeypatch.setattr(make_deploy.os.path, "exists",
                         lambda path: False if path == make_deploy.HEX else True)

    with pytest.raises(SystemExit):
        make_deploy.build()

    assert calls["n"] == 1


def test_build_hard_fails_when_hex_is_universal_not_plain_v2(monkeypatch, tmp_path):
    """Sprint 014's own new assertion: even when classify_attempt()
    itself returns SUCCESS (a hex exists, no compile diagnostic), a hex
    containing universal-hex block markers must not be reported as
    flashable -- it means PXT_COMPILE_SWITCHES=csv-mbcodal silently
    failed to take effect. Analogous in shape to
    test_build_reports_failure_when_benign_shape_recurs above: build()
    must exit non-zero rather than trust the filename alone."""
    hex_path = tmp_path / "binary.hex"
    hex_path.write_text(UNIVERSAL_HEX_FIXTURE)

    monkeypatch.setattr(make_deploy, "_run_pxt_build",
                         lambda: CLEAN_SUCCESS_LOG)
    monkeypatch.setattr(make_deploy, "HEX", str(hex_path))

    with pytest.raises(SystemExit):
        make_deploy.build()


# --- build()'s new sprint-023 gate: size floor + translation-unit presence -


def test_build_fails_when_hex_is_below_the_size_floor(monkeypatch, tmp_path):
    """The core regression this ticket closes: a real, well-formed hex
    (0 universal-hex markers, all ten translation units logged as
    compiled) that is nonetheless too small must not reach the success
    path."""
    hex_path = tmp_path / "binary.hex"
    hex_path.write_text(PLAIN_V2_HEX_FIXTURE)  # tiny -- far below the floor

    monkeypatch.setattr(make_deploy, "_run_pxt_build",
                         lambda: GENUINE_CLEAN_BUILD_LOG)
    monkeypatch.setattr(make_deploy, "HEX", str(hex_path))

    with pytest.raises(SystemExit) as exc:
        make_deploy.build()
    message = str(exc.value)
    assert str(make_deploy.MIN_HEX_SIZE_BYTES) in message
    assert "below" in message


def test_build_fails_when_a_translation_unit_is_missing(monkeypatch, tmp_path):
    """A build that logs nine of the ten units must fail, naming the
    one that never compiled."""
    hex_path = tmp_path / "binary.hex"
    hex_path.write_text(_padded_plain_v2_hex())
    present = [f for f in make_deploy.EXPECTED_CPP_FILES
               if f != 'src/platform/otos_port.cpp']
    log = CLEAN_SUCCESS_LOG + '\n'.join(
        _building_cxx_line(f) for f in present
    )

    monkeypatch.setattr(make_deploy, "_run_pxt_build", lambda: log)
    monkeypatch.setattr(make_deploy, "HEX", str(hex_path))

    with pytest.raises(SystemExit) as exc:
        make_deploy.build()
    assert "src/platform/otos_port.cpp" in str(exc.value)


def test_build_fails_when_zero_translation_units_compiled(monkeypatch, tmp_path):
    """The recurring stale-cache shape: a clean log/hex with ZERO
    `Building CXX object` lines must fail build() -- not pass as
    'nothing needed rebuilding, therefore fine'. Own test, not
    incidental to the missing-single-file test above."""
    hex_path = tmp_path / "binary.hex"
    hex_path.write_text(_padded_plain_v2_hex())

    monkeypatch.setattr(make_deploy, "_run_pxt_build",
                         lambda: CLEAN_SUCCESS_LOG)
    monkeypatch.setattr(make_deploy, "HEX", str(hex_path))

    with pytest.raises(SystemExit) as exc:
        make_deploy.build()
    assert "zero" in str(exc.value).lower()


def test_build_succeeds_with_a_genuinely_complete_build(monkeypatch, capsys, tmp_path):
    """Positive/regression: a hex at the size floor plus a log naming
    all ten translation units must still reach build()'s success path
    on attempt 1 -- proving the two new checks don't false-positive on
    a real success."""
    hex_path = tmp_path / "binary.hex"
    hex_path.write_text(_padded_plain_v2_hex())

    monkeypatch.setattr(make_deploy, "_run_pxt_build",
                         lambda: GENUINE_CLEAN_BUILD_LOG)
    monkeypatch.setattr(make_deploy, "HEX", str(hex_path))

    make_deploy.build()  # must not raise / sys.exit

    out = capsys.readouterr().out
    assert "hex:" in out
    assert "[attempt 1]" in out


# --- build_testrig()'s wiring: testrig's own scratch, own hex path --------


def test_build_testrig_uses_its_own_scratch_dir_and_hex_path(monkeypatch, capsys, tmp_path):
    """build_testrig() must never touch the primary DEPLOY/HEX -- it
    runs `pxt build` against DEPLOY_TESTRIG and classifies against
    HEX_TESTRIG, not HEX. The mutual-exclusivity constraint applies to
    the build step too, not just sync(). Real temp hex file (0-marker,
    plain-V2 fixture padded to the size floor) and a log naming all ten
    translation units, per build()'s own gate checks -- build_testrig()
    reuses build() unchanged, so it is subject to them too."""
    hex_path = tmp_path / "binary.hex"
    hex_path.write_text(_padded_plain_v2_hex())
    calls = []

    def fake_run(deploy_dir=None, hex_path=None):
        calls.append((deploy_dir, hex_path))
        return GENUINE_CLEAN_BUILD_LOG

    monkeypatch.setattr(make_deploy, "_run_pxt_build", fake_run)
    monkeypatch.setattr(make_deploy, "HEX_TESTRIG", str(hex_path))

    make_deploy.build_testrig()  # must not raise / sys.exit

    assert calls == [(make_deploy.DEPLOY_TESTRIG, str(hex_path))]
    out = capsys.readouterr().out
    assert "testrig hex:" in out
    assert str(hex_path) in out


def test_build_testrig_reports_hard_failure_like_the_primary_build(monkeypatch):
    """build_testrig() reuses classify_attempt() unchanged -- a real
    compile error in testrig.ts must fail immediately, no retry, same
    as the primary deploy's build()."""
    monkeypatch.setattr(
        make_deploy, "_run_pxt_build",
        lambda deploy_dir=None, hex_path=None: COMPILE_ERROR_LOG,
    )
    monkeypatch.setattr(
        make_deploy.os.path, "exists",
        lambda path: False if path == make_deploy.HEX_TESTRIG else True,
    )

    with pytest.raises(SystemExit):
        make_deploy.build_testrig()
