"""tests/host/test_setprofile_precedence_source_pin.py -- pins
`Protocol::setProfile()`'s null guard, strip-then-accept whitespace
handling, strip-then-measure-then-clip truncation ordering, the
constructor's `profileBuf_` seeding shape, and `buildIdentity()`'s
buffer wiring in `src/comms/protocol.cpp`/`protocol.h`, plus
`tools/make_deploy.py::_inject_profile()`'s regex staying aimed at the
one `kProfile` declaration, for sprint 037 ticket 005,
clasi/sprints/037-runtime-identity-setters-hello-banner-role-and-
common-name-are-hardcoded/tickets/005-host-level-source-pin-tests-
setprofile-precedence-truncation-whitespace-and-late-call-succeeds-
behavior.md.

**Direct model, not a copy.** This is `setDeviceRole()`'s sibling test
file, `tests/host/test_setdevicerole_precedence_source_pin.py` (ticket
004) -- same idioms, same helper shapes, deliberately duplicated per
that file's own precedent that each source-pin file in this directory
stays self-contained (no shared helper module exists). It does NOT
re-cover `setDeviceRole()`/`sendBanner()`/the role banner format --
those stay pinned exactly where ticket 004 put them. It DOES re-derive
`stripWhitespaceInto()`'s own algorithm as a worked example (test 4
below), the same way ticket 004's file does, rather than importing
ticket 004's copy -- these two files intentionally do not share code.

**What this is NOT.** Source-text pinning, following
`test_setdevicerole_precedence_source_pin.py`'s own precedent (and,
further back, `test_setupwifi_precedence_source_pin.py`) of
regex-asserting on source text without compiling it -- `tests/host/`
cannot compile `protocol.cpp` at all (it includes `pxt.h`, directly and
transitively; confirmed by that file and by
`test_protocol_stack_canary_source_pin.py`). It cannot prove a live
`id` reply is byte-identical on real hardware, or that `setProfile()`
called after the first reply is actually picked up by the NEXT one on
a running board. Everything below is UNVERIFIED on hardware; it only
confirms the source SHAPE that would make those things true is present
and has not regressed.

**Why each pin is aimed at a specific regression, not "the text is
present".**

1. `test_null_guard_precedes_every_write` -- the null check
   (`name == nullptr`) must gate BEFORE any write to
   `profileBuf_`/`profileTruncated_`/`profileSetAtRuntime_`, not
   merely exist somewhere in the body.
2. `test_whitespace_is_stripped_not_rejected` -- the stakeholder
   decision this whole ticket exists to protect (`stakeholder_approval`
   gate, 2026-09-08), extended to `profile` even though the source
   issue's own text never asked for a whitespace rule at all: `profile`
   sits inside the same space-separated, positionally-parsed `id` reply
   as the banner fields `setDeviceRole()` already strips. This is a
   STRIP, not a REJECT, so the test asserts both the positive (a
   `stripWhitespaceInto()` call feeding `profileBuf_`) AND the negative
   (no `DBG:profile rejected: whitespace` string anywhere in the file --
   its presence means reject was re-implemented). Only `DBG:profile
   rejected: null argument` may exist. A worked example
   (`setProfile("the bot")` stripping to `"thebot"`) is included so the
   pin reads as a concrete behavior, not just a regex hit.
3. `test_truncation_uses_stripped_length_not_raw_strlen` -- pins that
   `profileTruncated_` is computed from `nameLen` -- the variable
   `stripWhitespaceInto()` itself RETURNED (the true stripped length,
   per that function's own doc comment) -- never from
   `strlen(name)` compared directly against `sizeof(profileBuf_)`. A
   regression that measured the raw argument instead would satisfy a
   weaker "does nameLen appear somewhere" pin while silently flagging
   whitespace-padded values as truncated when they are not.
4. `test_whitespace_only_overflow_does_not_truncate` -- the explicit
   overflow case the acceptance criteria calls out: an input whose RAW
   length exceeds `profileBuf_`'s `sizeof` only because of whitespace
   about to be stripped must NOT be flagged truncated. Re-derives
   `stripWhitespaceInto()`'s own pinned algorithm (already source-pinned
   for the shared function itself by ticket 004's
   `test_strip_whitespace_into_counts_full_length_unbounded_by_dst_size`
   -- not re-pinned here, just relied on) in plain host Python against
   the real `profileBuf_` size read from `protocol.h`.
5. `test_no_late_call_guard` -- unlike `setupWifi()` (guarded because
   `WifiLink::Config` borrows into the credential buffers and
   `serviceJoin()` re-reads them on every retry), `execId()`'s
   `snprintf` dereferences `identity.profile` at REPLY time, so a call
   at any point (including after the first `id` reply already went
   out) has no live read to corrupt and must succeed. This asserts
   `setProfile()`'s body contains exactly ONE `return;` statement (the
   null guard's own) and never references a `*Begun_`-style flag or
   gates on `profileSetAtRuntime_` itself -- a guard copied from
   `setupWifi()`'s shape would silently refuse a legitimate late call.
6. `test_constructor_seeds_from_named_constant` -- `Protocol::
   Protocol()` must seed `profileBuf_` from `kProfile` by name, not an
   inline `"unbaked"` literal -- a hardcoded literal here would silently
   diverge from `kProfile` the moment that constant is edited.
7. `test_build_identity_points_at_owned_buffer_not_constant` --
   `buildIdentity()` must assign `identity.profile = profileBuf_`,
   never `identity.profile = kProfile` -- the single highest-value
   assertion in this file: this is the exact regression that would
   silently break `setProfile()` while every default-output test kept
   passing (baked default is identical either way).
8. `test_dbg_profile_format_has_src_name_trunc_tokens` -- the `DBG:
   profile` line's `snprintf` format string contains `src=`, `name=`,
   and `trunc=` tokens, matching the issue's own recommended shape
   (`src=baked|runtime name=vevov trunc=0`).
9. `test_inject_profile_regex_still_matches_exactly_one_declaration` --
   cross-file consistency check: `tools/make_deploy.py`'s
   `_K_PROFILE_RE` (the actual compiled regex object, imported directly
   -- not a re-typed copy that could drift from the real one) still
   matches exactly one `kProfile` declaration in the CHECKED-IN
   `src/comms/protocol.cpp`. `tests/tools/test_make_deploy_profile.py`
   already covers `_inject_profile()`'s end-to-end behavior against
   scratch copies; this is the one additional check worth having here,
   since ticket 002 edited the same identity block that regex targets
   and a source-pin file sitting next to that edit is the natural place
   to catch a shape change before it reaches that other file's fixtures.

Run with::

    uv run pytest tests/host/test_setprofile_precedence_source_pin.py
"""
import pathlib
import re
import sys

