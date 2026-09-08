"""tests/host/test_setdevicerole_precedence_source_pin.py -- pins
`Protocol::setDeviceRole()`'s null guard, strip-then-accept whitespace
handling, strip-then-measure-then-clip truncation ordering, the
constructor's seeding shape, and `buildIdentity()`/`sendBanner()`'s
buffer wiring in `src/comms/protocol.cpp`/`protocol.h` and
`src/comms/wire_handler.cpp`, for sprint 037 ticket 004,
clasi/sprints/037-runtime-identity-setters-hello-banner-role-and-
common-name-are-hardcoded/tickets/004-host-level-source-pin-tests-
setdevicerole-precedence-truncation-whitespace-and-constructor-
seeding-shape.md.

**What this is NOT.** Source-text pinning, following
`test_dispatched_job_motion_source_pin.py`'s own precedent (and, more
directly, `test_setupwifi_precedence_source_pin.py`, sprint 036 ticket
003's sibling test for the same problem) of regex-asserting on source
text without compiling it -- `tests/host/` cannot compile
`protocol.cpp` at all (it includes `pxt.h`, directly and transitively;
confirmed by that file and by
`test_protocol_stack_canary_source_pin.py`). It cannot prove a live
`HELLO` reply is byte-identical on real hardware, or that
`setDeviceRole()` called after the first banner is actually picked up
by the NEXT one on a running board -- see ticket 007 for the
on-hardware side. Everything below is UNVERIFIED on hardware; it only
confirms the source SHAPE that would make those things true is present
and has not regressed.

**Why each pin is aimed at a specific regression, not "the text is
present".**

1. `test_null_guard_precedes_every_write` -- the null check
   (`role == nullptr || commonName == nullptr`) must gate BEFORE any
   write to `roleBuf_`/`commonNameBuf_`/`deviceRoleTruncated_`, not
   merely exist somewhere in the body.
2. `test_whitespace_is_stripped_not_rejected` -- the stakeholder
   decision this whole ticket exists to protect (`stakeholder_approval`
   gate, 2026-09-08): whitespace is stripped and the call still
   succeeds. This is a STRIP, not a REJECT, so the test asserts both
   the positive (a `stripWhitespaceInto()` call feeding each buffer)
   AND the negative (no `DBG:role rejected: whitespace` string
   anywhere in the file -- its presence means reject was
   re-implemented). Only `DBG:role rejected: null argument` may exist.
3. `test_truncation_uses_stripped_length_not_raw_strlen` -- the
   easiest thing in the sprint to get backwards per the ticket's own
   framing: this pins that `deviceRoleTruncated_` is computed from the
   variables `stripWhitespaceInto()` RETURNED (the true stripped
   length, per that function's own doc comment), not from
   `strlen(role)`/`strlen(commonName)` compared directly against
   `sizeof(...)`. A regression that measured the raw argument instead
   would satisfy a weaker "does roleLen >= sizeof(...) appear
   somewhere" pin while silently flagging whitespace-padded values as
   truncated when they are not.
4. `test_whitespace_only_overflow_does_not_truncate` -- the explicit
   overflow case the acceptance criteria calls out: an input whose RAW
   length exceeds the buffer only because of whitespace about to be
   stripped must NOT be flagged truncated. Re-derives
   `stripWhitespaceInto()`'s own pinned algorithm (strip, then count
   the FULL stripped length, independent of what fits the destination)
   in plain host Python against the real `roleBuf_`/`commonNameBuf_`
   sizes read from `protocol.h`, and cross-checks it against the
   source-pinned shape from test 3 above -- not a substitute for that
   pin, a concrete worked example of what it protects.
5. `test_no_late_call_guard` -- unlike `setupWifi()` (guarded because
   `WifiLink::Config` borrows into the credential buffers and
   `serviceJoin()` re-reads them on every retry --
   `wifi_link.cpp:538,560-561`), `sendBanner()` dereferences
   `identity.role`/`commonName` at EMIT time, so a call at any point
   (including after the first banner already went out) has no live
   read to corrupt and must succeed. This asserts `setDeviceRole()`'s
   body contains exactly ONE `return;` statement (the null guard's
   own) -- a second one, keyed off some "already begun" flag copied
   from `setupWifi()`'s shape, would silently refuse a legitimate
   late call.
6. `test_constructor_seeds_from_named_constants` -- `Protocol::
   Protocol()` must seed `roleBuf_`/`commonNameBuf_` from `kRole`/
   `kCommonName` by name, not inline literals -- a hardcoded
   `"NEZHA2"`/`"robot"` here would silently diverge from `kRole`/
   `kCommonName` the moment either constant is edited alone.
7. `test_build_identity_points_at_owned_buffers_not_constants` --
   `buildIdentity()` must assign `identity.role = roleBuf_` and
   `identity.commonName = commonNameBuf_`, never `identity.role =
   kRole` -- the specific regression this test exists to catch, since
   a revert to the constant would leave the DEFAULT-value tests
   passing (same string either way) while silently breaking every
   runtime `setDeviceRole()` call.
8. `test_nsdmi_comment_mentions_the_roleBuf_exception` -- the stale
   "NSDMI, not a hand-written constructor" comment (which used to
   claim every member is NSDMI'd, with no exception for the buffers a
   hand-written constructor now seeds) must stay amended to name that
   exception, not silently revert to the old blanket claim beside a
   constructor that would then contradict it.
9. `test_send_banner_format_string_and_kRoleCommonName_defaults` --
   the closest a source-pin test can get to "the default banner is
   byte-identical" without compiling: `kRole`/`kCommonName` are
   unchanged literal values, and `sendBanner()`'s format string is
   exactly `"device %s %s %s %s\\n"` reading, in order,
   `identity.role, identity.commonName, identity.name,
   identity.serial`.

Run with::

    uv run pytest tests/host/test_setdevicerole_precedence_source_pin.py
"""
import pathlib
import re

