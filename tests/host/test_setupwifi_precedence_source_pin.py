"""tests/host/test_setupwifi_precedence_source_pin.py -- pins
`Protocol::setupWifi()`'s precedence flag, late-call guard, and
truncation bookkeeping in `src/comms/protocol.cpp`/`protocol.h` for
sprint 036 ticket 003,
clasi/sprints/036-runtime-wifi-credentials-via-setupwifi/tickets/
003-host-level-test-setupwifi-precedence-truncation-and-late-call-
behavior.md.

**What this is NOT.** Source-text pinning, following
`test_dispatched_job_motion_source_pin.py`'s own precedent of
regex-asserting on source text without compiling it -- `tests/host/`
cannot compile `protocol.cpp` at all (it includes `pxt.h`, directly
and transitively; confirmed by that file and by
`test_protocol_stack_canary_source_pin.py`, both of which document the
same blocker). It cannot prove `WifiLink::begin()` actually treats an
explicit empty SSID as a deliberate disable, or that a late
`setupWifi()` call genuinely leaves an in-progress join untouched, on
real hardware -- only that the source shape which makes those things
true is present and has not regressed back to the rejected ternary.
The late-call guard's behavior in particular is UNVERIFIED on
hardware: its correctness is reasoned from reading
`src/comms/wifi_link.cpp`'s `serviceJoin()` (source reading, not a
measurement -- see `.claude/rules/measurement-citations.md`), which is
exactly why this file exists: to catch a regression in the WIRING
(does `setupWifi()` actually refuse the late write, does
`serviceWifi()` actually key off the flag) rather than to re-prove the
reasoning from first principles.

**Why each pin is aimed at a specific regression, not "the text is
present".**

1. `test_late_call_guard_gates_before_any_store_write` -- the ticket's
   own worry is a guard that is *present but ineffective*: checked
   after the writes, or only in a comment. This pins the `wifiBegun_`
   check textually BEFORE every one of the four writes it must gate
   (`wifiSsid_`, `wifiPassword_`, `wifiCredsExplicit_`,
   `wifiCredsTruncated_`), and separately pins that the guard's `return`
   actually prevents fallthrough to those writes (single function body,
   guard clause with its own `return`).
2. `test_service_wifi_branches_on_explicit_flag_not_ternary` -- the
   specific bug class ticket 001 exists to avoid regressing into. A
   pin that only searches for `wifiCredsExplicit_` somewhere in the
   file is weak: this asserts the REJECTED shape
   (`wifiSsid_[0] ? wifiSsid_ : kWifiSsid`, in any equivalent
   whitespace) is ABSENT from `serviceWifi()`'s body, in addition to
   asserting the accepted `if (wifiCredsExplicit_)` shape is present.
3. `test_truncation_computed_before_copy_from_both_fields` -- pins
   that both `wifiSsid_` and `wifiPassword_` get a `strlen(...) >=
   sizeof(...)` check that assigns into `wifiCredsTruncated_`, and that
   this happens textually before the `snprintf` calls that fill the
   storage (truncation must describe the caller's input, not an
   artifact of an already-clipped copy).
4. `test_enable_wifi_reached_unconditionally_on_non_late_path` --
   `setupWifi("")` must still enable (SUC-002): this pins that
   `enableWifi()` is called in `setupWifi()`'s body with no
   conditional on the ssid argument's truthiness guarding it.
5. `test_wifi_debug_buffer_grown_and_fields_present` -- pins
   `wifiDbgBuf_[384]` (not reverted to 320) AND that
   `emitWifiDebug()`'s format string carries both `credsrc=` and
   `trunc=` -- together, because the point of ticket 001's buffer
   growth was specifically to give the new fields room; pinning one
   without the other would miss a regression that re-shrinks the
   buffer while leaving the fields in the (now truncated-at-runtime)
   format string.
6. `test_bake_path_untouched_wifi_ssid_password_lines` -- confirms the
   byte-identical DO-NOT-REFORMAT lines
   `tools/make_deploy.py::_inject_wifi_secrets()` regexes are still
   present verbatim. `tests/tools/test_make_deploy_wifi.py` already
   pins this from the deploy-tool side; this is the same invariant
   read from the protocol.cpp side, as a second failure point close to
   the code most likely to disturb it.

A tiny host-computable cross-check
(`test_truncation_boundary_constants_agree_with_cell_sizes`) restates
the truncation boundary math (`len >= size` against sizes 33/64) in
pure Python with no `pxt.h`/CODAL dependency, as optional polish per
the ticket -- it is a sanity check on the constants, not a substitute
for the source-pin assertions above, which are what actually verify
the shipped code.

Run with::

    uv run pytest tests/host/test_setupwifi_precedence_source_pin.py
"""
import pathlib
import re

