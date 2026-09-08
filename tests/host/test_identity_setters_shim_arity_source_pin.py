"""tests/host/test_identity_setters_shim_arity_source_pin.py -- pins the
TS/shim surface for `setDeviceRole()` and `setProfile()` (sprint 037
ticket 006, clasi/sprints/037-runtime-identity-setters-hello-banner-
role-common-name-and-kprofile/tickets/006-ts-shim-arity-and-toolbox-
visibility-pin-test-for-setdevicerole-and-setprofile.md). Mirrors
sprint 036 ticket 004's `test_setupwifi_shim_arity_source_pin.py`
exactly -- same problem (a `run.ts` export and its `sim.ts`
`shim=`-annotated counterpart drifting apart in argument count or
order), same solution, applied to two setters instead of one. Ticket
003's `test_setdevicerole_precedence_source_pin.py` and
`test_setprofile_precedence_source_pin.py` already pin
`Protocol::setDeviceRole()`/`Protocol::setProfile()`'s C++ core -- this
file does not repeat any of that and stays entirely on the
three-layer TS/shim boundary: `src/blocks/run.ts` (student-facing
export) -> `src/blocks/sim.ts` (`shim=`-annotated simulator
counterpart) -> `src/shims.cpp` (the native definition PXT's shim
scanner binds `shim=` to).

**What this is NOT.** Source-text pinning, no TS compiler and no C++
compile -- same convention every other TS-surface check in
`tests/host/` already follows.

**Why each pin is aimed at a specific regression.** Same rationale as
`test_setupwifi_shim_arity_source_pin.py`'s docstring, applied to both
setters:

1. `test_*_three_layer_arity_and_order_agree` -- exactly 2 string
   parameters (role, commonName) for setDeviceRole, exactly 1 string
   parameter (name) for setProfile, in the SAME NAME ORDER across all
   three layers. Comparing only counts or only types would pass a swap
   to `(commonName, role)` in one layer -- comparing declared names in
   order is what actually catches that. Unlike setupWifi's
   `password = ""`, NEITHER setter carries a default on any parameter;
   pinned here too.
2. `test_run_ts_*_call_site_passes_args_in_declared_order` -- an arity
   match alone misses a swapped *call*: both setDeviceRole parameters
   are `string`, so `_setDeviceRole(commonName, role)` at the call site
   compiles fine and silently swaps the two at runtime.
3. `test_shims_cpp_*_pragma_immediately_precedes_declaration` -- the
   same `//%` adjacency rule `registerRunName()`'s comment documents
   (`src/shims.cpp:1835-1838`) and `test_setupwifi_shim_arity_source_
   pin.py` already pins for setupWifi.
4. `test_run_ts_*_is_block_hidden` -- both setters stay
   `//% blockHidden=true`, matching setupWifi's precedent for
   advanced/config calls that should not tempt a student into the
   visible toolbox.
5. `test_shims_cpp_*_emptiness_guard_uses_getutf8size_not_tocharrray`
   -- MEASURED gopiv 2026-09-07, fw 1.20260907.1 (documented in
   `src/shims.cpp`'s own comment above setupWifi, and repeated as
   "Same emptiness trap as setupWifi() above" on both new setters): at
   PXT String size 0, `MSTR(...).toCharArray()` returns junk, not a
   clean `""`. Both setters accept an empty string as a legitimate
   value (an empty role/commonName/name clears the field rather than
   erroring), so each parameter's emptiness check must use
   `->getUTF8Size() == 0`, never a `toCharArray()`-based test.
6. `test_sim_ts_*_records_arguments_not_bare_noop` -- `_setDeviceRole`/
   `_setProfile` must follow the `_setupWifi`/`_setupRadio` pattern
   (record into module-local sim state) and NOT the `_enableWifiLink`
   pattern (bare no-op, nothing to observe).
7. `test_block_toolbox_order_passes_unmodified` -- same-file witness,
   in addition to running `tests/host/test_block_toolbox_order.py`
   directly per the ticket's own instruction, that neither setter
   joined the visible toolbox baseline.

Run with::

    uv run pytest tests/host/test_identity_setters_shim_arity_source_pin.py
"""
import pathlib
import re

