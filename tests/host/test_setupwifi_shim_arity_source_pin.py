"""tests/host/test_setupwifi_shim_arity_source_pin.py -- pins the
TS/shim surface for `setupWifi()` (sprint 036 ticket 004,
clasi/sprints/036-runtime-wifi-credentials-via-setupwifi/tickets/
004-ts-shim-arity-and-toolbox-visibility-pin-test-for-setupwifi.md).
Ticket 003's `test_setupwifi_precedence_source_pin.py` already pins
`Protocol::setupWifi()`'s C++ core (precedence flag, late-call guard,
truncation, `DBG:wifi` field) -- this file does not repeat any of that
and stays entirely on the three-layer TS/shim boundary:
`src/blocks/run.ts` (student-facing export) -> `src/blocks/sim.ts`
(`shim=`-annotated simulator counterpart) -> `src/shims.cpp` (the
native definition PXT's shim scanner binds `shim=` to).

**What this is NOT.** Source-text pinning, no TS compiler and no C++
compile -- same convention every other TS-surface check in
`tests/host/` already follows (`test_block_toolbox_order.py`), and the
same reason `test_setupwifi_precedence_source_pin.py` gives for why
`protocol.cpp` can't be compiled here: `pxt.h` and its CODAL/PXT
dependency chain are not available to a host build.

**Why each pin is aimed at a specific regression, not "the text is
present".**

1. `test_three_layer_arity_and_order_agree` -- the actual arity/
   adjacency check the ticket asks for: `run.ts`'s exported
   `setupWifi`, `sim.ts`'s `shim=`-annotated `_setupWifi`, and
   `shims.cpp`'s native `setupWifi` must all declare exactly 2
   string-typed parameters, in the SAME NAME ORDER (ssid, password).
   Comparing only counts or only types would pass a swap to
   `(password, ssid)` in one layer -- comparing declared names in
   order is what actually catches that. This is also the pin the
   ticket's third acceptance criterion names directly: reorder
   `_setupWifi`'s parameters to `(password, ssid)` without touching
   the call site, and this test must fail.
2. `test_run_ts_call_site_passes_ssid_password_in_declared_order` --
   an arity match alone misses a swapped *call*: both parameters are
   `string`, so `_setupWifi(password, ssid)` at the call site compiles
   fine and silently swaps the two at runtime. This pins the actual
   argument order at the call site against `setupWifi`'s own declared
   parameter order, not just against the shim's parameter names.
3. `test_shims_cpp_pragma_immediately_precedes_declaration` -- the
   `//%` adjacency rule `registerRunName()`'s own comment documents
   (`src/shims.cpp:1835-1838`): PXT's shim scanner requires `//%` to
   sit IMMEDIATELY above the declaration it annotates, with nothing
   between -- not even a comment. A comment inserted between the two
   fails the build with a misleading "declaration not understood" that
   names the comment line, not the shim.
4. `test_run_ts_setup_wifi_is_block_hidden` -- defends a security
   property, not a style choice: a visible toolbox block would invite
   a beginner to drag `setupWifi` into a shared project and hardcode a
   passphrase in the tracked program, exactly what the `secrets.ts`
   split (this sprint's whole point) exists to prevent. Pinned
   directly here, in addition to `test_block_toolbox_order.py`
   continuing to pass unmodified (confirmed separately below) -- that
   file's baseline is an indirect witness (it would need a new visible
   entry if `setupWifi` ever grew a `block=` caption without staying
   hidden), this test is the direct one.
5. `test_shims_cpp_emptiness_guard_uses_getutf8size_not_tocharrray` --
   MEASURED gopiv 2026-09-07, fw 1.20260907.1 (documented in
   `src/shims.cpp`'s own comment above `setupWifi`, and the same trap
   `registerRunName()`'s comment independently documents): at PXT
   String size 0, `MSTR(...).toCharArray()` returns junk, not a clean
   `""`. `setupWifi("")` is a REQUIRED path -- SUC-002's explicit
   disable -- so an empty SSID must reach `Protocol::setupWifi()` as a
   genuine `""`. Pins that both the ssid and password emptiness checks
   use `->getUTF8Size() == 0`, and that no `toCharArray()`-based
   emptiness test (peeking at the first byte, or comparing a
   `toCharArray()` result) has crept back in.
6. `test_sim_ts_setup_wifi_records_arguments_not_bare_noop` -- `_setupWifi`
   must follow the `_setupRadio` pattern (records into module-local sim
   state so a sim test can assert what a program passed) and NOT the
   `_enableWifiLink` pattern (bare no-op, nothing to observe) --
   `sim.ts:543` and `:565` are the two precedents this test tells
   apart. Confirms both sim-local variables are assigned from the
   corresponding parameter.
7. `test_block_toolbox_order_passes_unmodified` -- runs (via direct
   import, not a subprocess) the two toolbox-order assertions from
   `tests/host/test_block_toolbox_order.py` as a same-file witness that
   ticket 002's `setupWifi` landed without joining the visible toolbox
   baseline -- see that file's own docstring for why a hidden function
   with no `block=` caption is excluded from its scan already. The
   ticket's own instruction is to run that file directly and confirm
   it needs no changes; this local call is a belt-and-braces repeat so
   a `uv run pytest` scoped to just this file still catches a
   toolbox-baseline regression caused by `setupWifi`.

Run with::

    uv run pytest tests/host/test_setupwifi_shim_arity_source_pin.py
"""
import pathlib
import re