# tests/host/test_setdevicerole_precedence_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"
_PROTOCOL_H = _REPO_ROOT / "src" / "comms" / "protocol.h"
_WIRE_HANDLER_CPP = _REPO_ROOT / "src" / "comms" / "wire_handler.cpp"


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    see test_bus_guard_source_pin.py's identical helper for the full
    rationale. Duplicated here rather than imported: each source-pin
    test file in this directory stays self-contained, the same
    precedent test_dispatched_job_motion_source_pin.py and
    test_setupwifi_precedence_source_pin.py themselves follow
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


def _function_body(source_text, signature_pattern, label, filename):
    """Finds `signature_pattern` (a regex matching through the function's
    opening `{`) and returns the brace-matched body (not including the
    enclosing braces). Fails loudly, naming `label`, if the signature is
    not found -- distinguishing "renamed or removed" from "exists but
    lacks the call"."""
    m = re.search(signature_pattern, source_text)
    assert m, (
        f"{label}: no match for {signature_pattern!r} in {filename} -- "
        f"has this function been renamed or removed?"
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


_PROTOCOL_CPP_RAW = _PROTOCOL_CPP.read_text()
_PROTOCOL_H_RAW = _PROTOCOL_H.read_text()
_WIRE_HANDLER_CPP_RAW = _WIRE_HANDLER_CPP.read_text()

_PROTOCOL_CPP_STRIPPED = _strip_comments(_PROTOCOL_CPP_RAW)
_PROTOCOL_H_STRIPPED = _strip_comments(_PROTOCOL_H_RAW)
_WIRE_HANDLER_CPP_STRIPPED = _strip_comments(_WIRE_HANDLER_CPP_RAW)

_SET_DEVICE_ROLE_SIG = (
    r"void\s+Protocol::setDeviceRole\s*\(\s*const\s+char\s*\*\s*role\s*,"
    r"\s*const\s+char\s*\*\s*commonName\s*\)\s*\{"
)
_CONSTRUCTOR_SIG = r"Protocol::Protocol\s*\(\s*\)\s*\{"
_BUILD_IDENTITY_SIG = r"Wire::Identity\s+Protocol::buildIdentity\s*\(\s*\)\s*\{"
_STRIP_WHITESPACE_INTO_SIG = (
    r"size_t\s+stripWhitespaceInto\s*\(\s*const\s+char\s*\*\s*src\s*,"
    r"\s*char\s*\*\s*dst\s*,\s*size_t\s+dstSize\s*\)\s*\{"
)
_SEND_BANNER_SIG = r"void\s+WireHandler::sendBanner\s*\(\s*\)\s*\{"


def _set_device_role_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _SET_DEVICE_ROLE_SIG,
        "Protocol::setDeviceRole", "src/comms/protocol.cpp",
    )