# tests/host/test_identity_setters_shim_arity_source_pin.py -> host ->
# tests -> repo root
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
    Mirrors `test_setupwifi_shim_arity_source_pin.py`'s identical
    helper -- each source-pin file in this directory stays
    self-contained rather than sharing a helper module."""
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
    """Splits a parenthesized parameter list on top-level commas and
    parses each into (name, type, default_or_None). Works for both the
    TS shape (`role: string`) and the PXT shim C++ shape
    (`String role`). Identical to
    `test_setupwifi_shim_arity_source_pin.py`'s helper of the same
    name."""
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
# Extraction: run.ts's exported setDeviceRole / setProfile.
# ---------------------------------------------------------------------

_RUN_TS_SETDEVICEROLE_RE = re.compile(
    r"export function setDeviceRole\(([^)]*)\)\s*:\s*void\s*\{"
)
_RUN_TS_SETPROFILE_RE = re.compile(
    r"export function setProfile\(([^)]*)\)\s*:\s*void\s*\{"
)


def _run_ts_match(regex, label):
    m = regex.search(_RUN_TS_TEXT)
    assert m, (
        f"src/blocks/run.ts: no match for {label} -- has the function "
        f"been renamed, removed, or had its return type changed?"
    )
    return m


def _run_ts_setdevicerole_match():
    return _run_ts_match(
        _RUN_TS_SETDEVICEROLE_RE,
        "'export function setDeviceRole(...): void {'",
    )


def _run_ts_setprofile_match():
    return _run_ts_match(
        _RUN_TS_SETPROFILE_RE, "'export function setProfile(...): void {'"
    )


def _run_ts_setdevicerole_params():
    return _parse_param_list(_run_ts_setdevicerole_match().group(1))


def _run_ts_setprofile_params():
    return _parse_param_list(_run_ts_setprofile_match().group(1))


def _run_ts_setdevicerole_body():
    m = _run_ts_setdevicerole_match()
    return _function_body(_RUN_TS_TEXT, m.end(), "run.ts setDeviceRole")


def _run_ts_setprofile_body():
    m = _run_ts_setprofile_match()
    return _function_body(_RUN_TS_TEXT, m.end(), "run.ts setProfile")


# ---------------------------------------------------------------------
# Extraction: sim.ts's shim=-annotated _setDeviceRole / _setProfile.
# ---------------------------------------------------------------------

_SIM_TS_SETDEVICEROLE_RE = re.compile(
    r"//%\s*shim=diffDrive::setDeviceRole\s*\n\s*"
    r"export function _setDeviceRole\(([^)]*)\)\s*:\s*void\s*\{"
)
_SIM_TS_SETPROFILE_RE = re.compile(
    r"//%\s*shim=diffDrive::setProfile\s*\n\s*"
    r"export function _setProfile\(([^)]*)\)\s*:\s*void\s*\{"
)


def _sim_ts_match(regex, label):
    m = regex.search(_SIM_TS_TEXT)
    assert m, (
        f"src/blocks/sim.ts: no match for {label} -- has the shim "
        f"annotation or the declaration moved apart, been renamed, or "
        f"been removed?"
    )
    return m


def _sim_ts_setdevicerole_match():
    return _sim_ts_match(
        _SIM_TS_SETDEVICEROLE_RE,
        "'//% shim=diffDrive::setDeviceRole' immediately followed by "
        "'export function _setDeviceRole(...): void {'",
    )


def _sim_ts_setprofile_match():
    return _sim_ts_match(
        _SIM_TS_SETPROFILE_RE,
        "'//% shim=diffDrive::setProfile' immediately followed by "
        "'export function _setProfile(...): void {'",
    )


def _sim_ts_setdevicerole_params():
    return _parse_param_list(_sim_ts_setdevicerole_match().group(1))


def _sim_ts_setprofile_params():
    return _parse_param_list(_sim_ts_setprofile_match().group(1))


def _sim_ts_setdevicerole_body():
    m = _sim_ts_setdevicerole_match()
    return _function_body(_SIM_TS_TEXT, m.end(), "sim.ts _setDeviceRole")


def _sim_ts_setprofile_body():
    m = _sim_ts_setprofile_match()
    return _function_body(_SIM_TS_TEXT, m.end(), "sim.ts _setProfile")


# ---------------------------------------------------------------------
# Extraction: shims.cpp's native setDeviceRole / setProfile.
# ---------------------------------------------------------------------

_SHIMS_CPP_SETDEVICEROLE_RE = re.compile(r"void setDeviceRole\(([^)]*)\)\s*\{")
_SHIMS_CPP_SETPROFILE_RE = re.compile(r"void setProfile\(([^)]*)\)\s*\{")


def _shims_cpp_match(regex, label):
    m = regex.search(_SHIMS_CPP_TEXT)
    assert m, (
        f"src/shims.cpp: no match for {label} -- has the native "
        f"definition been renamed, removed, or had its return type "
        f"changed?"
    )
    return m


def _shims_cpp_setdevicerole_match():
    return _shims_cpp_match(
        _SHIMS_CPP_SETDEVICEROLE_RE, "'void setDeviceRole(...) {'"
    )


def _shims_cpp_setprofile_match():
    return _shims_cpp_match(
        _SHIMS_CPP_SETPROFILE_RE, "'void setProfile(...) {'"
    )


def _shims_cpp_setdevicerole_params():
    return _parse_param_list(_shims_cpp_setdevicerole_match().group(1))


def _shims_cpp_setprofile_params():
    return _parse_param_list(_shims_cpp_setprofile_match().group(1))


def _shims_cpp_setdevicerole_body():
    m = _shims_cpp_setdevicerole_match()
    return _function_body(_SHIMS_CPP_TEXT, m.end(), "shims.cpp setDeviceRole")


def _shims_cpp_setprofile_body():
    m = _shims_cpp_setprofile_match()
    return _function_body(_SHIMS_CPP_TEXT, m.end(), "shims.cpp setProfile")


# ---------------------------------------------------------------------
# 1. Arity and name-order agreement across all three layers.
# ---------------------------------------------------------------------

def test_setdevicerole_three_layer_arity_and_order_agree():
    """All three declarations must carry exactly 2 string-typed
    parameters, in the same name order (role, commonName), with NO
    default on either (unlike setupWifi's password = ""). Reordering
    `_setDeviceRole`'s parameters to `(commonName, role)` in sim.ts,
    without touching run.ts's call site, changes NEITHER the parameter
    count NOR any type -- both stay `string` -- so only comparing
    declared NAMES in order catches it."""
    run_params = _run_ts_setdevicerole_params()
    sim_params = _sim_ts_setdevicerole_params()
    shim_params = _shims_cpp_setdevicerole_params()

    assert len(run_params) == 2, (
        f"run.ts setDeviceRole: expected 2 parameters, found "
        f"{len(run_params)}: {run_params}"
    )
    assert len(sim_params) == 2, (
        f"sim.ts _setDeviceRole: expected 2 parameters, found "
        f"{len(sim_params)}: {sim_params}"
    )
    assert len(shim_params) == 2, (
        f"shims.cpp setDeviceRole: expected 2 parameters, found "
        f"{len(shim_params)}: {shim_params}"
    )

    run_names = [name for name, _type, _default in run_params]
    sim_names = [name for name, _type, _default in sim_params]
    shim_names = [name for name, _type, _default in shim_params]

    assert run_names == ["role", "commonName"], (
        f"run.ts setDeviceRole: expected parameter order (role, "
        f"commonName), found {run_names}"
    )
    assert sim_names == run_names, (
        f"sim.ts _setDeviceRole's parameter order {sim_names} does not "
        f"match run.ts setDeviceRole's order {run_names} -- a reorder "
        f"here compiles fine (both parameters are string-typed) and "
        f"would silently swap role/commonName at runtime unless the "
        f"call site is reordered to match."
    )
    assert shim_names == run_names, (
        f"shims.cpp setDeviceRole's parameter order {shim_names} does "
        f"not match run.ts setDeviceRole's order {run_names}."
    )

    run_types = [t.lower() for _name, t, _default in run_params]
    sim_types = [t.lower() for _name, t, _default in sim_params]
    shim_types = [t.lower() for _name, t, _default in shim_params]
    assert run_types == ["string", "string"], (
        f"run.ts setDeviceRole: expected both parameters typed string, "
        f"found {run_types}"
    )
    assert sim_types == ["string", "string"], (
        f"sim.ts _setDeviceRole: expected both parameters typed "
        f"string, found {sim_types}"
    )
    assert shim_types == ["string", "string"], (
        f"shims.cpp setDeviceRole: expected both parameters typed "
        f"String, found {shim_types}"
    )

    run_defaults = [d for _n, _t, d in run_params]
    sim_defaults = [d for _n, _t, d in sim_params]
    shim_defaults = [d for _n, _t, d in shim_params]
    assert run_defaults == [None, None], (
        f"run.ts setDeviceRole: expected no default on either "
        f"parameter (unlike setupWifi's password), found {run_defaults}"
    )
    assert sim_defaults == [None, None], (
        f"sim.ts _setDeviceRole: expected no default on either "
        f"parameter, found {sim_defaults}"
    )
    assert shim_defaults == [None, None], (
        f"shims.cpp setDeviceRole: expected no default on either "
        f"parameter, found {shim_defaults}"
    )


def test_setprofile_three_layer_arity_and_order_agree():
    """All three declarations must carry exactly 1 string-typed
    parameter (name), with no default."""
    run_params = _run_ts_setprofile_params()
    sim_params = _sim_ts_setprofile_params()
    shim_params = _shims_cpp_setprofile_params()

    assert len(run_params) == 1, (
        f"run.ts setProfile: expected 1 parameter, found "
        f"{len(run_params)}: {run_params}"
    )
    assert len(sim_params) == 1, (
        f"sim.ts _setProfile: expected 1 parameter, found "
        f"{len(sim_params)}: {sim_params}"
    )
    assert len(shim_params) == 1, (
        f"shims.cpp setProfile: expected 1 parameter, found "
        f"{len(shim_params)}: {shim_params}"
    )

    run_names = [name for name, _type, _default in run_params]
    sim_names = [name for name, _type, _default in sim_params]
    shim_names = [name for name, _type, _default in shim_params]

    assert run_names == ["name"], (
        f"run.ts setProfile: expected parameter name 'name', found "
        f"{run_names}"
    )
    assert sim_names == run_names, (
        f"sim.ts _setProfile's parameter name {sim_names} does not "
        f"match run.ts setProfile's {run_names}."
    )
    assert shim_names == run_names, (
        f"shims.cpp setProfile's parameter name {shim_names} does not "
        f"match run.ts setProfile's {run_names}."
    )

    run_types = [t.lower() for _name, t, _default in run_params]
    sim_types = [t.lower() for _name, t, _default in sim_params]
    shim_types = [t.lower() for _name, t, _default in shim_params]
    assert run_types == ["string"], (
        f"run.ts setProfile: expected parameter typed string, found "
        f"{run_types}"
    )
    assert sim_types == ["string"], (
        f"sim.ts _setProfile: expected parameter typed string, found "
        f"{sim_types}"
    )
    assert shim_types == ["string"], (
        f"shims.cpp setProfile: expected parameter typed String, "
        f"found {shim_types}"
    )

    assert run_params[0][2] is None, (
        f"run.ts setProfile: expected no default on 'name', found "
        f"{run_params[0][2]!r}"
    )
    assert sim_params[0][2] is None, (
        f"sim.ts _setProfile: expected no default on 'name', found "
        f"{sim_params[0][2]!r}"
    )
    assert shim_params[0][2] is None, (
        f"shims.cpp setProfile: expected no default on 'name', found "
        f"{shim_params[0][2]!r}"
    )


# ---------------------------------------------------------------------
# 2. run.ts's call sites pass args in the declared order.
# ---------------------------------------------------------------------

_SETDEVICEROLE_CALL_SITE_RE = re.compile(
    r"_setDeviceRole\(\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_SETPROFILE_CALL_SITE_RE = re.compile(r"_setProfile\(\s*(\w+)\s*\)")


def test_run_ts_setdevicerole_call_site_passes_args_in_declared_order():
    """setDeviceRole()'s body must call _setDeviceRole(role,
    commonName) with both arguments in the SAME order setDeviceRole
    itself declared them -- an arity/name-order match between the two
    declarations (test above) does not by itself prove the call site
    didn't swap the arguments it passes."""
    body = _run_ts_setdevicerole_body()
    call = _SETDEVICEROLE_CALL_SITE_RE.search(body)
    assert call, (
        f"run.ts setDeviceRole(): no call to _setDeviceRole(<arg>, "
        f"<arg>) found in the body:\n{body}"
    )
    declared_order = [n for n, _t, _d in _run_ts_setdevicerole_params()]
    call_order = [call.group(1), call.group(2)]
    assert call_order == declared_order, (
        f"run.ts setDeviceRole(): calls _setDeviceRole({call.group(1)}, "
        f"{call.group(2)}) but setDeviceRole's own declared parameter "
        f"order is {declared_order} -- this passes the two string "
        f"arguments in the wrong order at runtime, which compiles "
        f"cleanly because both are typed string."
    )