# tests/host/test_setupwifi_shim_arity_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_RUN_TS = _REPO_ROOT / "src" / "blocks" / "run.ts"
_SIM_TS = _REPO_ROOT / "src" / "blocks" / "sim.ts"
_SHIMS_CPP = _REPO_ROOT / "src" / "shims.cpp"

_RUN_TS_TEXT = _RUN_TS.read_text(encoding="utf-8")
_SIM_TS_TEXT = _SIM_TS.read_text(encoding="utf-8")
_SHIMS_CPP_TEXT = _SHIMS_CPP.read_text(encoding="utf-8")
_SHIMS_CPP_LINES = _SHIMS_CPP_TEXT.splitlines()


def _function_body(source_text, open_brace_end, label):
    """Brace-matches from the position just after a function's opening
    `{` (i.e. `open_brace_end` is the index of the char right after
    it) and returns the body text, not including the enclosing braces.
    Mirrors `test_setupwifi_precedence_source_pin.py`'s identical
    helper -- each source-pin file in this directory stays
    self-contained rather than sharing a helper module (no such module
    exists in `tests/host/` as of this ticket)."""
    depth = 1
    i = open_brace_end
    while i < len(source_text):
        if source_text[i] == "{":
            depth += 1
        elif source_text[i] == "}":
            depth -= 1
            if depth == 0:
                return source_text[open_brace_end:i]
        i += 1
    raise AssertionError(f"{label}: unbalanced braces scanning body")


def _parse_param_list(params_text):
    """Splits a parenthesized parameter list on top-level commas (none
    of the three declarations nest parens or generics inside a
    parameter) and parses each into (name, type, default_or_None).
    Works for both the TS shape (`ssid: string`, `password: string =
    ""`) and the PXT shim C++ shape (`String ssid`)."""
    params_text = params_text.strip()
    if not params_text:
        return []
    parts = [p.strip() for p in params_text.split(",")]
    parsed = []
    for part in parts:
        # TS shape: NAME : TYPE [= DEFAULT]
        m = re.match(r"^(\w+)\s*:\s*(\w+)\s*(?:=\s*(.+))?$", part)
        if m:
            parsed.append((m.group(1), m.group(2), m.group(3)))
            continue
        # C++ shim shape: TYPE NAME
        m = re.match(r"^(\w+)\s+(\w+)$", part)
        if m:
            parsed.append((m.group(2), m.group(1), None))
            continue
        raise AssertionError(f"could not parse parameter {part!r}")
    return parsed