def _constructor_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _CONSTRUCTOR_SIG,
        "Protocol::Protocol", "src/comms/protocol.cpp",
    )


def _build_identity_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _BUILD_IDENTITY_SIG,
        "Protocol::buildIdentity", "src/comms/protocol.cpp",
    )


def _strip_whitespace_into_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _STRIP_WHITESPACE_INTO_SIG,
        "stripWhitespaceInto", "src/comms/protocol.cpp",
    )


def _send_banner_body():
    return _function_body(
        _WIRE_HANDLER_CPP_STRIPPED, _SEND_BANNER_SIG,
        "WireHandler::sendBanner", "src/comms/wire_handler.cpp",
    )


# ---------------------------------------------------------------------
# 1. Null guard: present, and gates BEFORE every write it must prevent.
# ---------------------------------------------------------------------

_NULL_GUARD_RE = re.compile(
    r"if\s*\(\s*role\s*==\s*nullptr\s*\|\|\s*commonName\s*==\s*nullptr\s*\)"
    r"\s*\{[^}]*?return\s*;[^}]*?\}",
    re.DOTALL,
)

_WRITE_TARGETS = [
    ("roleBuf_", re.compile(r"roleBuf_\s*(?:\[|,|=)")),
    ("commonNameBuf_", re.compile(r"commonNameBuf_\s*(?:\[|,|=)")),
    ("deviceRoleTruncated_", re.compile(r"deviceRoleTruncated_\s*(?:\|=|=)")),
]


def test_null_guard_precedes_every_write():
    """The null check must gate BEFORE any write to
    roleBuf_/commonNameBuf_/deviceRoleTruncated_ -- a guard present but
    checked AFTER those writes (or only in a comment) would let a null
    argument reach stripWhitespaceInto()'s own dereference of `src`."""
    body = _set_device_role_body()

    guard_match = _NULL_GUARD_RE.search(body)
    assert guard_match, (
        "Protocol::setDeviceRole(): no "
        "'if (role == nullptr || commonName == nullptr) { ... return; ... }' "
        f"null guard found in the body:\n{body}"
    )
    guard_end = guard_match.end()

    for label, write_re in _WRITE_TARGETS:
        write_match = write_re.search(body)
        assert write_match, (
            f"Protocol::setDeviceRole(): no write to {label} found in the "
            f"body -- has the store logic moved or been renamed?:\n{body}"
        )
        assert guard_end <= write_match.start(), (
            f"Protocol::setDeviceRole(): the null guard does not appear "
            f"BEFORE the write to {label} -- a null argument could reach "
            f"this write instead of being refused:\n{body}"
        )


# ---------------------------------------------------------------------
# 2. Whitespace is STRIPPED, not rejected -- the stakeholder decision.
# ---------------------------------------------------------------------

_REJECTED_WHITESPACE_MSG = "DBG:role rejected: whitespace"
_ACCEPTED_NULL_MSG = "DBG:role rejected: null argument"

_STRIP_ROLE_RE = re.compile(
    r"\bstripWhitespaceInto\s*\(\s*role\s*,\s*roleBuf_\s*,"
    r"\s*sizeof\s*\(\s*roleBuf_\s*\)\s*\)"
)
_STRIP_COMMON_NAME_RE = re.compile(
    r"\bstripWhitespaceInto\s*\(\s*commonName\s*,\s*commonNameBuf_\s*,"
    r"\s*sizeof\s*\(\s*commonNameBuf_\s*\)\s*\)"
)


