"""tests/host/test_wifi_flash_port_write_sense_source_pin.py -- pins the
success/failure SENSE of `WifiFlashPortCodal::write()` in
`src/platform/wifi_flash_port.cpp` (038-002 repair, found by sprint 038
ticket 004's hardware run).

`src/platform/wifi_flash_port.cpp` is the ONE translation unit in the
credential-store feature that reaches real CODAL flash
(`codal::MicroBitFlash`) -- host tests
(`tests/host/test_wifi_credential_store.py`) exercise
`WifiCredentialStore` against `tests/host/wifi_flash_port_shim.cpp`'s
fake, in-memory `WifiFlashPort` instead, because there is no real flash
on the host. That fake is a fine seam for `WifiCredentialStore`'s own
logic, but it cannot catch a bug in the REAL wrapper's comparison
against `codal::MicroBitFlash::flash_write()`'s return value -- which
is exactly what broke here. So this file does the only thing available
on the host: pins the source text of the comparison itself.

**What this is NOT.** No compile of wifi_flash_port.cpp (it pulls in
pxt.h and the real CODAL headers, which is not a host-buildable
target), no C++ compiler invocation at all -- pure source-text pinning,
same convention as every other `*_source_pin.py` file in this
directory.

**The bug this pins against regressing.** The vendored header's doc
comment is wrong:
`built/dockercodal/libraries/codal-microbit-v2/inc/MicroBitFlash.h:61`
says "@return non-zero on sucess, zero on error" for
`MicroBitFlash::flash_write()`. The actual implementation
(`built/dockercodal/libraries/codal-microbit-v2/source/MicroBitFlash.cpp`)
returns `MICROBIT_OK` (0) on its success path and
`MICROBIT_INVALID_PARAMETER` (-1001, non-zero) from its guard
failures -- the header's doc is backwards. A `!= 0` comparison against
that return value reads a successful write as a failure and a rejected
write as a success.

MEASURED gopiv 2026-09-09 (team-lead's own hardware run, sprint 038
ticket 004): with the old `!= 0` comparison flashed, `WIFICRED SET 0
TestNet038 secretpw038 #2` returned `err 3` and a following `WIFICRED
#3` enumerated nothing, even though slot 0 and both strings were well
within range. Artifact: `captures/wifi-credential-store-20260909/`.

The fix compares against the named constant `MICROBIT_OK` with `==`,
not a bare `0` with `!=` -- pinned here so a well-meaning "fix" that
reads the (wrong) vendored doc comment and flips the sense back does
not silently reintroduce this.

Run with::

    uv run pytest tests/host/test_wifi_flash_port_write_sense_source_pin.py
"""
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_WIFI_FLASH_PORT_CPP = _REPO_ROOT / "src" / "platform" / "wifi_flash_port.cpp"
_MICROBIT_FLASH_H = (
    _REPO_ROOT
    / "built"
    / "dockercodal"
    / "libraries"
    / "codal-microbit-v2"
    / "inc"
    / "MicroBitFlash.h"
)
_MICROBIT_FLASH_CPP = (
    _REPO_ROOT
    / "built"
    / "dockercodal"
    / "libraries"
    / "codal-microbit-v2"
    / "source"
    / "MicroBitFlash.cpp"
)

_SOURCE_TEXT = _WIFI_FLASH_PORT_CPP.read_text(encoding="utf-8")

_WRITE_FUNCTION_RE = re.compile(
    r"bool\s+WifiFlashPortCodal::write\s*\([^)]*\)\s*\{(?P<body>.*?)\n\}",
    re.DOTALL,
)


def _write_function_body():
    m = _WRITE_FUNCTION_RE.search(_SOURCE_TEXT)
    assert m, (
        f"{_WIFI_FLASH_PORT_CPP}: no match for "
        f"'bool WifiFlashPortCodal::write(...) {{ ... }}' -- has the "
        f"function been renamed, removed, or had its signature changed?"
    )
    return m.group("body")


def test_write_return_compares_against_microbit_ok_by_name():
    """The line that turns flash_write()'s int return into this
    method's bool must spell out `MICROBIT_OK`, not a bare `0` -- using
    the named constant is what makes the comparison legible against
    ErrorNo.h's convention instead of silently depending on its
    numeric value."""
    body = _write_function_body()
    assert "MICROBIT_OK" in body, (
        f"WifiFlashPortCodal::write(): expected the flash_write() "
        f"return check to reference the named constant MICROBIT_OK, "
        f"found none in the body:\n{body}"
    )


