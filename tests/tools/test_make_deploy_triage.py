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


def test_v1_hexmerge_failure_is_benign():
    verdict, reason = make_deploy.classify_attempt(
        V1_HEXMERGE_LOG, hex_exists=False
    )
    assert verdict == make_deploy.BENIGN
    assert "hex-merge" in reason


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


# --- build()'s retry-then-report wiring ------------------------------------


def test_build_retries_once_on_benign_then_succeeds(monkeypatch, capsys):
    """The documented shape: attempt 1 hits a benign abort, attempt 2
    succeeds -- build() must retry automatically and not raise."""
    attempts = {"n": 0}

    def fake_run():
        attempts["n"] += 1
        return V1_HEXMERGE_LOG if attempts["n"] == 1 else CLEAN_SUCCESS_LOG

    hex_present_by_attempt = {1: False, 2: True}
    monkeypatch.setattr(make_deploy, "_run_pxt_build", fake_run)
    monkeypatch.setattr(
        make_deploy.os.path, "exists",
        lambda path: hex_present_by_attempt.get(attempts["n"], False)
        if path == make_deploy.HEX else True,
    )
    monkeypatch.setattr(make_deploy.os.path, "getsize", lambda path: 123456)

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