# ---------------------------------------------------------------------
# Extraction: run.ts's exported setupWifi.
# ---------------------------------------------------------------------

_RUN_TS_SETUPWIFI_RE = re.compile(
    r"export function setupWifi\(([^)]*)\)\s*:\s*void\s*\{"
)


def _run_ts_setupwifi_match():
    m = _RUN_TS_SETUPWIFI_RE.search(_RUN_TS_TEXT)
    assert m, (
        "src/blocks/run.ts: no match for "
        r"'export function setupWifi(...): void {' -- has setupWifi() "
        "been renamed, removed, or had its return type changed?"
    )
    return m


def _run_ts_setupwifi_params():
    return _parse_param_list(_run_ts_setupwifi_match().group(1))


def _run_ts_setupwifi_body():
    m = _run_ts_setupwifi_match()
    return _function_body(_RUN_TS_TEXT, m.end(), "run.ts setupWifi")


# ---------------------------------------------------------------------
# Extraction: sim.ts's shim=-annotated _setupWifi.
# ---------------------------------------------------------------------

_SIM_TS_SETUPWIFI_RE = re.compile(
    r"//%\s*shim=diffDrive::setupWifi\s*\n\s*"
    r"export function _setupWifi\(([^)]*)\)\s*:\s*void\s*\{"
)


def _sim_ts_setupwifi_match():
    m = _SIM_TS_SETUPWIFI_RE.search(_SIM_TS_TEXT)
    assert m, (
        "src/blocks/sim.ts: no match for '//% shim=diffDrive::setupWifi' "
        "immediately followed by 'export function _setupWifi(...): "
        "void {' -- has the shim annotation or the declaration moved "
        "apart, been renamed, or been removed?"
    )
    return m


def _sim_ts_setupwifi_params():
    return _parse_param_list(_sim_ts_setupwifi_match().group(1))


def _sim_ts_setupwifi_body():
    m = _sim_ts_setupwifi_match()
    return _function_body(_SIM_TS_TEXT, m.end(), "sim.ts _setupWifi")


# ---------------------------------------------------------------------
# Extraction: shims.cpp's native setupWifi.
# ---------------------------------------------------------------------

_SHIMS_CPP_SETUPWIFI_RE = re.compile(
    r"void setupWifi\(([^)]*)\)\s*\{"
)


def _shims_cpp_setupwifi_match():
    m = _SHIMS_CPP_SETUPWIFI_RE.search(_SHIMS_CPP_TEXT)
    assert m, (
        "src/shims.cpp: no match for 'void setupWifi(...) {' -- has "
        "the native definition been renamed, removed, or had its "
        "return type changed?"
    )
    return m


def _shims_cpp_setupwifi_params():
    return _parse_param_list(_shims_cpp_setupwifi_match().group(1))


def _shims_cpp_setupwifi_body():
    m = _shims_cpp_setupwifi_match()
    return _function_body(_SHIMS_CPP_TEXT, m.end(), "shims.cpp setupWifi")


# ---------------------------------------------------------------------
# 1. Arity and name-order agreement across all three layers.
# ---------------------------------------------------------------------