def test_whitespace_is_stripped_not_rejected():
    """Stakeholder decision, stakeholder_approval gate 2026-09-08:
    whitespace in role/commonName is removed (leading, trailing, and
    internal) and the call still SUCCEEDS -- never a rejection path.
    Confirms both halves: (a) stripWhitespaceInto() is actually called
    on both role and commonName, feeding their respective buffers, and
    (b) no 'DBG:role rejected: whitespace' string exists ANYWHERE in
    protocol.cpp -- its presence means the reject behavior was
    (re)implemented instead of strip. The only rejection message that
    may exist is 'DBG:role rejected: null argument'."""
    body = _set_device_role_body()

    assert _STRIP_ROLE_RE.search(body), (
        "Protocol::setDeviceRole(): no "
        "'stripWhitespaceInto(role, roleBuf_, sizeof(roleBuf_))' call "
        f"found -- role must be stripped into its own buffer:\n{body}"
    )
    assert _STRIP_COMMON_NAME_RE.search(body), (
        "Protocol::setDeviceRole(): no "
        "'stripWhitespaceInto(commonName, commonNameBuf_, "
        "sizeof(commonNameBuf_))' call found -- commonName must be "
        f"stripped into its own buffer:\n{body}"
    )

    assert _REJECTED_WHITESPACE_MSG not in _PROTOCOL_CPP_RAW, (
        f"src/comms/protocol.cpp contains {_REJECTED_WHITESPACE_MSG!r} -- "
        "this is the REJECTED behavior (stakeholder chose strip-and-"
        "accept, not reject, for whitespace in role/commonName). Its "
        "presence anywhere in the file means reject was reintroduced."
    )
    assert _ACCEPTED_NULL_MSG in _PROTOCOL_CPP_RAW, (
        f"src/comms/protocol.cpp is missing {_ACCEPTED_NULL_MSG!r} -- "
        "the null-argument rejection message must still exist as the "
        "ONLY rejection path."
    )


# ---------------------------------------------------------------------
# 3. Truncation computed from the STRIPPED length, never raw strlen.
# ---------------------------------------------------------------------

_ROLE_LEN_FROM_STRIP_RE = re.compile(
    r"\broleLen\s*=\s*stripWhitespaceInto\s*\(\s*role\s*,"
)
_COMMON_NAME_LEN_FROM_STRIP_RE = re.compile(
    r"\bcommonNameLen\s*=\s*stripWhitespaceInto\s*\(\s*commonName\s*,"
)
_ROLE_TRUNC_CHECK_RE = re.compile(
    r"\broleLen\s*>=\s*sizeof\s*\(\s*roleBuf_\s*\)"
)
_COMMON_NAME_TRUNC_CHECK_RE = re.compile(
    r"\bcommonNameLen\s*>=\s*sizeof\s*\(\s*commonNameBuf_\s*\)"
)
_RAW_STRLEN_ROLE_RE = re.compile(r"strlen\s*\(\s*role\s*\)")
_RAW_STRLEN_COMMON_NAME_RE = re.compile(r"strlen\s*\(\s*commonName\s*\)")


def test_truncation_uses_stripped_length_not_raw_strlen():
    """The single easiest thing in this sprint to implement backwards
    (team-lead's own framing): deviceRoleTruncated_ must be computed
    from roleLen/commonNameLen -- the variables stripWhitespaceInto()
    itself RETURNED -- never from strlen(role)/strlen(commonName)
    compared directly against sizeof(...). This pins BOTH that the
    length variables are fed by stripWhitespaceInto()'s return value
    (not some other source with the same name) AND that no direct raw
    strlen() comparison exists anywhere in the body -- a regression
    that introduced a second, raw-length check alongside a
    correctly-named roleLen variable would defeat a pin that only
    looked for the variable name."""
    body = _set_device_role_body()

    assert _ROLE_LEN_FROM_STRIP_RE.search(body), (
        "Protocol::setDeviceRole(): 'roleLen' must be assigned directly "
        f"from stripWhitespaceInto(role, ...)'s return value:\n{body}"
    )
    assert _COMMON_NAME_LEN_FROM_STRIP_RE.search(body), (
        "Protocol::setDeviceRole(): 'commonNameLen' must be assigned "
        f"directly from stripWhitespaceInto(commonName, ...)'s return "
        f"value:\n{body}"
    )
    assert _ROLE_TRUNC_CHECK_RE.search(body), (
        "Protocol::setDeviceRole(): no 'roleLen >= sizeof(roleBuf_)' "
        f"truncation check found:\n{body}"
    )
    assert _COMMON_NAME_TRUNC_CHECK_RE.search(body), (
        "Protocol::setDeviceRole(): no 'commonNameLen >= "
        f"sizeof(commonNameBuf_)' truncation check found:\n{body}"
    )

    assert not _RAW_STRLEN_ROLE_RE.search(body), (
        "Protocol::setDeviceRole(): found strlen(role) -- truncation "
        "must be judged from the STRIPPED length (roleLen), never the "
        f"raw argument's strlen():\n{body}"
    )
    assert not _RAW_STRLEN_COMMON_NAME_RE.search(body), (
        "Protocol::setDeviceRole(): found strlen(commonName) -- "
        "truncation must be judged from the STRIPPED length "
        f"(commonNameLen), never the raw argument's strlen():\n{body}"
    )

    # Ordering cross-check: the strip calls must appear textually
    # before the truncation assignment they feed.
    role_strip = _ROLE_LEN_FROM_STRIP_RE.search(body)
    common_name_strip = _COMMON_NAME_LEN_FROM_STRIP_RE.search(body)
    trunc_assign = re.search(r"deviceRoleTruncated_\s*=\s*0\s*;", body)
    assert trunc_assign, (
        "Protocol::setDeviceRole(): no 'deviceRoleTruncated_ = 0;' reset "
        f"found before the per-field truncation checks:\n{body}"
    )
    assert role_strip.end() <= trunc_assign.start(), (
        "Protocol::setDeviceRole(): roleLen's stripWhitespaceInto() call "
        "must appear BEFORE deviceRoleTruncated_'s reset/assignment -- "
        f"strip-then-measure-then-clip ordering:\n{body}"
    )
    assert common_name_strip.end() <= trunc_assign.start(), (
        "Protocol::setDeviceRole(): commonNameLen's stripWhitespaceInto() "
        "call must appear BEFORE deviceRoleTruncated_'s reset/assignment "
        f"-- strip-then-measure-then-clip ordering:\n{body}"
    )