# tests/host/test_setupwifi_precedence_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"
_PROTOCOL_H = _REPO_ROOT / "src" / "comms" / "protocol.h"


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    see test_bus_guard_source_pin.py's identical helper for the full
    rationale. Duplicated here rather than imported: each source-pin
    test file in this directory stays self-contained, the same
    precedent test_dispatched_job_motion_source_pin.py itself follows
    (confirmed no shared helper module exists in tests/host/ as of
    this ticket)."""
    out_lines = []
    in_block = False
    for raw in text.splitlines():
        line = raw
        if in_block:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block = False
            else:
                out_lines.append("")
                continue
        while "/*" in line:
            head, _, rest = line.partition("/*")
            if "*/" in rest:
                line = head + rest.split("*/", 1)[1]
            else:
                line = head
                in_block = True
                break
        line = line.split("//", 1)[0]
        out_lines.append(line)
    return "\n".join(out_lines)


def _function_body(source_text, signature_pattern, label):
    """Finds `signature_pattern` (a regex matching through the function's
    opening `{`) and returns the brace-matched body (not including the
    enclosing braces). Fails loudly, naming `label`, if the signature is
    not found -- distinguishing "renamed or removed" from "exists but
    lacks the call"."""
    m = re.search(signature_pattern, source_text)
    assert m, (
        f"{label}: no match for {signature_pattern!r} in "
        f"{_PROTOCOL_CPP.relative_to(_REPO_ROOT)} -- has this function "
        f"been renamed or removed?"
    )
    depth = 0
    i = m.end() - 1  # the opening '{' itself
    while i < len(source_text):
        if source_text[i] == "{":
            depth += 1
        elif source_text[i] == "}":
            depth -= 1
            if depth == 0:
                return source_text[m.end():i]
        i += 1
    raise AssertionError(f"{label}: unbalanced braces scanning body")


_PROTOCOL_CPP_STRIPPED = _strip_comments(_PROTOCOL_CPP.read_text())
_PROTOCOL_H_STRIPPED = _strip_comments(_PROTOCOL_H.read_text())

_SETUP_WIFI_SIG = (
    r"void\s+Protocol::setupWifi\s*\(\s*const\s+char\s*\*\s*ssid\s*,"
    r"\s*const\s+char\s*\*\s*password\s*\)\s*\{"
)
_SERVICE_WIFI_SIG = r"void\s+Protocol::serviceWifi\s*\(\s*\)\s*\{"
_EMIT_WIFI_DEBUG_SIG = r"void\s+Protocol::emitWifiDebug\s*\(\s*\)\s*\{"


def _setup_wifi_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _SETUP_WIFI_SIG, "Protocol::setupWifi"
    )


def _service_wifi_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _SERVICE_WIFI_SIG, "Protocol::serviceWifi"
    )


def _emit_wifi_debug_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _EMIT_WIFI_DEBUG_SIG, "Protocol::emitWifiDebug"
    )


# ---------------------------------------------------------------------
# 1. Late-call guard: present, gates BEFORE the writes, and its
#    `return` actually short-circuits fallthrough to them.
# ---------------------------------------------------------------------

_LATE_CALL_GUARD_RE = re.compile(
    r"if\s*\(\s*wifiBegun_\s*\)\s*\{[^}]*?return\s*;[^}]*?\}", re.DOTALL
)

