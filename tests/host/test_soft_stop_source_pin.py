"""tests/host/test_soft_stop_source_pin.py -- one soft stop, four
callers (sprint 033 ticket 004,
config-descriptor-table-softstop-goto-deadline.md).

**What this fixes.** The soft-stop sequence -- `engine.endMove()`,
`kernel.neutral()`, and the port-level immediate zero -- was written out
independently in `stopAll()`, `endMove()`, the starvation watchdog, and
`updateMove()`'s move-completion branch. Four copies of one sequence are
four chances for them to stop agreeing, and they already had:
`updateMove()`'s branch carried only the port write, so a move that
ended on that path never got the unconditional `kernel.neutral()` the
other three had. `Rig::softStop()` is now the single definition and all
four call it.

**Why this is a source-text test, not a behavioral one.**
`tests/host/` cannot compile `shims.cpp` at all -- it includes `pxt.h`
transitively -- so there is no way to link the real `Rig` and count
calls into a mock port. The same precedent
`test_staged_stop_source_pin.py` and `test_bus_guard_source_pin.py`
document applies: this proves the source SHAPE (one definition, four
callers, no inline copies) is present, not that the sequence behaves
correctly on hardware. `test_staged_stop_source_pin.py` pins the
cross-fiber staging inside that one definition;
`test_cross_fiber_stop_settle_window.py` and
`test_stop_move_zeros_continuous_drive.py` are what exercise the
underlying primitives against a real kernel.

Run with::

    uv run pytest tests/host/test_soft_stop_source_pin.py
"""
import pathlib
import re