# ---------------------------------------------------------------------
# 3b. stripWhitespaceInto() itself: strippedLen counts every
#     non-whitespace byte of the FULL input, not bounded by dstSize --
#     this is what makes roleLen/commonNameLen the TRUE stripped
#     length rather than "however much fit in the buffer".
# ---------------------------------------------------------------------

def test_strip_whitespace_into_counts_full_length_unbounded_by_dst_size():
    """stripWhitespaceInto()'s own doc comment claims it 'separately
    counts the FULL stripped length past what fit' -- this pins that
    the `++strippedLen;` increment is NOT itself gated by the same
    `dstSize` capacity check that guards the `dst[written++] = ...`
    write. If a future edit folded strippedLen's increment inside that
    capacity check, roleLen/commonNameLen would silently become
    'however much fit', and the whitespace-only-overflow guarantee
    (test below) would no longer hold for inputs longer than the
    buffer."""
    body = _strip_whitespace_into_body()

    increment = re.search(r"\+\+\s*strippedLen\s*;", body)
    capacity_check = re.search(
        r"if\s*\(\s*dstSize\s*>\s*0\s*&&\s*written\s*\+\s*1\s*<\s*dstSize\s*\)",
        body,
    )
    assert increment, (
        f"stripWhitespaceInto(): no '++strippedLen;' found:\n{body}"
    )
    assert capacity_check, (
        "stripWhitespaceInto(): no 'if (dstSize > 0 && written + 1 < "
        f"dstSize)' capacity check found:\n{body}"
    )
    assert increment.end() <= capacity_check.start(), (
        "stripWhitespaceInto(): '++strippedLen;' must appear BEFORE the "
        "dstSize capacity check that gates the actual write -- otherwise "
        "the returned length is bounded by what fit, not the true "
        f"stripped length:\n{body}"
    )


# ---------------------------------------------------------------------
# 4. The explicit whitespace-only-overflow case from the acceptance
#    criteria: RAW length >= buffer size only because of whitespace
#    about to be stripped; STRIPPED length < buffer size. The pinned
#    algorithm (test 3b above) must NOT flag this truncated.
# ---------------------------------------------------------------------

_BUF_SIZE_RE_TEMPLATE = r"char\s+{name}\s*\[\s*(\d+)\s*\]\s*;"


def _buffer_size(member_name):
    m = re.search(_BUF_SIZE_RE_TEMPLATE.format(name=member_name), _PROTOCOL_H_STRIPPED)
    assert m, (
        f"{member_name} array declaration not found in "
        f"{_PROTOCOL_H.relative_to(_REPO_ROOT)} -- has it been renamed?"
    )
    return int(m.group(1))