def test_run_ts_setprofile_call_site_passes_args_in_declared_order():
    """setProfile()'s body must call _setProfile(name)."""
    body = _run_ts_setprofile_body()
    call = _SETPROFILE_CALL_SITE_RE.search(body)
    assert call, (
        f"run.ts setProfile(): no call to _setProfile(<arg>) found in "
        f"the body:\n{body}"
    )
    declared_name = _run_ts_setprofile_params()[0][0]
    assert call.group(1) == declared_name, (
        f"run.ts setProfile(): calls _setProfile({call.group(1)}) but "
        f"setProfile's own declared parameter is {declared_name!r}."
    )


# ---------------------------------------------------------------------
# 3. shims.cpp: `//%` sits immediately above each declaration.
# ---------------------------------------------------------------------

def _assert_pragma_immediately_precedes(decl_re, label):
    decl_line_index = None
    for i, line in enumerate(_SHIMS_CPP_LINES):
        if decl_re.match(line):
            decl_line_index = i
            break
    assert decl_line_index is not None, (
        f"src/shims.cpp: no line matching {label}'s declaration found."
    )
    assert decl_line_index > 0, (
        f"src/shims.cpp: {label}'s declaration is the first line of "
        f"the file -- there is no line above it for a //% pragma."
    )
    preceding_line = _SHIMS_CPP_LINES[decl_line_index - 1]
    assert re.match(r"^\s*//%\s*$", preceding_line), (
        f"src/shims.cpp: the line immediately above {label}'s "
        f"declaration is {preceding_line!r}, not a bare '//%' pragma -- "
        f"PXT's shim scanner requires //% to sit directly above the "
        f"declaration with nothing in between, not even a comment."
    )


