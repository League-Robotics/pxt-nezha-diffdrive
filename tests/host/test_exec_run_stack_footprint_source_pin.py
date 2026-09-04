"""tests/host/test_exec_run_stack_footprint_source_pin.py -- pins
`WireHandler::execRun()`'s local-variable layout in
src/comms/wire_handler.cpp.

**Why a source-pin test for a file the host CAN compile.** Every other
source-pin test in this directory exists because its target file pulls
in `pxt.h` and simply cannot be built here at all. `wire_handler.cpp`
has no such problem -- it is exercised directly, through a ctypes shim,
by the existing wire-grammar host suite. But the property this test
pins (stack-frame layout: which locals are live before a given point in
the function) is invisible to that suite regardless: a host machine's
stack frames bear no relationship to the target ARM Cortex-M0's, and a
functional test can only ever observe RESULTS, never how much stack a
call used to produce them. Reordering `execRun()`'s locals changes
nothing a compiled test could detect either way -- only reading the
source proves the shape is still there.

**What this fixes.** `execRun()` used to be flagged for committing
`argv`/`result`/`sanitized`/`buf` (~750 bytes) to its own stack frame
regardless of whether the adapter refuses before any of them are ever
used. `argv` has no early-return point ahead of it (the adapter call
needs it as an argument) and stays a local. `result` moves to a
`WireHandler` member (`runResult_`) so its storage is never part of
this function's stack frame at all -- a guarantee that holds regardless
of what any particular compiler's stack-slot-sharing pass decides to
do, unlike simply reordering a local's declaration. `sanitized` and
`buf` were already declared, textually, after both of the early
returns they follow -- confirmed by this test rather than assumed.

Run with::

    uv run pytest tests/host/test_exec_run_stack_footprint_source_pin.py
"""
import pathlib
import re

# tests/host/test_exec_run_stack_footprint_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_WIRE_HANDLER_CPP = _REPO_ROOT / "src" / "comms" / "wire_handler.cpp"
_WIRE_HANDLER_H = _REPO_ROOT / "src" / "comms" / "wire_handler.h"


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    same technique test_staged_stop_source_pin.py uses, duplicated here
    per this directory's own precedent (each source-pin file is
    self-contained)."""
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
    assert m, f"{label}: no match for {signature_pattern!r} -- renamed or removed?"
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


_CPP_STRIPPED = _strip_comments(_WIRE_HANDLER_CPP.read_text())
_H_STRIPPED = _strip_comments(_WIRE_HANDLER_H.read_text())

_EXEC_RUN_SIG = (
    r"void\s+WireHandler::execRun\s*\(\s*char\*\*\s*fields\s*,\s*"
    r"size_t\s+fieldCount\s*,\s*uint32_t\s+id\s*,\s*uint8_t&\s*errCode\s*\)\s*\{"
)
_EXEC_RUN_BODY = _function_body(_CPP_STRIPPED, _EXEC_RUN_SIG, "WireHandler::execRun")


def test_result_is_a_member_not_an_exec_run_stack_local():
    """`result` must no longer be declared as a `char result[...]`
    stack array inside execRun() -- its storage belongs to the
    WireHandler instance (`runResult_`), never to this function's own
    frame, so it is off the stack regardless of what any compiler's
    stack-slot-sharing pass decides."""
    assert not re.search(r"\bchar\s+result\s*\[", _EXEC_RUN_BODY), (
        f"execRun(): still declares a local `char result[...]` array -- "
        f"this must be the runResult_ member instead:\n{_EXEC_RUN_BODY}"
    )
    assert re.search(r"\brunResult_\b", _EXEC_RUN_BODY), (
        f"execRun(): does not reference runResult_ at all -- has the "
        f"member relocation been reverted?\n{_EXEC_RUN_BODY}"
    )


def test_run_result_member_is_declared_on_wire_handler():
    """The member itself must actually exist on WireHandler, sized
    identically to the old local (kMaxRunResultBytes) -- the same
    pattern emitBuf_ already establishes for this class."""
    assert re.search(
        r"\bchar\s+runResult_\s*\[\s*kMaxRunResultBytes\s*\]", _H_STRIPPED
    ), "wire_handler.h: no `char runResult_[kMaxRunResultBytes]` member found"


def test_sanitized_and_buf_locals_are_declared_after_both_early_returns():
    """`sanitized` and `buf` must be declared AFTER both of execRun()'s
    early returns (`outcome != kOk` and `!hasResult`) -- textually,
    which is the only thing source-pinning can check; whether a given
    compiler's optimizer actually shrinks the pre-refusal frame because
    of it is a hardware question this test cannot answer."""
    first_return = _EXEC_RUN_BODY.find("if (outcome != Result::kOk) return;")
    assert first_return != -1, (
        f"execRun(): outcome != Result::kOk early return not found:\n{_EXEC_RUN_BODY}"
    )
    second_return = _EXEC_RUN_BODY.find("if (!hasResult) return;", first_return)
    assert second_return != -1, (
        f"execRun(): !hasResult early return not found after the first "
        f"one:\n{_EXEC_RUN_BODY}"
    )
    sanitized_decl = _EXEC_RUN_BODY.find("char sanitized[")
    assert sanitized_decl != -1, (
        f"execRun(): no `char sanitized[...]` declaration found:\n{_EXEC_RUN_BODY}"
    )
    buf_decl = _EXEC_RUN_BODY.find("char buf[")
    assert buf_decl != -1, (
        f"execRun(): no `char buf[...]` declaration found:\n{_EXEC_RUN_BODY}"
    )
    assert second_return < sanitized_decl, (
        "execRun(): `sanitized` is declared before the !hasResult early "
        f"return -- it must follow both returns:\n{_EXEC_RUN_BODY}"
    )
    assert second_return < buf_decl, (
        "execRun(): `buf` is declared before the !hasResult early "
        f"return -- it must follow both returns:\n{_EXEC_RUN_BODY}"
    )


def test_argv_stays_a_local_declared_before_the_adapter_call():
    """`argv` has no early-return point ahead of it -- the adapter call
    itself needs it as an argument -- so it must stay a plain local,
    declared before `adapter_.onRun(`."""
    argv_decl = _EXEC_RUN_BODY.find("const char* argv[kMaxRunArgs];")
    assert argv_decl != -1, (
        f"execRun(): no `const char* argv[kMaxRunArgs];` local found -- "
        f"has this been moved to a member unexpectedly?\n{_EXEC_RUN_BODY}"
    )
    call_site = _EXEC_RUN_BODY.find("adapter_.onRun(")
    assert call_site != -1, f"execRun(): no adapter_.onRun( call found:\n{_EXEC_RUN_BODY}"
    assert argv_decl < call_site, (
        f"execRun(): argv is declared after the onRun() call that needs "
        f"it:\n{_EXEC_RUN_BODY}"
    )