def _strip_whitespace_reference(src):
    """Re-derives stripWhitespaceInto()'s pinned algorithm (test 3b
    above) in plain host Python: strippedLen counts every non-
    whitespace byte of the FULL input, unbounded by any destination
    capacity. UNVERIFIED against the compiled C++ -- tests/host/
    cannot compile protocol.cpp (see this file's module doc comment)
    -- this reproduces the shape the source-pin assertions above
    confirm is actually present, as a concrete worked example."""
    return len("".join(ch for ch in src if not ch.isspace()))


def test_whitespace_only_overflow_does_not_truncate():
    """The single explicit case the acceptance criteria calls out: an
    input whose RAW length is >= sizeof(roleBuf_) ONLY because of
    whitespace bytes that will be stripped, whose STRIPPED length is <
    sizeof(roleBuf_). Under the pinned strip-then-measure algorithm
    (test 3b), this must NOT be flagged truncated -- a regression to
    raw strlen() (test 3's own negative pin) would flag it. Same shape
    repeated for commonNameBuf_."""
    role_buf_size = _buffer_size("roleBuf_")
    common_name_buf_size = _buffer_size("commonNameBuf_")

    # Small payload, padded with whitespace far past the buffer size --
    # e.g. role_buf_size=24: "ab" (2 chars) + 40 spaces = raw length 42
    # (>= 24), stripped length 2 (< 24).
    role_value = "ab" + (" " * (role_buf_size + 20))
    assert len(role_value) >= role_buf_size, (
        "test setup error: the whitespace-only-overflow fixture's RAW "
        "length must be >= roleBuf_'s sizeof to exercise the overflow "
        "case at all"
    )
    stripped_len = _strip_whitespace_reference(role_value)
    assert stripped_len < role_buf_size, (
        "test setup error: the whitespace-only-overflow fixture's "
        "STRIPPED length must be < roleBuf_'s sizeof"
    )
    would_truncate = stripped_len >= role_buf_size
    assert would_truncate is False, (
        "a role value that only overflows roleBuf_'s raw length because "
        "of whitespace about to be stripped must NOT be judged "
        "truncated once the stripped length is what's measured"
    )

    common_name_value = "cn" + (" " * (common_name_buf_size + 20))
    assert len(common_name_value) >= common_name_buf_size
    stripped_len_cn = _strip_whitespace_reference(common_name_value)
    assert stripped_len_cn < common_name_buf_size
    assert (stripped_len_cn >= common_name_buf_size) is False, (
        "a commonName value that only overflows commonNameBuf_'s raw "
        "length because of whitespace about to be stripped must NOT be "
        "judged truncated once the stripped length is what's measured"
    )


# ---------------------------------------------------------------------
# 5. NO late-call guard -- setDeviceRole() must have exactly one
#    `return;` (the null guard's own), unlike setupWifi()'s wifiBegun_
#    refusal.
# ---------------------------------------------------------------------

def test_no_late_call_guard():
    """Unlike setupWifi() (guarded because WifiLink::Config borrows
    into the credential buffers and serviceJoin() re-reads them on
    every retry -- wifi_link.cpp), sendBanner() dereferences
    identity.role/commonName at EMIT time, not at some earlier "begin"
    time a late write could corrupt -- so a set-after-first-banner call
    has no live-read hazard and MUST succeed. This asserts the body
    contains exactly ONE `return;` statement (the null guard's own,
    pinned in test 1) -- a second one gated on some "already begun"
    flag copied from setupWifi()'s shape would silently refuse a
    legitimate late call."""
    body = _set_device_role_body()
    returns = re.findall(r"\breturn\s*;", body)
    assert len(returns) == 1, (
        "Protocol::setDeviceRole(): expected exactly ONE 'return;' "
        "statement (the null guard's own) -- found "
        f"{len(returns)}. A second early return suggests a late-call "
        "guard was copied from setupWifi()'s shape, which would "
        "silently refuse a legitimate call arriving after the first "
        f"banner already went out:\n{body}"
    )
    # And no reference anywhere in the body to a "begun"-style flag --
    # the specific state setupWifi() keys its own guard off of.
    assert not re.search(r"[Bb]egun_", body), (
        "Protocol::setDeviceRole(): found a reference to a "
        "'*Begun_'-style flag -- setDeviceRole() must have no late-call "
        f"guard at all, unlike setupWifi()'s wifiBegun_:\n{body}"
    )


# ---------------------------------------------------------------------
# 6. Constructor seeds roleBuf_/commonNameBuf_ from the NAMED
#    constants kRole/kCommonName, not inline literals.
# ---------------------------------------------------------------------