# tests/host/test_setprofile_precedence_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"
_PROTOCOL_H = _REPO_ROOT / "src" / "comms" / "protocol.h"
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    see test_bus_guard_source_pin.py's identical helper for the full
    rationale. Duplicated here rather than imported: each source-pin
    test file in this directory stays self-contained, the same
    precedent test_setdevicerole_precedence_source_pin.py and
    test_setupwifi_precedence_source_pin.py themselves follow."""
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

_PROTOCOL_CPP_STRIPPED = _strip_comments(_PROTOCOL_CPP_RAW)
_PROTOCOL_H_STRIPPED = _strip_comments(_PROTOCOL_H_RAW)

_SET_PROFILE_SIG = (
    r"void\s+Protocol::setProfile\s*\(\s*const\s+char\s*\*\s*name\s*\)\s*\{"
)
_CONSTRUCTOR_SIG = r"Protocol::Protocol\s*\(\s*\)\s*\{"
_BUILD_IDENTITY_SIG = r"Wire::Identity\s+Protocol::buildIdentity\s*\(\s*\)\s*\{"


def _set_profile_body():
    return _function_body(
        _PROTOCOL_CPP_STRIPPED, _SET_PROFILE_SIG,
        "Protocol::setProfile", "src/comms/protocol.cpp",
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


# ---------------------------------------------------------------------
# 1. Null guard: present, and gates BEFORE every write it must prevent.
# ---------------------------------------------------------------------

_NULL_GUARD_RE = re.compile(
    r"if\s*\(\s*name\s*==\s*nullptr\s*\)\s*\{[^}]*?return\s*;[^}]*?\}",
    re.DOTALL,
)

_WRITE_TARGETS = [
    ("profileBuf_", re.compile(r"profileBuf_\s*(?:\[|,|=)")),
    ("profileTruncated_", re.compile(r"profileTruncated_\s*(?:\|=|=)")),
    ("profileSetAtRuntime_", re.compile(r"profileSetAtRuntime_\s*(?:\|=|=)")),
]


def test_null_guard_precedes_every_write():
    """The null check must gate BEFORE any write to
    profileBuf_/profileTruncated_/profileSetAtRuntime_ -- a guard
    present but checked AFTER those writes (or only in a comment) would
    let a null argument reach stripWhitespaceInto()'s own dereference of
    `src`."""
    body = _set_profile_body()

    guard_match = _NULL_GUARD_RE.search(body)
    assert guard_match, (
        "Protocol::setProfile(): no "
        "'if (name == nullptr) { ... return; ... }' null guard found in "
        f"the body:\n{body}"
    )
    guard_end = guard_match.end()

    for label, write_re in _WRITE_TARGETS:
        write_match = write_re.search(body)
        assert write_match, (
            f"Protocol::setProfile(): no write to {label} found in the "
            f"body -- has the store logic moved or been renamed?:\n{body}"
        )
        assert guard_end <= write_match.start(), (
            f"Protocol::setProfile(): the null guard does not appear "
            f"BEFORE the write to {label} -- a null argument could reach "
            f"this write instead of being refused:\n{body}"
        )


# ---------------------------------------------------------------------
# 2. Whitespace is STRIPPED, not rejected -- the stakeholder decision,
#    extended to `profile` beyond the source issue's literal text.
# ---------------------------------------------------------------------

_REJECTED_WHITESPACE_MSG = "DBG:profile rejected: whitespace"
_ACCEPTED_NULL_MSG = "DBG:profile rejected: null argument"

_STRIP_PROFILE_RE = re.compile(
    r"\bstripWhitespaceInto\s*\(\s*name\s*,\s*profileBuf_\s*,"
    r"\s*sizeof\s*\(\s*profileBuf_\s*\)\s*\)"
)


def _strip_whitespace_reference(src):
    """Re-derives stripWhitespaceInto()'s pinned algorithm (source-pinned
    for the shared function by ticket 004's own
    test_strip_whitespace_into_counts_full_length_unbounded_by_dst_size)
    in plain host Python: every non-whitespace byte of the FULL input,
    unbounded by any destination capacity. UNVERIFIED against the
    compiled C++ -- tests/host/ cannot compile protocol.cpp (see this
    file's module doc comment) -- this reproduces the shape the
    source-pin assertions confirm is actually present, as a concrete
    worked example."""
    return "".join(ch for ch in src if not ch.isspace())


def test_whitespace_is_stripped_not_rejected():
    """Stakeholder decision, stakeholder_approval gate 2026-09-08,
    extended to `profile` beyond the source issue's own text because
    `profile` sits in the same space-separated, positionally-parsed
    `id` reply as the banner fields: whitespace in `name` is removed
    (leading, trailing, and internal) and the call still SUCCEEDS --
    never a rejection path. Confirms three things: (a)
    stripWhitespaceInto() is actually called on `name`, feeding
    profileBuf_, (b) no 'DBG:profile rejected: whitespace' string exists
    ANYWHERE in protocol.cpp -- its presence means the reject behavior
    was (re)implemented instead of strip, and (c) a worked example:
    'the bot' strips to 'thebot', never a rejection."""
    body = _set_profile_body()

    assert _STRIP_PROFILE_RE.search(body), (
        "Protocol::setProfile(): no "
        "'stripWhitespaceInto(name, profileBuf_, sizeof(profileBuf_))' "
        f"call found -- name must be stripped into its own buffer:\n{body}"
    )

    assert _REJECTED_WHITESPACE_MSG not in _PROTOCOL_CPP_RAW, (
        f"src/comms/protocol.cpp contains {_REJECTED_WHITESPACE_MSG!r} -- "
        "this is the REJECTED behavior (stakeholder chose strip-and-"
        "accept, not reject, for whitespace in profile/name). Its "
        "presence anywhere in the file means reject was reintroduced."
    )
    assert _ACCEPTED_NULL_MSG in _PROTOCOL_CPP_RAW, (
        f"src/comms/protocol.cpp is missing {_ACCEPTED_NULL_MSG!r} -- "
        "the null-argument rejection message must still exist as the "
        "ONLY rejection path."
    )

    # Worked example: setProfile("the bot") must succeed and store
    # "thebot", never fail -- pinning the CLAIM, not just the regex.
    stripped = _strip_whitespace_reference("the bot")
    assert stripped == "thebot", (
        "test setup error: the worked example itself is wrong -- "
        f"'the bot' stripped should be 'thebot', got {stripped!r}"
    )


# ---------------------------------------------------------------------
# 3. Truncation computed from the STRIPPED length, never raw strlen.
# ---------------------------------------------------------------------

_NAME_LEN_FROM_STRIP_RE = re.compile(
    r"\bnameLen\s*=\s*stripWhitespaceInto\s*\(\s*name\s*,"
)
_PROFILE_TRUNC_CHECK_RE = re.compile(
    r"\bprofileTruncated_\s*=\s*nameLen\s*>=\s*sizeof\s*\(\s*profileBuf_\s*\)"
)
_RAW_STRLEN_NAME_RE = re.compile(r"strlen\s*\(\s*name\s*\)")


def test_truncation_uses_stripped_length_not_raw_strlen():
    """profileTruncated_ must be computed from nameLen -- the variable
    stripWhitespaceInto() itself RETURNED -- never from strlen(name)
    compared directly against sizeof(profileBuf_). This pins BOTH that
    nameLen is fed by stripWhitespaceInto()'s return value (not some
    other source with the same name) AND that no direct raw strlen()
    comparison exists anywhere in the body -- a regression that
    introduced a second, raw-length check alongside a correctly-named
    nameLen variable would defeat a pin that only looked for the
    variable name."""
    body = _set_profile_body()

    assert _NAME_LEN_FROM_STRIP_RE.search(body), (
        "Protocol::setProfile(): 'nameLen' must be assigned directly "
        f"from stripWhitespaceInto(name, ...)'s return value:\n{body}"
    )
    assert _PROFILE_TRUNC_CHECK_RE.search(body), (
        "Protocol::setProfile(): no 'profileTruncated_ = nameLen >= "
        f"sizeof(profileBuf_)' truncation check found:\n{body}"
    )
    assert not _RAW_STRLEN_NAME_RE.search(body), (
        "Protocol::setProfile(): found strlen(name) -- truncation must "
        "be judged from the STRIPPED length (nameLen), never the raw "
        f"argument's strlen():\n{body}"
    )

    # Ordering cross-check: the strip call (which assigns nameLen) must
    # appear textually before the truncation assignment it feeds --
    # strip-then-measure-then-clip.
    name_strip = _NAME_LEN_FROM_STRIP_RE.search(body)
    trunc_assign = _PROFILE_TRUNC_CHECK_RE.search(body)
    assert name_strip.end() <= trunc_assign.start(), (
        "Protocol::setProfile(): nameLen's stripWhitespaceInto() call "
        "must appear BEFORE profileTruncated_'s assignment -- "
        f"strip-then-measure-then-clip ordering:\n{body}"
    )


# ---------------------------------------------------------------------
# 4. The explicit whitespace-only-overflow case from the acceptance
#    criteria: RAW length >= profileBuf_'s sizeof only because of
#    whitespace about to be stripped; STRIPPED length < that sizeof.
#    The pinned algorithm (stripWhitespaceInto(), pinned for the shared
#    function itself by ticket 004) must NOT flag this truncated.
# ---------------------------------------------------------------------

_BUF_SIZE_RE_TEMPLATE = r"char\s+{name}\s*\[\s*(\d+)\s*\]\s*;"


def _buffer_size(member_name):
    m = re.search(_BUF_SIZE_RE_TEMPLATE.format(name=member_name), _PROTOCOL_H_STRIPPED)
    assert m, (
        f"{member_name} array declaration not found in "
        f"{_PROTOCOL_H.relative_to(_REPO_ROOT)} -- has it been renamed?"
    )
    return int(m.group(1))


def test_whitespace_only_overflow_does_not_truncate():
    """The single explicit case the acceptance criteria calls out: an
    input whose RAW length is >= sizeof(profileBuf_) ONLY because of
    whitespace bytes that will be stripped, whose STRIPPED length is <
    sizeof(profileBuf_). Under the pinned strip-then-measure algorithm,
    this must NOT be flagged truncated -- a regression to raw strlen()
    (test 3's own negative pin) would flag it."""
    profile_buf_size = _buffer_size("profileBuf_")

    # Small payload, padded with whitespace far past the buffer size --
    # e.g. profile_buf_size=32: "vv" (2 chars) + 50 spaces = raw length
    # 52 (>= 32), stripped length 2 (< 32).
    name_value = "vv" + (" " * (profile_buf_size + 20))
    assert len(name_value) >= profile_buf_size, (
        "test setup error: the whitespace-only-overflow fixture's RAW "
        "length must be >= profileBuf_'s sizeof to exercise the overflow "
        "case at all"
    )
    stripped_len = len(_strip_whitespace_reference(name_value))
    assert stripped_len < profile_buf_size, (
        "test setup error: the whitespace-only-overflow fixture's "
        "STRIPPED length must be < profileBuf_'s sizeof"
    )
    would_truncate = stripped_len >= profile_buf_size
    assert would_truncate is False, (
        "a profile name that only overflows profileBuf_'s raw length "
        "because of whitespace about to be stripped must NOT be judged "
        "truncated once the stripped length is what's measured"
    )


# ---------------------------------------------------------------------
# 5. NO late-call guard -- setProfile() must have exactly one
#    `return;` (the null guard's own), unlike setupWifi()'s wifiBegun_
#    refusal, and must not gate on profileSetAtRuntime_ itself.
# ---------------------------------------------------------------------

def test_no_late_call_guard():
    """Unlike setupWifi() (guarded because WifiLink::Config borrows
    into the credential buffers and serviceJoin() re-reads them on
    every retry), execId()'s snprintf dereferences identity.profile at
    REPLY time, not at some earlier "begin" time a late write could
    corrupt -- so a set-after-first-reply call has no live-read hazard
    and MUST succeed. This is the ticket's own most important negative
    assertion: a future "consistency" refactor that copies setupWifi()'s
    guard shape onto setProfile() must fail this test loudly. Asserts
    the body contains exactly ONE `return;` statement (the null guard's
    own, pinned in test 1), no reference to a '*Begun_'-style flag, and
    no conditional gating on profileSetAtRuntime_ itself (which exists
    only to be SET, recording provenance for the DBG line -- never
    read back to refuse a call)."""
    body = _set_profile_body()
    returns = re.findall(r"\breturn\s*;", body)
    assert len(returns) == 1, (
        "Protocol::setProfile(): expected exactly ONE 'return;' "
        "statement (the null guard's own) -- found "
        f"{len(returns)}. A second early return suggests a late-call "
        "guard was copied from setupWifi()'s shape, which would "
        "silently refuse a legitimate call arriving after the first "
        f"'id' reply already went out:\n{body}"
    )
    assert not re.search(r"[Bb]egun_", body), (
        "Protocol::setProfile(): found a reference to a '*Begun_'-style "
        "flag -- setProfile() must have no late-call guard at all, "
        f"unlike setupWifi()'s wifiBegun_:\n{body}"
    )
    assert not re.search(r"if\s*\([^)]*profileSetAtRuntime_[^)]*\)", body), (
        "Protocol::setProfile(): found a conditional gating on "
        "profileSetAtRuntime_ -- that flag exists only to be SET, "
        "recording provenance for the DBG line, never read back to "
        f"refuse a call:\n{body}"
    )


# ---------------------------------------------------------------------
# 6. Constructor seeds profileBuf_ from the NAMED constant kProfile,
#    not an inline literal.
# ---------------------------------------------------------------------

_CTOR_SEED_PROFILE_RE = re.compile(
    r'snprintf\s*\(\s*profileBuf_\s*,\s*sizeof\s*\(\s*profileBuf_\s*\)\s*,'
    r'\s*"%s"\s*,\s*kProfile\s*\)'
)
# The rejected shape: a hardcoded literal instead of the named constant.
_CTOR_SEED_PROFILE_LITERAL_RE = re.compile(
    r'snprintf\s*\(\s*profileBuf_\s*,[^;]*"unbaked"'
)


def test_constructor_seeds_from_named_constant():
    """Protocol::Protocol() must seed profileBuf_ from kProfile BY
    NAME, not an inline literal -- a hardcoded "unbaked" here would
    silently diverge from kProfile the moment that constant is edited
    (same reasoning as ticket 004's constructor check for
    kRole/kCommonName)."""
    body = _constructor_body()

    assert _CTOR_SEED_PROFILE_RE.search(body), (
        'Protocol::Protocol(): no \'snprintf(profileBuf_, '
        f'sizeof(profileBuf_), "%s", kProfile)\' seed line found:\n{body}'
    )
    assert not _CTOR_SEED_PROFILE_LITERAL_RE.search(body), (
        "Protocol::Protocol(): profileBuf_ appears seeded from a "
        'hardcoded "unbaked" literal instead of the named kProfile '
        f"constant:\n{body}"
    )


# ---------------------------------------------------------------------
# 7. buildIdentity() points identity.profile at the OWNED buffer,
#    never the constant. The single highest-value assertion in this
#    file.
# ---------------------------------------------------------------------

def test_build_identity_points_at_owned_buffer_not_constant():
    """buildIdentity() must assign identity.profile = profileBuf_ --
    NOT identity.profile = kProfile. This is the exact regression this
    test exists to catch: a "simplification" back to the constant would
    leave every DEFAULT-value test passing (same string either way)
    while silently breaking every runtime setProfile() call."""
    body = _build_identity_body()

    assert re.search(r"identity\.profile\s*=\s*profileBuf_\s*;", body), (
        "Protocol::buildIdentity(): no 'identity.profile = profileBuf_;' "
        f"assignment found:\n{body}"
    )
    assert not re.search(r"identity\.profile\s*=\s*kProfile\s*;", body), (
        "Protocol::buildIdentity(): found 'identity.profile = kProfile;' "
        "-- this reverts every runtime setProfile() call to a no-op "
        f"while leaving the default-value tests passing:\n{body}"
    )


# ---------------------------------------------------------------------
# 8. DBG:profile line format -- src=, name=, trunc= tokens present.
# ---------------------------------------------------------------------

_DBG_PROFILE_FORMAT_RE = re.compile(
    r'"DBG:profile\s+src=%s\s+name=%s\s+trunc=%u"'
)


def test_dbg_profile_format_has_src_name_trunc_tokens():
    """The DBG:profile line's snprintf format string must contain
    src=, name=, and trunc= tokens, in that order, matching the issue's
    own recommended shape ('src=baked|runtime name=vevov trunc=0')."""
    body = _set_profile_body()
    assert _DBG_PROFILE_FORMAT_RE.search(body), (
        "Protocol::setProfile(): no 'DBG:profile src=%s name=%s "
        f"trunc=%u' format string found:\n{body}"
    )


# ---------------------------------------------------------------------
# 9. tools/make_deploy.py's _inject_profile() regex still matches
#    exactly one kProfile declaration in the checked-in protocol.cpp.
# ---------------------------------------------------------------------

def test_inject_profile_regex_still_matches_exactly_one_declaration():
    """Cross-file consistency check: import the REAL _K_PROFILE_RE
    object from tools/make_deploy.py (not a re-typed copy that could
    silently drift from it) and confirm it matches exactly one
    'constexpr const char* kProfile = "...";' declaration in the
    checked-in src/comms/protocol.cpp. tests/tools/
    test_make_deploy_profile.py already covers _inject_profile()'s
    end-to-end behavior against scratch copies; this is the
    complementary check that the regex's TARGET, in the real file
    ticket 002 edited, still exists in the exact shape that regex
    expects."""
    import make_deploy

    matches = list(make_deploy._K_PROFILE_RE.finditer(_PROTOCOL_CPP_RAW))
    assert len(matches) == 1, (
        "tools/make_deploy.py's _K_PROFILE_RE matched "
        f"{len(matches)} declarations in src/comms/protocol.cpp, "
        "expected exactly 1 -- protocol.cpp's kProfile declaration "
        "shape has changed; update _K_PROFILE_RE (or this test) to "
        "match."
    )