# tests/host/test_soft_stop_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SHIMS_CPP = _REPO_ROOT / "src" / "shims.cpp"
_SHIMS_TEXT = _SHIMS_CPP.read_text()


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    same technique test_staged_stop_source_pin.py uses, duplicated here
    (each source-pin file in this directory is self-contained, per
    precedent) rather than imported."""
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
    opening `{`) in `source_text` and returns the brace-matched body
    (NOT including the enclosing braces)."""
    m = re.search(signature_pattern, source_text)
    assert m, (
        f"{label}: no match for {signature_pattern!r} in "
        f"{_SHIMS_CPP.relative_to(_REPO_ROOT)} -- has this function been "
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


_SHIMS_STRIPPED = _strip_comments(_SHIMS_TEXT)

_SOFT_STOP_SIG = r"void\s+Rig::softStop\s*\(\s*\)\s*\{"

# The four stop paths the ticket names, each keyed by a signature
# specific enough not to collide with a call (`r.engine.endMove()` must
# not match the free function `endMove()`).
_CALL_SITES = {
    "stopAll": r"\bvoid\s+stopAll\s*\(\s*\)\s*\{",
    "endMove": r"^void\s+endMove\s*\(\s*\)\s*\{",
    "watchdogEntry": r"static\s+void\s+watchdogEntry\s*\(\s*void\*\s*context\s*\)\s*\{",
    "updateMove": r"\bbool\s+updateMove\s*\(\s*\)\s*\{",
}


def _site_body(name):
    flags_pattern = _CALL_SITES[name]
    if flags_pattern.startswith("^"):
        # `endMove` needs a line anchor to avoid matching a call.
        m = re.search(flags_pattern, _SHIMS_STRIPPED, re.MULTILINE)
        assert m, f"{name}: signature not found"
        return _function_body(
            _SHIMS_STRIPPED[m.start():], flags_pattern.lstrip("^"), name
        )
    return _function_body(_SHIMS_STRIPPED, flags_pattern, name)


def test_soft_stop_is_defined_exactly_once():
    """One definition of the sequence, and it is a member of `Rig` --
    the object that owns every piece of state it touches (the engine,
    the kernel, both motor ports, the bus guard and the staging flag)."""
    definitions = re.findall(_SOFT_STOP_SIG, _SHIMS_STRIPPED)
    assert len(definitions) == 1, (
        f"expected exactly one `void Rig::softStop() {{` definition in "
        f"shims.cpp, found {len(definitions)}"
    )
    assert re.search(r"^\s*void softStop\(\);\s*$", _SHIMS_STRIPPED, re.MULTILINE), (
        "Rig no longer declares softStop() as a member -- the point of "
        "the consolidation is that the one stop sequence belongs to the "
        "object that owns the state it touches."
    )


def test_soft_stop_body_carries_all_three_parts():
    """The consolidation is only worth anything if the one definition is
    the WHOLE sequence: clear the move engine, disarm the kernel's held
    command, and write the ports (or stage that write)."""
    body = _function_body(_SHIMS_STRIPPED, _SOFT_STOP_SIG, "Rig::softStop")
    for fragment in ("engine.endMove()", "kernel.neutral()", "emergencyStop"):
        assert fragment in body, (
            f"Rig::softStop() is missing `{fragment}` -- a partial stop "
            f"is what the four hand-written copies already were:\n{body}"
        )


def test_all_four_stop_paths_call_soft_stop():
    """`stopAll()` (the `stop` block and the wire's STOP verb),
    `endMove()` (the `stop move` block), the starvation watchdog, and
    `updateMove()`'s move-completion branch."""
    for name in _CALL_SITES:
        body = _site_body(name)
        assert re.search(r"\b(?:r\.|rig->)softStop\s*\(\s*\)", body), (
            f"{name}(): does not call softStop():\n{body}"
        )


def test_no_stop_path_still_writes_the_sequence_inline():
    """The copies are gone, not merely joined by a fifth. A stop path
    that still calls `engine.endMove()`, `kernel.neutral()` or a port's
    `emergencyStop()` itself has kept its own copy of a sequence that
    now has one owner."""
    for name in _CALL_SITES:
        body = _site_body(name)
        for fragment in ("engine.endMove()", "kernel.neutral()", "emergencyStop"):
            assert fragment not in body, (
                f"{name}(): still writes `{fragment}` inline instead of "
                f"routing through softStop():\n{body}"
            )


def test_updateMove_completion_branch_is_the_one_that_gained_the_pair():
    """`updateMove()`'s branch is the site that was NOT equal to the
    other three: it delivered the port write alone, with no
    `engine.endMove()`/`kernel.neutral()`. Routing it through
    `softStop()` is what makes the four agree, so pin that the call is
    inside the `wasActive && !moveActive` branch rather than somewhere
    else in the function."""
    body = _site_body("updateMove")
    assert re.search(
        r"if\s*\(\s*wasActive\s*&&\s*!moveActive\s*\)\s*r\.softStop\s*\(\s*\)\s*;",
        body,
    ), (
        "updateMove(): the move-completion branch no longer reads "
        f"`if (wasActive && !moveActive) r.softStop();`:\n{body}"
    )


def test_deliver_stop_now_survives_only_as_one_line_of_history():
    """The sprint's own bar: `grep -c 'deliverStopNow' src/shims.cpp` is
    1. The free function is gone -- `Rig::softStop()` absorbed it -- and
    the single surviving line is a COMMENT saying so, kept because
    `src/DESIGN.md`, `tests/host/fake_ports.h` and several code-review
    documents still refer to the old name and a reader arriving from one
    of them needs a pointer. Any second occurrence means either the
    function came back or the comments naming it were left behind, and
    both are what this ticket removed."""
    hits = [
        (n, line)
        for n, line in enumerate(_SHIMS_TEXT.splitlines(), 1)
        if "deliverStopNow" in line
    ]
    assert len(hits) == 1, (
        f"expected exactly one line naming deliverStopNow in shims.cpp, "
        f"found {len(hits)}: {hits}"
    )
    assert hits[0][1].lstrip().startswith("//"), (
        f"the one surviving deliverStopNow line is code, not the "
        f"historical note this test expects: {hits[0]}"
    )
    assert "deliverStopNow" not in _SHIMS_STRIPPED, (
        "deliverStopNow still appears outside a comment -- the free "
        "function was supposed to be absorbed by Rig::softStop()."
    )