def test_three_layer_arity_and_order_agree():
    """All three declarations must carry exactly 2 string-typed
    parameters, in the same name order (ssid, password). This is the
    actual regression the ticket targets: reordering `_setupWifi`'s
    parameters to `(password, ssid)` in sim.ts, without touching
    run.ts's call site, changes NEITHER the parameter count NOR any
    type -- both stay `string` -- so only comparing declared NAMES in
    order catches it."""
    run_params = _run_ts_setupwifi_params()
    sim_params = _sim_ts_setupwifi_params()
    shim_params = _shims_cpp_setupwifi_params()

    assert len(run_params) == 2, (
        f"run.ts setupWifi: expected 2 parameters, found "
        f"{len(run_params)}: {run_params}"
    )
    assert len(sim_params) == 2, (
        f"sim.ts _setupWifi: expected 2 parameters, found "
        f"{len(sim_params)}: {sim_params}"
    )
    assert len(shim_params) == 2, (
        f"shims.cpp setupWifi: expected 2 parameters, found "
        f"{len(shim_params)}: {shim_params}"
    )

    run_names = [name for name, _type, _default in run_params]
    sim_names = [name for name, _type, _default in sim_params]
    shim_names = [name for name, _type, _default in shim_params]

    assert run_names == ["ssid", "password"], (
        f"run.ts setupWifi: expected parameter order (ssid, password), "
        f"found {run_names}"
    )
    assert sim_names == run_names, (
        f"sim.ts _setupWifi's parameter order {sim_names} does not "
        f"match run.ts setupWifi's order {run_names} -- a reorder here "
        f"compiles fine (both parameters are string-typed) and would "
        f"silently swap ssid/password at runtime unless the call site "
        f"is reordered to match."
    )
    assert shim_names == run_names, (
        f"shims.cpp setupWifi's parameter order {shim_names} does not "
        f"match run.ts setupWifi's order {run_names}."
    )

    run_types = [t.lower() for _name, t, _default in run_params]
    sim_types = [t.lower() for _name, t, _default in sim_params]
    shim_types = [t.lower() for _name, t, _default in shim_params]
    assert run_types == ["string", "string"], (
        f"run.ts setupWifi: expected both parameters typed string, "
        f"found {run_types}"
    )
    assert sim_types == ["string", "string"], (
        f"sim.ts _setupWifi: expected both parameters typed string, "
        f"found {sim_types}"
    )
    assert shim_types == ["string", "string"], (
        f"shims.cpp setupWifi: expected both parameters typed String, "
        f"found {shim_types}"
    )

    # run.ts's password carries the default that makes
    # diffDrive.setupWifi(SSID) legal; PXT shims don't carry defaults
    # across the shim= boundary (setupRadio's channel/group: number =
    # 10 default is likewise not repeated in _setupRadio's signature,
    # sim.ts:543 -- the precedent this mirrors), so sim.ts and
    # shims.cpp must NOT declare one.
    assert run_params[1][2] == '""', (
        f"run.ts setupWifi: expected password: string = \"\" (the "
        f"default that makes setupWifi(SSID) legal), found default "
        f"{run_params[1][2]!r}"
    )
    assert sim_params[1][2] is None, (
        f"sim.ts _setupWifi: expected no default on the password "
        f"parameter (shim= declarations don't carry the run.ts "
        f"wrapper's default), found {sim_params[1][2]!r}"
    )
    assert shim_params[1][2] is None, (
        f"shims.cpp setupWifi: expected no default on the password "
        f"parameter, found {shim_params[1][2]!r}"
    )


# ---------------------------------------------------------------------
# 2. run.ts's call site passes ssid, password in the declared order.
# ---------------------------------------------------------------------

_CALL_SITE_RE = re.compile(r"_setupWifi\(\s*(\w+)\s*,\s*(\w+)\s*\)")


def test_run_ts_call_site_passes_ssid_password_in_declared_order():
    """setupWifi()'s body must call _setupWifi(ssid, password) with
    both arguments in the SAME order setupWifi itself declared them --
    an arity/name-order match between the two declarations (test
    above) does not by itself prove the call site didn't swap the
    arguments it passes."""
    body = _run_ts_setupwifi_body()
    call = _CALL_SITE_RE.search(body)
    assert call, (
        f"run.ts setupWifi(): no call to _setupWifi(<arg>, <arg>) "
        f"found in the body:\n{body}"
    )
    declared_order = [n for n, _t, _d in _run_ts_setupwifi_params()]
    call_order = [call.group(1), call.group(2)]
    assert call_order == declared_order, (
        f"run.ts setupWifi(): calls _setupWifi({call.group(1)}, "
        f"{call.group(2)}) but setupWifi's own declared parameter "
        f"order is {declared_order} -- this passes the two string "
        f"arguments in the wrong order at runtime, which compiles "
        f"cleanly because both are typed string."
    )