def test_shims_cpp_setdevicerole_pragma_immediately_precedes_declaration():
    """Same `//%` adjacency rule as setupWifi's own pin
    (`registerRunName()`'s comment, src/shims.cpp:1835-1838): a
    comment inserted between the pragma and the declaration fails the
    build with a misleading 'declaration not understood' that names
    the comment line, not the shim."""
    _assert_pragma_immediately_precedes(
        re.compile(r"\s*void\s+setDeviceRole\s*\("), "setDeviceRole"
    )


def test_shims_cpp_setprofile_pragma_immediately_precedes_declaration():
    _assert_pragma_immediately_precedes(
        re.compile(r"\s*void\s+setProfile\s*\("), "setProfile"
    )


# ---------------------------------------------------------------------
# 4. run.ts: both setters are //% blockHidden=true.
# ---------------------------------------------------------------------

_SETDEVICEROLE_BLOCK_HIDDEN_RE = re.compile(
    r"//%\s*blockHidden=true\s*\n\s*export function setDeviceRole\("
)
_SETPROFILE_BLOCK_HIDDEN_RE = re.compile(
    r"//%\s*blockHidden=true\s*\n\s*export function setProfile\("
)


def test_run_ts_setdevicerole_is_block_hidden():
    """Matches setupWifi's precedent: a visible toolbox block would
    invite a beginner to drag setDeviceRole into a shared project and
    hardcode a role/commonName override in the tracked program. Pinned
    directly here, in addition to test_block_toolbox_order.py
    continuing to pass unmodified (confirmed separately below)."""
    assert _SETDEVICEROLE_BLOCK_HIDDEN_RE.search(_RUN_TS_TEXT), (
        "src/blocks/run.ts: no '//% blockHidden=true' found "
        "immediately above 'export function setDeviceRole(' -- a "
        "visible block here would let it join the toolbox baseline."
    )