_CTOR_SEED_ROLE_RE = re.compile(
    r'snprintf\s*\(\s*roleBuf_\s*,\s*sizeof\s*\(\s*roleBuf_\s*\)\s*,'
    r'\s*"%s"\s*,\s*kRole\s*\)'
)
_CTOR_SEED_COMMON_NAME_RE = re.compile(
    r'snprintf\s*\(\s*commonNameBuf_\s*,\s*sizeof\s*\(\s*commonNameBuf_\s*\)\s*,'
    r'\s*"%s"\s*,\s*kCommonName\s*\)'
)
# The rejected shape: a hardcoded literal instead of the named constant.
_CTOR_SEED_ROLE_LITERAL_RE = re.compile(
    r'snprintf\s*\(\s*roleBuf_\s*,[^;]*"NEZHA2"'
)
_CTOR_SEED_COMMON_NAME_LITERAL_RE = re.compile(
    r'snprintf\s*\(\s*commonNameBuf_\s*,[^;]*"robot"'
)


def test_constructor_seeds_from_named_constants():
    """Protocol::Protocol() must seed roleBuf_/commonNameBuf_ from
    kRole/kCommonName BY NAME, not inline literals -- a hardcoded
    "NEZHA2"/"robot" here would silently diverge from kRole/kCommonName
    the moment anyone edits one but not the other (the exact failure
    mode the ticket calls out)."""
    body = _constructor_body()

    assert _CTOR_SEED_ROLE_RE.search(body), (
        'Protocol::Protocol(): no \'snprintf(roleBuf_, sizeof(roleBuf_), '
        f'"%s", kRole)\' seed line found:\n{body}'
    )
    assert _CTOR_SEED_COMMON_NAME_RE.search(body), (
        'Protocol::Protocol(): no \'snprintf(commonNameBuf_, '
        f'sizeof(commonNameBuf_), "%s", kCommonName)\' seed line found:'
        f'\n{body}'
    )
    assert not _CTOR_SEED_ROLE_LITERAL_RE.search(body), (
        "Protocol::Protocol(): roleBuf_ appears seeded from a hardcoded "
        f'"NEZHA2" literal instead of the named kRole constant:\n{body}'
    )
    assert not _CTOR_SEED_COMMON_NAME_LITERAL_RE.search(body), (
        "Protocol::Protocol(): commonNameBuf_ appears seeded from a "
        'hardcoded "robot" literal instead of the named kCommonName '
        f"constant:\n{body}"
    )


# ---------------------------------------------------------------------
# 7. buildIdentity() points identity.role/commonName at the OWNED
#    buffers, never the constants.
# ---------------------------------------------------------------------

def test_build_identity_points_at_owned_buffers_not_constants():
    """buildIdentity() must assign identity.role = roleBuf_ and
    identity.commonName = commonNameBuf_ -- NOT identity.role = kRole.
    This is the specific regression this test exists to catch: a
    "simplification" back to the constants would leave every
    DEFAULT-value test passing (same string either way) while silently
    breaking every runtime setDeviceRole() call."""
    body = _build_identity_body()

    assert re.search(r"identity\.role\s*=\s*roleBuf_\s*;", body), (
        "Protocol::buildIdentity(): no 'identity.role = roleBuf_;' "
        f"assignment found:\n{body}"
    )
    assert re.search(r"identity\.commonName\s*=\s*commonNameBuf_\s*;", body), (
        "Protocol::buildIdentity(): no 'identity.commonName = "
        f"commonNameBuf_;' assignment found:\n{body}"
    )
    assert not re.search(r"identity\.role\s*=\s*kRole\s*;", body), (
        "Protocol::buildIdentity(): found 'identity.role = kRole;' -- "
        "this reverts every runtime setDeviceRole() call to a no-op "
        f"while leaving the default-value tests passing:\n{body}"
    )
    assert not re.search(r"identity\.commonName\s*=\s*kCommonName\s*;", body), (
        "Protocol::buildIdentity(): found 'identity.commonName = "
        "kCommonName;' -- this reverts every runtime setDeviceRole() "
        f"call to a no-op while leaving the default-value tests passing:"
        f"\n{body}"
    )


