"""tests/host/test_wifi_join_error_debug_source_pin.py -- pins
`Protocol::emitWifiDebug()`'s new `join=` field for sprint 038 ticket
001,
clasi/sprints/038-flash-backed-wifi-credential-store-with-join-failure-diagnostics/tickets/
001-wifilink-retain-and-expose-the-cwjap-failure-code.md.

**What this is NOT.** Source-text pinning, following
`test_setupwifi_precedence_source_pin.py`'s own precedent (itself
following `test_dispatched_job_motion_source_pin.py`) of
regex-asserting on source text without compiling it --
`src/comms/protocol.cpp` includes `pxt.h`, directly and transitively,
so `tests/host/` cannot compile or execute it at all. This file cannot
prove `emitWifiDebug()` produces a correct byte stream on real
hardware -- only that the source shape emitting `join=` from
`WifiLink::lastJoinError()` is present, and that a pure-Python
worst-case reconstruction of the format string's substitutions fits
`wifiDbgBuf_`'s declared capacity.

`WifiLink::lastJoinError()` ITSELF -- capture, retention across
kJoin -> kBackoff, and the no-stale-value reset on each new attempt --
is exercised directly (not source-pinned) by
`tests/host/test_wifi_link.py`, because `wifi_link.cpp` is
host-portable and DOES compile under `tests/host/` (no `pxt.h`). This
file is only for the `Protocol`-side wiring that cannot be.

The `+CWJAP:<code>` -> word mapping (1=timeout, 2=wrong password,
3=AP not found, 4=connect failed) is read from ESP-AT/Ai-WB2 vendor
documentation, not measured, and is UNVERIFIED on the Ai-WB2-12F --
see `.claude/rules/measurement-citations.md` and
`clasi/issues/wifi-join-failure-does-not-say-why.md`. Nothing in this
file, `emitWifiDebug()`, or `WifiLink` maps the code to a word; this
suite would need to change if a future ticket ever adds one.

Run with::

    uv run pytest tests/host/test_wifi_join_error_debug_source_pin.py
"""
import pathlib
import re

# tests/host/test_wifi_join_error_debug_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"
_PROTOCOL_H = _REPO_ROOT / "src" / "comms" / "protocol.h"
_WIFI_LINK_H = _REPO_ROOT / "src" / "comms" / "wifi_link.h"


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    duplicated from test_setupwifi_precedence_source_pin.py per that
    file's own note that each source-pin test stays self-contained."""
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


def _function_body(source_text, signature_pattern, label, path):
    m = re.search(signature_pattern, source_text)
    assert m, (
        f"{label}: no match for {signature_pattern!r} in "
        f"{path.relative_to(_REPO_ROOT)} -- has this function been "
        f"renamed or removed?"
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
_WIFI_LINK_H_STRIPPED = _strip_comments(_WIFI_LINK_H.read_text())

_EMIT_WIFI_DEBUG_SIG = r"void\s+Protocol::emitWifiDebug\s*\(\s*\)\s*\{"


def _emit_wifi_debug_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _EMIT_WIFI_DEBUG_SIG, "Protocol::emitWifiDebug",
        _PROTOCOL_CPP,
    )


# ---------------------------------------------------------------------
# 1. join= is present, sourced from wifiLink_.lastJoinError(), and
#    never carries the credential (a bare code/"-", not a word).
# ---------------------------------------------------------------------

def test_join_field_present_and_sourced_from_last_join_error():
    body = _emit_wifi_debug_body()
    assert "join=" in body, (
        f"Protocol::emitWifiDebug(): format string is missing 'join=':\n{body}"
    )
    assert re.search(r"wifiLink_\.lastJoinError\s*\(\s*\)", body), (
        f"Protocol::emitWifiDebug(): join= is not sourced from "
        f"wifiLink_.lastJoinError():\n{body}"
    )
    # No literal wifiPassword_/config_.password read anywhere near this
    # field -- the hard sprint-wide constraint (no passphrase ever
    # leaves the board). A source-pin can't prove absence everywhere,
    # but this at least catches the field being fed from the wrong
    # member inside its own emitting function.
    assert "wifiPassword_" not in body, (
        f"Protocol::emitWifiDebug(): must never reference wifiPassword_ "
        f"-- no passphrase may appear on the wire:\n{body}"
    )


def test_last_join_error_getter_exists_and_is_not_word_mapped():
    """`WifiLink::lastJoinError()` must return the RAW vendor int --
    this ticket explicitly does not introduce a word mapping. Grepping
    wifi_link.h for a mapping table (e.g. a switch/array translating
    codes to strings) would be a regression this file exists to catch,
    though the presence check is necessarily loose (a source-pin can't
    prove a negative precisely) -- the getter's own return type is the
    concrete pin."""
    assert re.search(r"\bint\s+lastJoinError\s*\(\s*\)\s*const\b", _WIFI_LINK_H_STRIPPED), (
        "wifi_link.h: no 'int lastJoinError() const' getter found -- has "
        "it been renamed, removed, or changed to return something other "
        "than the raw vendor int (e.g. a mapped enum/string)?"
    )
    # A word-mapping regression would plausibly introduce one of these
    # vendor-meaning words near the getter; a loose grep across the
    # whole header catches the likely shape of that regression without
    # being so broad it flags legitimate prose in the ticket comment
    # above the getter (which itself must use these words to explain
    # why they are NOT mapped -- so this only checks for a `case`/array
    # mapping shape, not the words' mere presence).
    assert not re.search(
        r'"(timeout|wrong[_ ]password|ap[_ ]not[_ ]found|connect[_ ]failed)"',
        _WIFI_LINK_H_STRIPPED,
        re.IGNORECASE,
    ), (
        "wifi_link.h: found a quoted vendor-meaning string near "
        "lastJoinError() -- this ticket must not introduce a code-to-word "
        "mapping; that is explicitly out of scope until hardware "
        "confirmation (see the ticket's own Description)."
    )