# ---------------------------------------------------------------------
# 3. shims.cpp: `//%` sits immediately above the declaration.
# ---------------------------------------------------------------------

def test_shims_cpp_pragma_immediately_precedes_declaration():
    """PXT's shim scanner requires `//%` to sit IMMEDIATELY above the
    declaration it annotates -- registerRunName()'s own comment
    documents this exact rule (src/shims.cpp:1835-1838): a comment
    between the two fails the build with a misleading 'declaration not
    understood' naming the comment line, not the real problem. Finds
    setupWifi's declaration line and asserts the line directly above
    it is the bare `//%` pragma, with nothing -- not even a comment --
    in between."""
    decl_line_index = None
    for i, line in enumerate(_SHIMS_CPP_LINES):
        if re.match(r"\s*void\s+setupWifi\s*\(", line):
            decl_line_index = i
            break
    assert decl_line_index is not None, (
        "src/shims.cpp: no line matching 'void setupWifi(' found."
    )
    assert decl_line_index > 0, (
        "src/shims.cpp: setupWifi's declaration is the first line of "
        "the file -- there is no line above it for a //% pragma."
    )
    preceding_line = _SHIMS_CPP_LINES[decl_line_index - 1]
    assert re.match(r"^\s*//%\s*$", preceding_line), (
        f"src/shims.cpp: the line immediately above setupWifi's "
        f"declaration is {preceding_line!r}, not a bare '//%' pragma -- "
        f"PXT's shim scanner requires //% to sit directly above the "
        f"declaration with nothing in between, not even a comment."
    )


# ---------------------------------------------------------------------
# 4. run.ts: setupWifi is //% blockHidden=true.
# ---------------------------------------------------------------------

_BLOCK_HIDDEN_RE = re.compile(
    r"//%\s*blockHidden=true\s*\n\s*export function setupWifi\("
)


def test_run_ts_setup_wifi_is_block_hidden():
    """Deliberate, not a style choice: a visible toolbox block would
    invite a beginner to drag setupWifi into a shared project and
    hardcode a passphrase in the tracked program -- exactly what the
    secrets.ts split exists to prevent. Pins that the //% blockHidden=
    true pragma sits directly above setupWifi's declaration (the same
    adjacency enableWifiLink and enableRadioLink already use)."""
    assert _BLOCK_HIDDEN_RE.search(_RUN_TS_TEXT), (
        "src/blocks/run.ts: no '//% blockHidden=true' found "
        "immediately above 'export function setupWifi(' -- a visible "
        "setupWifi block would let a student drag it into the toolbox "
        "and hardcode credentials in a tracked program, which is "
        "exactly what the secrets.ts split exists to prevent."
    )


def test_block_toolbox_order_passes_unmodified():
    """Same-file witness, in addition to running
    tests/host/test_block_toolbox_order.py directly per the ticket's
    own instruction: import its extraction/order-check functions and
    confirm setupWifi -- hidden and captionless -- did not join any
    group's visible baseline. See that file's own docstring for why a
    hidden function with no block= caption is excluded from its scan
    already; this call proves that stays true for setupWifi
    specifically, from within this file's own test run."""
    import test_block_toolbox_order as toolbox

    entries = toolbox._extract_entries()
    visible_names = {name for _kind, name, _grp, _cap, _w in entries}
    assert "setupWifi" not in visible_names, (
        "setupWifi appears among the visible toolbox entries "
        "extracted by test_block_toolbox_order.py -- it must stay "
        "//% blockHidden=true and out of the toolbox baseline."
    )

    rendered = toolbox._rendered_group_order(entries)
    mismatches = {}
    for group, expected in toolbox._BASELINE_GROUP_ORDER.items():
        actual = rendered.get(group, [])
        if actual != expected:
            mismatches[group] = {"expected": expected, "actual": actual}
    assert not mismatches, (
        "toolbox within-group order drifted from the approved layout "
        f"after setupWifi landed: {mismatches}"
    )