# ---------------------------------------------------------------------
# 8. The "NSDMI, not a hand-written constructor" comment must stay
#    amended to name the roleBuf_/commonNameBuf_ exception.
# ---------------------------------------------------------------------

def test_nsdmi_comment_mentions_the_rolebuf_exception():
    """protocol.h used to describe every member as NSDMI'd with no
    exception -- now that Protocol::Protocol() is a hand-written
    constructor seeding roleBuf_/commonNameBuf_ (and profileBuf_), the
    comment near wireAdapter_'s declaration must say so, not stand
    beside a constructor it contradicts. Greps for the OLD blanket
    phrase's specific absence-of-exception shape by requiring the
    amended phrase (naming roleBuf_) to be present."""
    assert re.search(
        r"NSDMI for every member below except\s+roleBuf_", _PROTOCOL_H_RAW
    ), (
        "src/comms/protocol.h: the 'NSDMI for every member below' "
        "comment must name the roleBuf_/commonNameBuf_ exception -- a "
        "stale blanket claim here would contradict the hand-written "
        "constructor that now seeds those buffers."
    )


# ---------------------------------------------------------------------
# 9. sendBanner()'s format string and the kRole/kCommonName default
#    values -- the closest a source-pin test can get to "the default
#    banner is byte-identical" without compiling protocol.cpp.
# ---------------------------------------------------------------------

_K_ROLE_RE = re.compile(r'constexpr const char\* kRole = "([^"]*)";')
_K_COMMON_NAME_RE = re.compile(r'constexpr const char\* kCommonName = "([^"]*)";')
_SEND_BANNER_FORMAT_RE = re.compile(
    r'snprintf\s*\(\s*buf\s*,\s*sizeof\s*\(\s*buf\s*\)\s*,'
    r'\s*"device %s %s %s %s\\n"\s*,\s*identity\.role\s*,'
    r'\s*identity\.commonName\s*,\s*identity\.name\s*,'
    r'\s*identity\.serial\s*\)',
    re.DOTALL,
)


def test_send_banner_format_string_and_krolecommonname_defaults():
    """kRole = "NEZHA2" and kCommonName = "robot" are unchanged literal
    values, and sendBanner()'s format string is exactly
    'device %s %s %s %s\\n' reading, in order, identity.role,
    identity.commonName, identity.name, identity.serial -- a literal
    ("NEZHA2"/"robot") reappearing directly in the format call instead
    of the identity fields would silently ignore every runtime
    setDeviceRole() call at emit time even if setDeviceRole() itself
    were correct."""
    role_match = _K_ROLE_RE.search(_PROTOCOL_CPP_STRIPPED)
    common_name_match = _K_COMMON_NAME_RE.search(_PROTOCOL_CPP_STRIPPED)
    assert role_match, (
        "src/comms/protocol.cpp: no "
        '\'constexpr const char* kRole = "...";\' declaration found.'
    )
    assert common_name_match, (
        "src/comms/protocol.cpp: no "
        '\'constexpr const char* kCommonName = "...";\' declaration '
        "found."
    )
    assert role_match.group(1) == "NEZHA2", (
        f"kRole is {role_match.group(1)!r}, expected 'NEZHA2' -- the "
        "HELLO banner's default role value."
    )
    assert common_name_match.group(1) == "robot", (
        f"kCommonName is {common_name_match.group(1)!r}, expected "
        "'robot' -- the HELLO banner's default common-name value."
    )

    banner_body = _send_banner_body()
    assert _SEND_BANNER_FORMAT_RE.search(banner_body), (
        "WireHandler::sendBanner(): format string must be exactly "
        "'device %s %s %s %s\\n' reading identity.role, "
        "identity.commonName, identity.name, identity.serial, in that "
        f"order:\n{banner_body}"
    )
    assert '"NEZHA2"' not in banner_body and "'NEZHA2'" not in banner_body, (
        "WireHandler::sendBanner(): a literal \"NEZHA2\" appears in the "
        "body -- the banner must read identity.role (which points at "
        f"the owned roleBuf_), never a hardcoded literal:\n{banner_body}"
    )
    assert '"robot"' not in banner_body and "'robot'" not in banner_body, (
        "WireHandler::sendBanner(): a literal \"robot\" appears in the "
        "body -- the banner must read identity.commonName (which points "
        "at the owned commonNameBuf_), never a hardcoded literal:"
        f"\n{banner_body}"
    )