def test_run_ts_setprofile_is_block_hidden():
    assert _SETPROFILE_BLOCK_HIDDEN_RE.search(_RUN_TS_TEXT), (
        "src/blocks/run.ts: no '//% blockHidden=true' found "
        "immediately above 'export function setProfile(' -- a visible "
        "block here would let it join the toolbox baseline."
    )


def test_block_toolbox_order_passes_unmodified():
    """Same-file witness, in addition to running
    tests/host/test_block_toolbox_order.py directly per the ticket's
    own instruction: import its extraction/order-check functions and
    confirm neither setDeviceRole nor setProfile -- both hidden and
    captionless -- joined any group's visible baseline."""
    import test_block_toolbox_order as toolbox

    entries = toolbox._extract_entries()
    visible_names = {name for _kind, name, _grp, _cap, _w in entries}
    assert "setDeviceRole" not in visible_names, (
        "setDeviceRole appears among the visible toolbox entries "
        "extracted by test_block_toolbox_order.py -- it must stay "
        "//% blockHidden=true and out of the toolbox baseline."
    )
    assert "setProfile" not in visible_names, (
        "setProfile appears among the visible toolbox entries "
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
        f"after setDeviceRole/setProfile landed: {mismatches}"
    )


# ---------------------------------------------------------------------
# 5. shims.cpp: emptiness guards use getUTF8Size(), not a
#    toCharArray()-based test.
# ---------------------------------------------------------------------