def test_write_return_uses_equality_not_bare_nonzero_check():
    """MicroBitFlash::flash_write() returns MICROBIT_OK (0) on
    success and MICROBIT_INVALID_PARAMETER (non-zero) on its guard
    failures -- the OPPOSITE sense of the vendored header's doc
    comment. The comparison must be `== MICROBIT_OK` (success is the
    truthy case); a `!= 0` (or `!= MICROBIT_OK`, or any bare `0`
    comparison) reads success as failure and failure as success."""
    body = _write_function_body()
    assert re.search(r"==\s*MICROBIT_OK\b", body), (
        f"WifiFlashPortCodal::write(): expected the flash_write() "
        f"return to be compared with '== MICROBIT_OK', found no such "
        f"comparison in the body:\n{body}"
    )
    assert not re.search(r"!=\s*0\b", body), (
        f"WifiFlashPortCodal::write(): found a '!= 0' comparison in "
        f"the body -- this is the inverted-sense bug (038-002): "
        f"MicroBitFlash::flash_write() returns MICROBIT_OK (0) on "
        f"SUCCESS, so '!= 0' reads a successful write as a failure. "
        f"See the MEASURED comment on this line in "
        f"wifi_flash_port.cpp:\n{body}"
    )
    assert not re.search(r"!=\s*MICROBIT_OK\b", body), (
        f"WifiFlashPortCodal::write(): found a '!= MICROBIT_OK' "
        f"comparison in the body -- this inverts the sense the same "
        f"way '!= 0' does, since MICROBIT_OK is 0:\n{body}"
    )


def test_write_comment_cites_the_hardware_measurement():
    """Per .claude/rules/measurement-citations.md, the MEASURED claim
    backing this fix must name its artifact. Pinned so the comment
    (and its citation) cannot be silently deleted by a later edit that
    only touches the comparison."""
    body = _write_function_body()
    assert "MEASURED gopiv 2026-09-09" in body, (
        f"WifiFlashPortCodal::write(): expected a 'MEASURED gopiv "
        f"2026-09-09' citation in the body per "
        f".claude/rules/measurement-citations.md, found none:\n{body}"
    )
    assert "captures/wifi-credential-store-20260909" in body, (
        f"WifiFlashPortCodal::write(): expected the MEASURED comment "
        f"to name its artifact path "
        f"(captures/wifi-credential-store-20260909/), found none:"
        f"\n{body}"
    )


def test_vendored_header_doc_still_disagrees_with_its_own_implementation():
    """Confirms the premise this fix (and its comment) depends on: the
    vendored header's doc comment for flash_write() really does say
    the opposite of what the implementation does. If a vendor update
    ever corrects the header text, this test will fail and should be
    read as a prompt to re-check whether the implementation changed
    too -- not silently deleted."""
    if not _MICROBIT_FLASH_H.exists() or not _MICROBIT_FLASH_CPP.exists():
        pytest.skip(
            "vendored codal-microbit-v2 sources not present in this "
            "checkout (built/dockercodal/ is a generated tree)"
        )
    header_text = _MICROBIT_FLASH_H.read_text(encoding="utf-8")
    impl_text = _MICROBIT_FLASH_CPP.read_text(encoding="utf-8")

    assert "non-zero on sucess, zero on error" in header_text, (
        f"{_MICROBIT_FLASH_H}: expected flash_write()'s doc comment "
        f"to still claim 'non-zero on sucess, zero on error' -- if "
        f"this vendored text changed, re-check whether the "
        f"implementation's actual return convention changed with it "
        f"before assuming wifi_flash_port.cpp's comparison still "
        f"needs to disagree with the doc."
    )
    assert re.search(r"return\s+MICROBIT_OK\s*;", impl_text), (
        f"{_MICROBIT_FLASH_CPP}: expected flash_write()'s success "
        f"path to still 'return MICROBIT_OK;' -- if this changed, "
        f"wifi_flash_port.cpp's '== MICROBIT_OK' comparison may need "
        f"to change with it."
    )