_WRITE_TARGETS = [
    # (label, regex matching an assignment/write to this member)
    ("wifiSsid_", re.compile(r"wifiSsid_\s*(?:\[|,|=)")),
    ("wifiPassword_", re.compile(r"wifiPassword_\s*(?:\[|,|=)")),
    ("wifiCredsExplicit_", re.compile(r"wifiCredsExplicit_\s*=")),
    ("wifiCredsTruncated_", re.compile(r"wifiCredsTruncated_\s*(?:\|=|=)")),
]


def test_late_call_guard_gates_before_any_store_write():
    """setupWifi() must refuse the STORE once wifiBegun_ is true -- not
    merely skip the enable. WifiLink::Config's ssid/password are
    pointers into wifiSsid_/wifiPassword_ that serviceJoin() re-reads
    on every join attempt and backoff retry
    (src/comms/wifi_link.cpp:538, :560-561; source reading, not
    measured -- the late-call path is UNVERIFIED on hardware), so a
    guard present only as a comment, or checked AFTER the writes
    already happened, would let a late call reach into a live join.
    This asserts the wifiBegun_ guard clause (with its own `return`)
    appears textually before each of the four writes it exists to
    prevent."""
    body = _setup_wifi_body()

    guard_match = _LATE_CALL_GUARD_RE.search(body)
    assert guard_match, (
        "Protocol::setupWifi(): no 'if (wifiBegun_) { ... return; ... }' "
        f"late-call guard found in the body:\n{body}"
    )
    guard_end = guard_match.end()

    for label, write_re in _WRITE_TARGETS:
        write_match = write_re.search(body)
        assert write_match, (
            f"Protocol::setupWifi(): no write to {label} found in the "
            f"body -- has the store logic moved or been renamed?:\n{body}"
        )
        assert guard_end <= write_match.start(), (
            f"Protocol::setupWifi(): the wifiBegun_ late-call guard does "
            f"not appear BEFORE the write to {label} -- a late call could "
            f"reach this write instead of being refused:\n{body}"
        )


def test_late_call_guard_keys_off_wifi_begun_flag():
    """The guard must specifically be wifiBegun_ -- not some other
    proxy (e.g. wifiEnabled_, or a state check on wifiLink_) that
    might look similar but does not track "has begin() already run
    and handed out live Config pointers"."""
    body = _setup_wifi_body()
    assert re.search(r"\bwifiBegun_\b", body), (
        f"Protocol::setupWifi(): no reference to wifiBegun_ at all in "
        f"the body:\n{body}"
    )


# ---------------------------------------------------------------------
# 2. Precedence: serviceWifi() must branch on wifiCredsExplicit_, not
#    the rejected ternary keyed off wifiSsid_[0].
# ---------------------------------------------------------------------

# The rejected shape from the prior-art patch: wifiSsid_[0] ? wifiSsid_
# : kWifiSsid (any whitespace variant). It cannot distinguish
# setupWifi("") from "never called" -- both leave wifiSsid_[0] == '\0'.
_REJECTED_TERNARY_RE = re.compile(
    r"wifiSsid_\s*\[\s*0\s*\]\s*\?\s*wifiSsid_\s*:\s*kWifiSsid"
)

_EXPLICIT_IF_RE = re.compile(r"if\s*\(\s*wifiCredsExplicit_\s*\)")