# ---------------------------------------------------------------------
# 5. shims.cpp: emptiness guard uses getUTF8Size(), not a
#    toCharArray()-based test.
# ---------------------------------------------------------------------

_SSID_GUARD_RE = re.compile(r"ssid->getUTF8Size\(\)\s*==\s*0")
_PASSWORD_GUARD_RE = re.compile(r"password->getUTF8Size\(\)\s*==\s*0")
_TOCHARARRAY_EMPTINESS_RE = re.compile(
    r"toCharArray\(\)\s*(?:\[\s*0\s*\]\s*==\s*'\\0'|==\s*(?:nullptr|0))"
)


def test_shims_cpp_emptiness_guard_uses_getutf8size_not_tocharrray():
    """MEASURED gopiv 2026-09-07, fw 1.20260907.1 (documented in this
    same function's own source comment, and independently in
    registerRunName()'s): at PXT String size 0, MSTR(...).
    toCharArray() returns junk, not a clean "". setupWifi("") is a
    REQUIRED path (SUC-002's explicit disable), so an empty SSID must
    reach Protocol::setupWifi() as a genuine "". Pins both emptiness
    checks use ->getUTF8Size() == 0, and that no
    toCharArray()-based emptiness test has crept back in."""
    body = _shims_cpp_setupwifi_body()
    assert _SSID_GUARD_RE.search(body), (
        f"shims.cpp setupWifi(): no 'ssid->getUTF8Size() == 0' "
        f"emptiness check found:\n{body}"
    )
    assert _PASSWORD_GUARD_RE.search(body), (
        f"shims.cpp setupWifi(): no 'password->getUTF8Size() == 0' "
        f"emptiness check found (directly, or via a passwordEmpty "
        f"helper expression):\n{body}"
    )
    assert not _TOCHARARRAY_EMPTINESS_RE.search(body), (
        f"shims.cpp setupWifi(): found a toCharArray()-based emptiness "
        f"test -- at PXT String size 0, toCharArray() returns junk, not "
        f"a clean \"\" (MEASURED gopiv 2026-09-07, fw 1.20260907.1). "
        f"Emptiness must be tested via ->getUTF8Size() == 0 instead:"
        f"\n{body}"
    )


# ---------------------------------------------------------------------
# 6. sim.ts: _setupWifi records its arguments, not a bare no-op.
# ---------------------------------------------------------------------

def test_sim_ts_setup_wifi_records_arguments_not_bare_noop():
    """_setupWifi must follow the _setupRadio pattern (records into
    module-local sim state so a sim test can assert what a program
    passed, sim.ts:543) and NOT the _enableWifiLink pattern (bare
    no-op, sim.ts:565) -- there is no WiFi module to simulate, but a
    test might reasonably want to assert what a program called
    setupWifi with. Pins that both declared parameters are assigned
    into sim-local state inside the body."""
    body = _sim_ts_setupwifi_body()
    params = _sim_ts_setupwifi_params()
    ssid_name, password_name = params[0][0], params[1][0]

    ssid_assign = re.search(
        rf"(\w+)\s*=\s*{re.escape(ssid_name)}\b", body
    )
    password_assign = re.search(
        rf"(\w+)\s*=\s*{re.escape(password_name)}\b", body
    )
    assert ssid_assign, (
        f"sim.ts _setupWifi(): no assignment of the '{ssid_name}' "
        f"parameter into any sim-local variable found -- this must "
        f"record its argument like _setupRadio does, not no-op like "
        f"_enableWifiLink:\n{body}"
    )
    assert password_assign, (
        f"sim.ts _setupWifi(): no assignment of the '{password_name}' "
        f"parameter into any sim-local variable found:\n{body}"
    )