# ---------------------------------------------------------------------
# 2. Byte budget: a pure-Python worst-case reconstruction of the
#    format string, with every %-substitution replaced by its type's
#    widest possible rendering, must fit wifiDbgBuf_'s declared size.
#    This restates the arithmetic from the ticket's own commit message
#    in a form CI re-checks on every run, rather than trusting the
#    comment never drifts from the code.
# ---------------------------------------------------------------------

_WIFI_DBG_BUF_DECL_RE = re.compile(r"\bwifiDbgBuf_\s*\[\s*(\d+)\s*\]\s*;")

# Worst-case field widths, by C++ type, for every %-conversion in
# emitWifiDebug()'s format string (see src/comms/protocol.cpp). Traced
# to each field's declared type in wifi_link.h / protocol.h -- not
# measured, this is arithmetic over declared sizes, same category as
# the ticket's own budget note.
_WORST_CASE_FIELDS = {
    "state": "6",              # WifiLink::State, 0..6 -> 1 digit
    "ip": "2" * 15,            # char[16] ownIp_/peerIp_ -> up to 15 chars
    "peer": "2" * 15,
    "port": "6" * 5,           # uint16_t max 65535
    "tcp": "2" * 3,            # uint8_t tcpOpenMask_, worst-case 3 digits
    "replyLink": "-128",       # int8_t replyLink_
    "to": "1",
    "restarts": "4" * 10,      # uint32_t max 4294967295
    "sent": "4" * 10,
    "rx": "4" * 10,
    "drop": "4" * 10,
    "mdns": "4" * 10,
    "mdnsOpen": "1",
    "cmd": "c" * 47,           # WifiLink::kTraceCommand=48 -> 47 chars + NUL
    "reply": "r" * 71,         # WifiLink::kTraceReply=72 -> 71 chars + NUL
    "credsrc": "1",
    "trunc": "2" * 3,          # uint8_t wifiCredsTruncated_, worst-case 3 digits
    "join": "9" * 2,           # lastJoinError() capture caps at 2 ASCII digits
}


def _worst_case_line_length():
    fmt = (
        "DBG:wifi state={state} ip={ip} peer={peer}:{port} tcp={tcp}/{replyLink} "
        "to={to} restarts={restarts} sent={sent} rx={rx} drop={drop} "
        "mdns={mdns}/{mdnsOpen} cmd={cmd} reply={reply} "
        "credsrc={credsrc} trunc={trunc} join={join}"
    )
    return len(fmt.format(**_WORST_CASE_FIELDS))


def test_worst_case_dbg_wifi_line_fits_the_declared_buffer():
    decl_match = _WIFI_DBG_BUF_DECL_RE.search(_PROTOCOL_H_STRIPPED)
    assert decl_match, (
        f"wifiDbgBuf_ array declaration not found in "
        f"{_PROTOCOL_H.relative_to(_REPO_ROOT)} -- has it been renamed?"
    )
    buf_size = int(decl_match.group(1))
    worst_case_len = _worst_case_line_length()
    worst_case_with_nul = worst_case_len + 1
    assert worst_case_with_nul <= buf_size, (
        f"Worst-case DBG:wifi line ({worst_case_len} chars + NUL = "
        f"{worst_case_with_nul}) does not fit wifiDbgBuf_[{buf_size}] -- "
        f"snprintf() will silently truncate on a real worst-case reply. "
        f"Grow the buffer or shorten a field."
    )
    # This ticket's own commit message states the exact used/remaining
    # count (see git log) -- 323/384 used, 61 bytes remaining for
    # ticket 006's ssid=/haspw= fields. Re-derive it here so that
    # number can never silently drift from the code.
    assert worst_case_with_nul == 323, (
        f"Worst-case DBG:wifi line is now {worst_case_with_nul}/384 bytes "
        f"(expected 323) -- a field changed width since this ticket's "
        f"commit message computed the budget for ticket 006. Update the "
        f"ticket's own recorded byte count and this pinned value together."
    )


def test_join_field_format_matches_the_two_digit_or_dash_shape():
    """emitWifiDebug() must build the join value with %s from a small
    stack buffer that is either "-" or the raw integer -- not %d
    directly on lastJoinError(), which would print "0" (the sentinel)
    instead of "-" for "no code captured", silently losing the
    distinction the whole ticket exists to preserve."""
    body = _emit_wifi_debug_body()
    # The format string is built from adjacent C string-literal chunks
    # (compiler-concatenated), so "join=%s" need not be its own quoted
    # literal -- just present, verbatim, as a %s conversion (not %d).
    assert re.search(r"join=%s\b", body), (
        f"Protocol::emitWifiDebug(): expected a %s conversion for "
        f"join= (built from a local buffer that renders the sentinel as "
        f"'-'), not %d directly on lastJoinError():\n{body}"
    )
    assert not re.search(r"join=%d\b", body), (
        f"Protocol::emitWifiDebug(): join= must not be a raw %d on "
        f"lastJoinError() -- that would print '0' for the sentinel "
        f"instead of '-':\n{body}"
    )