def test_service_wifi_branches_on_explicit_flag_not_ternary():
    """serviceWifi()'s lazy-begin branch must key off
    wifiCredsExplicit_, and must NOT be the rejected ternary
    `wifiSsid_[0] ? wifiSsid_ : kWifiSsid`. That ternary is the
    prior-art patch's approach and is wrong here -- it conflates
    setupWifi("") (explicitly disable) with "never called" (use the
    bake), which is exactly the bug ticket 001 exists to avoid
    regressing into. A pin that merely finds wifiCredsExplicit_
    somewhere would pass even if the ternary were reintroduced
    alongside it as dead or shadowing code, so this asserts the
    ternary's absence as its own check, not just the flag's
    presence."""
    body = _service_wifi_body()

    assert not _REJECTED_TERNARY_RE.search(body), (
        "Protocol::serviceWifi(): found the REJECTED ternary "
        "'wifiSsid_[0] ? wifiSsid_ : kWifiSsid' -- this is the prior-art "
        "patch's precedence bug (it cannot distinguish setupWifi(\"\") "
        "from 'never called'), which ticket 001 was written to remove:"
        f"\n{body}"
    )
    assert _EXPLICIT_IF_RE.search(body), (
        "Protocol::serviceWifi(): no 'if (wifiCredsExplicit_)' branch "
        f"found -- the lazy-begin config must key off this flag:\n{body}"
    )
    # And the branch must still fall back to the baked constants in the
    # else arm, or "never called" would stop using the deploy-time bake.
    assert re.search(r"config\.ssid\s*=\s*kWifiSsid", body), (
        f"Protocol::serviceWifi(): no 'config.ssid = kWifiSsid' fallback "
        f"found -- the bake path must remain reachable when "
        f"wifiCredsExplicit_ is false:\n{body}"
    )
    assert re.search(r"config\.ssid\s*=\s*wifiSsid_", body), (
        f"Protocol::serviceWifi(): no 'config.ssid = wifiSsid_' found -- "
        f"the explicit-program path must use the stored credentials:"
        f"\n{body}"
    )


# ---------------------------------------------------------------------
# 3. Truncation computed before the copy, from both fields.
# ---------------------------------------------------------------------

_TRUNC_SSID_RE = re.compile(
    r"strlen\s*\(\s*ssid\s*\)\s*>=\s*sizeof\s*\(\s*wifiSsid_\s*\)"
)
_TRUNC_PASSWORD_RE = re.compile(
    r"strlen\s*\(\s*password\s*\)\s*>=\s*sizeof\s*\(\s*wifiPassword_\s*\)"
)
_TRUNC_ASSIGN_RE = re.compile(r"wifiCredsTruncated_\s*(?:\|=|=)")
_SNPRINTF_SSID_RE = re.compile(r"snprintf\s*\(\s*wifiSsid_\s*,")
_SNPRINTF_PASSWORD_RE = re.compile(r"snprintf\s*\(\s*wifiPassword_\s*,")


def test_truncation_computed_before_copy_from_both_fields():
    """Both wifiSsid_ and wifiPassword_ must have a length check
    against their sizeof prior to the snprintf that fills them, with
    wifiCredsTruncated_ assigned from that check -- so the flag
    describes the CALLER's input length, not an artifact of an
    already-clipped copy. This pins both fields' checks and both
    copies' relative order, not just their presence."""
    body = _setup_wifi_body()

    ssid_check = _TRUNC_SSID_RE.search(body)
    password_check = _TRUNC_PASSWORD_RE.search(body)
    assert ssid_check, (
        f"Protocol::setupWifi(): no 'strlen(ssid) >= sizeof(wifiSsid_)' "
        f"truncation check found:\n{body}"
    )
    assert password_check, (
        f"Protocol::setupWifi(): no 'strlen(password) >= "
        f"sizeof(wifiPassword_)' truncation check found:\n{body}"
    )

    truncated_assigns = list(_TRUNC_ASSIGN_RE.finditer(body))
    assert truncated_assigns, (
        f"Protocol::setupWifi(): no assignment to wifiCredsTruncated_ "
        f"found:\n{body}"
    )
    last_truncated_assign_end = truncated_assigns[-1].end()

    ssid_copy = _SNPRINTF_SSID_RE.search(body)
    password_copy = _SNPRINTF_PASSWORD_RE.search(body)
    assert ssid_copy, (
        f"Protocol::setupWifi(): no 'snprintf(wifiSsid_, ...)' copy "
        f"found:\n{body}"
    )
    assert password_copy, (
        f"Protocol::setupWifi(): no 'snprintf(wifiPassword_, ...)' copy "
        f"found:\n{body}"
    )

    assert last_truncated_assign_end <= ssid_copy.start(), (
        "Protocol::setupWifi(): wifiCredsTruncated_ is assigned AFTER "
        "the wifiSsid_ snprintf copy -- truncation must be computed "
        f"from the caller's un-clipped input, before the copy:\n{body}"
    )
    assert last_truncated_assign_end <= password_copy.start(), (
        "Protocol::setupWifi(): wifiCredsTruncated_ is assigned AFTER "
        "the wifiPassword_ snprintf copy -- truncation must be computed "
        f"from the caller's un-clipped input, before the copy:\n{body}"
    )