_TOCHARARRAY_EMPTINESS_RE = re.compile(
    r"toCharArray\(\)\s*(?:\[\s*0\s*\]\s*==\s*'\\0'|==\s*(?:nullptr|0))"
)


def test_shims_cpp_setdevicerole_emptiness_guard_uses_getutf8size_not_tocharrray():
    """Same trap as setupWifi's own pin: MEASURED gopiv 2026-09-07, fw
    1.20260907.1 (src/shims.cpp's own comment above setupWifi; both
    new setters carry "Same emptiness trap as setupWifi() above").
    At PXT String size 0, MSTR(...).toCharArray() returns junk, not a
    clean "". An empty role or commonName is a legitimate value (it
    clears the field), so both emptiness checks must use
    ->getUTF8Size() == 0, and no toCharArray()-based emptiness test
    may have crept back in."""
    body = _shims_cpp_setdevicerole_body()
    assert re.search(r"role->getUTF8Size\(\)\s*==\s*0", body), (
        f"shims.cpp setDeviceRole(): no 'role->getUTF8Size() == 0' "
        f"emptiness check found:\n{body}"
    )
    assert re.search(r"commonName->getUTF8Size\(\)\s*==\s*0", body), (
        f"shims.cpp setDeviceRole(): no 'commonName->getUTF8Size() == "
        f"0' emptiness check found:\n{body}"
    )
    assert not _TOCHARARRAY_EMPTINESS_RE.search(body), (
        f"shims.cpp setDeviceRole(): found a toCharArray()-based "
        f"emptiness test -- at PXT String size 0, toCharArray() "
        f"returns junk, not a clean \"\" (MEASURED gopiv 2026-09-07, "
        f"fw 1.20260907.1). Emptiness must be tested via "
        f"->getUTF8Size() == 0 instead:\n{body}"
    )