# ---------------------------------------------------------------------
# 4. enableWifi() reached unconditionally on the non-late-call path --
#    setupWifi("") must still enable (SUC-002).
# ---------------------------------------------------------------------

def test_enable_wifi_reached_unconditionally_on_non_late_path():
    """setupWifi("") is a deliberate explicit disable that must still
    enable the link (WifiLink::begin() is what turns an empty SSID
    into kDisabled, not a guard here) -- so enableWifi() must not be
    gated behind a truthiness check on the ssid argument, e.g.
    `if (ssid[0]) enableWifi();` would silently break SUC-002. This
    finds the enableWifi() call in the body and confirms it is not
    immediately preceded by a conditional testing ssid's truthiness on
    the same or an enclosing single-statement guard."""
    body = _setup_wifi_body()

    enable_call = re.search(r"\benableWifi\s*\(\s*\)\s*;", body)
    assert enable_call, (
        f"Protocol::setupWifi(): no enableWifi() call found -- "
        f"'stores AND enables' requires this call in the non-late-call "
        f"path:\n{body}"
    )

    # Must not be wrapped as `if (ssid...) enableWifi();` or
    # `if (ssid...) { ... enableWifi(); }` with no unconditional
    # counterpart -- scan backwards from the call for the nearest
    # enclosing `if` on the ssid argument's truthiness.
    preceding = body[: enable_call.start()]
    assert not re.search(r"if\s*\(\s*ssid\s*\[\s*0\s*\]\s*\)\s*\{?\s*$",
                          preceding.rstrip()), (
        "Protocol::setupWifi(): enableWifi() appears gated behind a "
        "truthiness check on ssid -- setupWifi(\"\") must still call "
        f"enableWifi() per SUC-002:\n{body}"
    )

    # And the call must not be inside the late-call guard's own braces
    # (that guard returns before reaching here; this is really a
    # cross-check that the guard tested in section 1 is the ONLY early
    # return before enableWifi()).
    guard_match = _LATE_CALL_GUARD_RE.search(body)
    assert guard_match and guard_match.end() <= enable_call.start(), (
        f"Protocol::setupWifi(): enableWifi() call is not textually "
        f"after the late-call guard clause:\n{body}"
    )


# ---------------------------------------------------------------------
# 5. wifiDbgBuf_ grown to 384, and emitWifiDebug()'s format string
#    carries both credsrc= and trunc=.
# ---------------------------------------------------------------------

_WIFI_DBG_BUF_DECL_RE = re.compile(r"\bwifiDbgBuf_\s*\[\s*(\d+)\s*\]\s*;")