def test_shims_cpp_setprofile_emptiness_guard_uses_getutf8size_not_tocharrray():
    body = _shims_cpp_setprofile_body()
    assert re.search(r"name->getUTF8Size\(\)\s*==\s*0", body), (
        f"shims.cpp setProfile(): no 'name->getUTF8Size() == 0' "
        f"emptiness check found:\n{body}"
    )
    assert not _TOCHARARRAY_EMPTINESS_RE.search(body), (
        f"shims.cpp setProfile(): found a toCharArray()-based "
        f"emptiness test -- at PXT String size 0, toCharArray() "
        f"returns junk, not a clean \"\" (MEASURED gopiv 2026-09-07, "
        f"fw 1.20260907.1). Emptiness must be tested via "
        f"->getUTF8Size() == 0 instead:\n{body}"
    )


# ---------------------------------------------------------------------
# 6. sim.ts: both shims record their arguments, not a bare no-op.
# ---------------------------------------------------------------------

def test_sim_ts_setdevicerole_records_arguments_not_bare_noop():
    """_setDeviceRole must follow the _setupWifi/_setupRadio pattern
    (records into module-local sim state so a sim test can assert what
    a program passed) and NOT the _enableWifiLink pattern (bare no-op,
    nothing to observe). Pins that both declared parameters are
    assigned into sim-local state inside the body."""
    body = _sim_ts_setdevicerole_body()
    params = _sim_ts_setdevicerole_params()
    role_name, common_name_name = params[0][0], params[1][0]

    role_assign = re.search(rf"(\w+)\s*=\s*{re.escape(role_name)}\b", body)
    common_name_assign = re.search(
        rf"(\w+)\s*=\s*{re.escape(common_name_name)}\b", body
    )
    assert role_assign, (
        f"sim.ts _setDeviceRole(): no assignment of the '{role_name}' "
        f"parameter into any sim-local variable found -- this must "
        f"record its argument like _setupWifi does, not no-op like "
        f"_enableWifiLink:\n{body}"
    )
    assert common_name_assign, (
        f"sim.ts _setDeviceRole(): no assignment of the "
        f"'{common_name_name}' parameter into any sim-local variable "
        f"found:\n{body}"
    )


def test_sim_ts_setprofile_records_arguments_not_bare_noop():
    body = _sim_ts_setprofile_body()
    params = _sim_ts_setprofile_params()
    name_name = params[0][0]

    name_assign = re.search(rf"(\w+)\s*=\s*{re.escape(name_name)}\b", body)
    assert name_assign, (
        f"sim.ts _setProfile(): no assignment of the '{name_name}' "
        f"parameter into any sim-local variable found -- this must "
        f"record its argument like _setupWifi does, not no-op like "
        f"_enableWifiLink:\n{body}"
    )