def test_wifi_debug_buffer_grown_and_fields_present():
    """wifiDbgBuf_ must still be the grown size (384, up from 320) AND
    emitWifiDebug()'s format string must contain both credsrc= and
    trunc= -- pinned together, because the point of growing the buffer
    was specifically to give these new fields headroom (ticket 001's
    own budget: ~294/320 bytes already used by the pre-existing fields,
    leaving only ~26 bytes -- too tight for a ~19-byte addition and any
    future headroom). A regression that shrinks the buffer back to 320
    while leaving the fields in the format string would make the very
    diagnostic that exists to show truncation itself silently truncate
    at emitLine()'s wire cap."""
    decl_match = _WIFI_DBG_BUF_DECL_RE.search(_PROTOCOL_H_STRIPPED)
    assert decl_match, (
        f"wifiDbgBuf_ array declaration not found in "
        f"{_PROTOCOL_H.relative_to(_REPO_ROOT)} -- has it been renamed?"
    )
    size = int(decl_match.group(1))
    assert size == 384, (
        f"wifiDbgBuf_ is declared as [{size}], expected [384] -- ticket "
        f"001 grew it from 320 to 384 specifically to fit the new "
        f"credsrc=/trunc= fields with headroom; a shrink back to 320 "
        f"reopens the risk that the DBG:wifi line silently truncates."
    )

    debug_body = _emit_wifi_debug_body()
    assert "credsrc=" in debug_body, (
        f"Protocol::emitWifiDebug(): format string is missing "
        f"'credsrc=':\n{debug_body}"
    )
    assert "trunc=" in debug_body, (
        f"Protocol::emitWifiDebug(): format string is missing "
        f"'trunc=':\n{debug_body}"
    )
    # Both fields must actually be fed by the two new members, not just
    # present as literal text with nothing supplying them.
    assert re.search(r"wifiCredsExplicit_\s*\?\s*1\s*:\s*0", debug_body), (
        f"Protocol::emitWifiDebug(): credsrc= field is not sourced from "
        f"wifiCredsExplicit_:\n{debug_body}"
    )
    assert re.search(r"wifiCredsTruncated_", debug_body), (
        f"Protocol::emitWifiDebug(): trunc= field is not sourced from "
        f"wifiCredsTruncated_:\n{debug_body}"
    )


# ---------------------------------------------------------------------
# 6. The bake path is untouched -- the DO-NOT-REFORMAT lines
#    tools/make_deploy.py::_inject_wifi_secrets() regexes must remain
#    byte-identical. (Second failure point alongside
#    tests/tools/test_make_deploy_wifi.py, which pins this from the
#    deploy-tool side.)
# ---------------------------------------------------------------------

def test_bake_path_untouched_wifi_ssid_password_lines():
    """With wifiCredsExplicit_ false, kWifiSsid/kWifiPassword must
    still be what serviceWifi() uses for the bake -- and the constant
    DECLARATIONS themselves (the lines
    tools/make_deploy.py::_inject_wifi_secrets() regexes to inject a
    deploy-time bake) must remain present verbatim. This is a source
    reading of protocol.cpp, not a run of make_deploy.py --
    tests/tools/test_make_deploy_wifi.py is the authoritative pin for
    the regex/injection behavior itself; this is a second, cheaper
    tripwire close to the code most likely to disturb it."""
    raw_text = _PROTOCOL_CPP.read_text()
    assert re.search(
        r'constexpr const char\* kWifiSsid = "";', raw_text
    ), (
        "src/comms/protocol.cpp: the "
        "'constexpr const char* kWifiSsid = \"\";' DO-NOT-REFORMAT line "
        "(tools/make_deploy.py::_inject_wifi_secrets() regex target) "
        "was not found byte-identical."
    )
    assert re.search(
        r'constexpr const char\* kWifiPassword = "";', raw_text
    ), (
        "src/comms/protocol.cpp: the "
        "'constexpr const char* kWifiPassword = \"\";' DO-NOT-REFORMAT "
        "line (tools/make_deploy.py::_inject_wifi_secrets() regex "
        "target) was not found byte-identical."
    )


# ---------------------------------------------------------------------
# Optional polish: pure-host cross-check on the truncation boundary
# math against the sizes wifiSsid_[33] / wifiPassword_[64] use. Not a
# substitute for the source-pin assertions above.
# ---------------------------------------------------------------------

def _would_truncate(value, cell_size):
    """Re-derives setupWifi()'s own boundary check
    (strlen(value) >= sizeof(cell)) in plain host Python, against the
    same constants (33, 64) protocol.h declares for wifiSsid_/
    wifiPassword_. Pure sanity cross-check on the constants -- it does
    not exercise any shipped code."""
    return len(value) >= cell_size


def test_truncation_boundary_constants_agree_with_cell_sizes():
    # wifiSsid_[33]: a 32-char SSID fits (802.11 max), 33 does not.
    assert _would_truncate("s" * 32, 33) is False
    assert _would_truncate("s" * 33, 33) is True
    # wifiPassword_[64]: a 63-char WPA2 passphrase fits, 64 does not.
    assert _would_truncate("p" * 63, 64) is False
    assert _would_truncate("p" * 64, 64) is True
