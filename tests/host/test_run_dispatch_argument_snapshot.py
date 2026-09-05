"""tests/host/test_run_dispatch_argument_snapshot.py -- sprint 032
ticket 004 (BT-02, `run-dispatch-contract-argument-snapshot-and-fiber-
doc.md`): `src/blocks/run.ts`'s `runParts` used to be a bare
module-level `let`, reassigned wholesale by `wireRunDispatch()`'s
registered callback on every dispatch. `src/comms/protocol.h`
dispatches the `abort`/`clearestop` bypass reentrantly, NESTED inside
whatever job is currently ticking, on the SAME protocol fiber (sprint
028 collapsed RUN handling onto that one fiber). Nothing stopped a
nested dispatch's `runParts = text.split(":")` from overwriting the
outer command's own arguments for the rest of the outer handler's
execution -- every handler in this package happens to read its
arguments only at entry, before any reentrancy point, which is exactly
why nothing had broken yet, but nothing enforced that convention
either.

The fix replaces the bare variable with a push/pop STACK
(`runPartsStack: string[][]`): `wireRunDispatch()`'s callback pushes
its own newly-split `parts` array before invoking any handler and pops
it in a `finally` once every handler/any-handler has run;
`runArgText()`/`runArgCount()` read the TOP of the stack rather than a
bare module variable.

**What this pins, and how -- two layers.**

1. The push/pop stack's real, dynamic behavior IS EXECUTED here, not
   just pattern-matched -- following `test_run_arg_or_contract.py`'s
   precedent (extract the real source, compile it with the project's
   own pinned `node_modules/.bin/tsc`, run it under `node`). The
   dispatch core (`runPartsStack`'s declaration through `onRun`/
   `onRunCommand`) plus `runArg`/`runArgText`/`runArgCount` are
   extracted VERBATIM from `run.ts`, pasted into a throwaway harness
   alongside stub bodies for the two ambient shim functions this file
   calls (`runCommandText()`, `_registerRunDispatch()` -- normally
   `sim.ts`/native code), and driven through a scripted NESTED
   dispatch: an "outer" handler reads its own arguments at entry,
   synchronously triggers a second dispatch (standing in for
   protocol.h's abort/clearestop bypass landing reentrantly on this
   same fiber while the outer handler is still on the call stack), and
   then re-reads its own arguments again after the nested dispatch
   returns. The harness asserts the outer handler's arguments are
   identical before and after -- the property this ticket exists to
   guarantee.

   **What this does NOT cover.** This harness is real TypeScript
   executed under `node`, but it is still a host-side STAND-IN for
   `_registerRunDispatch`/`runCommandText` (normally backed by
   `sim.ts`'s browser-simulator body or native `shims.cpp`/
   `protocol.cpp` code this file cannot compile or execute --
   `tests/host/`'s own limitation, stated in
   `test_run_abort_source_pin.py`'s module docstring and unchanged
   here). It proves the push/pop stack's OWN shape does what it
   claims when driven directly; it cannot prove `protocol.cpp` actually
   dispatches `abort`/`clearestop` reentrantly on real hardware, or
   that a real nested dispatch is what this harness models -- that is
   `protocol.h`/`protocol.cpp`'s own documented contract (out of scope
   for this ticket) and ultimately a robot's job to confirm.

2. The three factually wrong "own fiber"/MessageBus comments this
   ticket also corrects (`run.ts`'s `runPartsStack` declaration
   comment, `onRun()`'s JSDoc, and `test/test.ts`'s `abort` handler
   preamble) are pinned by source-text regex: the OLD wrong phrasing
   must be gone, and specific NEW correct phrasing must be present --
   not just "some comment changed somewhere".

Run with::

    uv run pytest tests/host/test_run_dispatch_argument_snapshot.py
"""
import pathlib
import re
import subprocess

import pytest

# tests/host/test_run_dispatch_argument_snapshot.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_RUN_TS = _REPO_ROOT / "src" / "blocks" / "run.ts"
_TEST_TS = _REPO_ROOT / "test" / "test.ts"
_TSC = _REPO_ROOT / "node_modules" / ".bin" / "tsc"


def _run_ts_source() -> str:
    return _RUN_TS.read_text(encoding="utf-8")


def _test_ts_source() -> str:
    return _TEST_TS.read_text(encoding="utf-8")


def _find_balanced_close(text: str, open_brace_idx: int) -> int:
    """Index just past the '}' matching the '{' at open_brace_idx."""
    depth = 0
    i = open_brace_idx
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced braces starting at %d" % open_brace_idx)


def _find_matching_paren_close(text: str, open_paren_idx: int) -> int:
    """Index just past the ')' matching the '(' at open_paren_idx --
    needed because onRun()'s own parameter list
    (`handler: (arg: number) => void`) nests a paren inside the outer
    one, which a naive `[^)]*\\)` regex truncates at the WRONG `)`."""
    depth = 0
    i = open_paren_idx
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced parens starting at %d" % open_paren_idx)


def _function_source(name: str, exported: bool = True) -> str:
    """Verbatim `[export ]function <name>(...) {...}` text from
    run.ts, brace- and paren-balanced so neither a nested `if { }` nor
    a parameter list with its own `(...)` (onRun's `handler` param)
    truncates it early."""
    src = _run_ts_source()
    prefix = r"export function" if exported else r"function"
    m = re.search(r"%s %s\(" % (prefix, re.escape(name)), src)
    assert m, "%s%s() not found in run.ts" % (
        "export " if exported else "", name)
    paren_open_idx = m.end() - 1
    paren_close_idx = _find_matching_paren_close(src, paren_open_idx)
    brace_idx = src.index("{", paren_close_idx)
    close_idx = _find_balanced_close(src, brace_idx)
    return src[m.start():close_idx]


def _with_preceding_comment_block(src: str, source_text: str) -> str:
    """Prepend the contiguous `//`-comment (or `/** ... */`) block
    immediately above `source_text`'s own position in `src` -- a
    doc/preamble comment sits OUTSIDE the brace-balanced span
    `_function_source()` returns, so callers that need to inspect a
    function's own preceding comment (not just its body) walk back to
    it here."""
    start_idx = src.index(source_text)
    line_start = src.rfind("\n", 0, start_idx) + 1
    lines_before = src[:line_start].splitlines()
    comment_lines = []
    for line in reversed(lines_before):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or \
                stripped.startswith("/**") or stripped == "*/":
            comment_lines.append(line)
        else:
            break
    comment_lines.reverse()
    if not comment_lines:
        return source_text
    return "\n".join(comment_lines) + "\n" + source_text


def _extract_dispatch_core() -> str:
    """Everything from `runPartsStack`'s own declaration through the
    end of `onRunCommand()` -- the state block, `ensureRunState()`,
    `currentRunParts()`, `wireRunDispatch()`, `onRun()` and
    `onRunCommand()` -- verbatim, so the harness below exercises the
    REAL push/pop logic rather than a reimplementation of it."""
    src = _run_ts_source()
    start_idx = src.index("let runPartsStack: string[][]")
    assert start_idx >= 0, "runPartsStack declaration not found in run.ts"
    m = re.search(r"export function onRunCommand\(", src)
    assert m, "onRunCommand() not found in run.ts"
    brace_idx = src.index("{", m.end())
    close_idx = _find_balanced_close(src, brace_idx)
    return src[start_idx:close_idx]


# ---------------------------------------------------------------------------
# The real thing: compile the extracted dispatch core (+ runArg family)
# with the project's own tsc and execute a scripted nested dispatch
# under node.
# ---------------------------------------------------------------------------

_HARNESS_TEMPLATE = """
// Minimal ambient declarations for the two node globals this harness
// uses -- same reasoning as test_run_arg_or_contract.py's own
// harness: a bare script compile wants neither this project's
// PXT/browser-simulator @types nor node's own, so it declares just
// enough by hand.
declare const console: { log(msg: string): void; error(msg: string): void };
declare const process: { exitCode: number; exit(code: number): void };

// ---- stand-ins for the two ambient shim functions run.ts calls
// (normally sim.ts's browser body or native shims.cpp/protocol.cpp,
// neither of which tests/host/ can compile or execute) ----
let _registeredCallback: (() => void) | undefined = undefined;
function _registerRunDispatch(cb: () => void): void {
    _registeredCallback = cb;
}
let _commandText: string = "";
function runCommandText(): string {
    return _commandText;
}

// ---- the REAL dispatch core + runArg family, extracted verbatim ----
%(dispatch_core)s

%(run_arg_text_source)s

%(run_arg_count_source)s

%(run_arg_source)s

// ---- scripted nested dispatch ----
let failures = 0;
function check(condition: boolean, label: string): void {
    if (!condition) {
        console.error("FAIL " + label);
        failures++;
    }
}

let outerEntryArg0 = "";
let outerEntryArg1 = "";
let outerEntryCount = 0;
let outerAfterNestedArg0 = "";
let outerAfterNestedArg1 = "";
let outerAfterNestedCount = 0;
let nestedRan = false;
let nestedSawItsOwnArg = "";

onRun("outer", function (arg: number) {
    outerEntryArg0 = runArgText(0);
    outerEntryArg1 = runArgText(1);
    outerEntryCount = runArgCount();

    // Simulate protocol.h's abort/clearestop bypass landing
    // REENTRANTLY on this same fiber while "outer" is still
    // executing: dispatch a second command, synchronously, before
    // "outer" returns.
    const savedCommandText = _commandText;
    _commandText = "nested:99";
    if (_registeredCallback) _registeredCallback();
    _commandText = savedCommandText;

    // After the nested dispatch has returned, this handler's OWN
    // arguments must read back exactly as they did at entry -- the
    // whole point of the push/pop stack.
    outerAfterNestedArg0 = runArgText(0);
    outerAfterNestedArg1 = runArgText(1);
    outerAfterNestedCount = runArgCount();
});

onRun("nested", function (arg: number) {
    nestedRan = true;
    nestedSawItsOwnArg = runArgText(0);
});

// Top-level dispatch: protocol.cpp's dispatchJob() invoking the
// registered callback once for a dequeued RUN:outer:7:8.
_commandText = "outer:7:8";
if (_registeredCallback) _registeredCallback();

check(nestedRan, "the nested dispatch must actually have run");
check(nestedSawItsOwnArg === "99",
    "the nested handler must see its OWN argument (99), got " + nestedSawItsOwnArg);
check(outerEntryArg0 === "7",
    "outer must see its own arg 0 (7) at entry, got " + outerEntryArg0);
check(outerEntryArg1 === "8",
    "outer must see its own arg 1 (8) at entry, got " + outerEntryArg1);
check(outerEntryCount === 2,
    "outer must see argCount 2 at entry, got " + outerEntryCount);
check(outerAfterNestedArg0 === "7",
    "outer's arg 0 must still be 7 AFTER the nested dispatch returns " +
    "(BT-02: this is exactly what the push/pop stack must prevent from " +
    "regressing), got " + outerAfterNestedArg0);
check(outerAfterNestedArg1 === "8",
    "outer's arg 1 must still be 8 AFTER the nested dispatch returns, " +
    "got " + outerAfterNestedArg1);
check(outerAfterNestedCount === 2,
    "outer's argCount must still be 2 AFTER the nested dispatch returns, " +
    "got " + outerAfterNestedCount);

// A dispatch after the stack has unwound back to empty must not see a
// stale frame left behind by a mispaired push/pop.
check(runArgCount() === 0,
    "runArgCount() outside any dispatch (stack empty) must be 0, got " +
    runArgCount());
check(runArgText(0) === "",
    "runArgText() outside any dispatch (stack empty) must be \\"\\", got " +
    JSON.stringify(runArgText(0)));

if (failures > 0) {
    console.log("FAIL: " + failures + " check(s) failed");
    process.exit(1);
} else {
    console.log("PASS");
    process.exit(0);
}
"""


@pytest.fixture(scope="module")
def _harness_result(tmp_path_factory):
    assert _TSC.is_file(), (
        f"{_TSC} does not exist -- run `npm install` first (see "
        f"test_typescript_typecheck.py's header comment: this "
        f"deliberately never falls back to `npx tsc`)"
    )
    dispatch_core = _extract_dispatch_core()
    # `export`/`declare` are meaningless (and one is a parse error)
    # outside a module/namespace -- strip leading `export ` so the
    # harness compiles as a plain script, without touching any body.
    dispatch_core = re.sub(r"^(\s*)export function", r"\1function",
                            dispatch_core, flags=re.MULTILINE)
    run_arg_text_source = _function_source("runArgText").replace(
        "export function runArgText", "function runArgText", 1)
    run_arg_count_source = _function_source("runArgCount").replace(
        "export function runArgCount", "function runArgCount", 1)
    run_arg_source = _function_source("runArg").replace(
        "export function runArg", "function runArg", 1)

    harness_ts = _HARNESS_TEMPLATE % {
        "dispatch_core": dispatch_core,
        "run_arg_text_source": run_arg_text_source,
        "run_arg_count_source": run_arg_count_source,
        "run_arg_source": run_arg_source,
    }

    tmp_dir = tmp_path_factory.mktemp("run_dispatch_snapshot_harness")
    ts_path = tmp_dir / "harness.ts"
    js_path = tmp_dir / "harness.js"
    tsconfig_path = tmp_dir / "tsconfig.json"
    ts_path.write_text(harness_ts, encoding="utf-8")
    # `types: []` (a real tsconfig.json, not the CLI --types flag)
    # keeps this project's own node_modules/@types/* (baked in for the
    # PXT simulator target) from being auto-included and colliding in
    # a bare script compile that wants neither -- same reasoning as
    # test_run_arg_or_contract.py's own harness. `strict: false`
    # matches this repo's OWN root tsconfig.json (PXT's device target
    # never enables strict mode) rather than imposing a stricter check
    # here than what actually builds -- run.ts's own
    # `currentRunParts(): string[]` returning `undefined` when the
    # stack is empty is accepted under the real build for the same
    # reason.
    tsconfig_path.write_text(
        '{"compilerOptions": {"target": "es2017", "lib": ["es2017"], '
        '"types": [], "strict": false, "outFile": "%s"}, '
        '"files": ["%s"]}' % (js_path.name, ts_path.name),
        encoding="utf-8",
    )

    compile_result = subprocess.run(
        [str(_TSC), "-p", str(tsconfig_path)],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert compile_result.returncode == 0, (
        f"harness failed to compile -- this means the EXTRACTED "
        f"dispatch core is not valid standalone TypeScript, which "
        f"should be impossible if src/blocks/run.ts itself type-checks "
        f"(see test_typescript_typecheck.py):\n"
        f"stdout:\n{compile_result.stdout}\nstderr:\n{compile_result.stderr}\n"
        f"---- generated harness ----\n{harness_ts}"
    )

    run_result = subprocess.run(
        ["node", str(js_path)], capture_output=True, text=True,
    )
    return run_result


def test_nested_dispatch_leaves_outer_arguments_intact(_harness_result):
    """Runs the REAL extracted push/pop stack (compiled and executed,
    not just pattern-matched): a nested dispatch (standing in for
    protocol.h's abort/clearestop bypass) landing reentrantly on the
    same fiber while an outer handler is still executing must not
    corrupt that outer handler's own runArg()/runArgText()/
    runArgCount() results once the nested dispatch returns."""
    assert _harness_result.returncode == 0, (
        f"nested-dispatch argument-snapshot check failed:\n"
        f"stdout:\n{_harness_result.stdout}\nstderr:\n{_harness_result.stderr}"
    )
    assert "PASS" in _harness_result.stdout


# ---------------------------------------------------------------------------
# run.ts: the push/pop stack's own shape (source-pin, cheap and
# specific -- names the exact mechanism the executed test above
# exercises dynamically).
# ---------------------------------------------------------------------------


def test_run_parts_is_a_stack_not_a_bare_variable():
    src = _run_ts_source()
    assert "let runPartsStack: string[][]" in src, (
        "run.ts must declare runPartsStack as a stack of frames "
        "(string[][]), not a bare string[] runParts"
    )
    assert "let runParts: string[]" not in src, (
        "the old bare module-level `runParts: string[]` must be gone"
    )
    assert re.search(r"\bruns*Parts\s*=\s*text\.split", src) is None, (
        "no code may reassign a bare `runParts` variable wholesale -- "
        "the whole point of this ticket is that reassignment is what "
        "let a nested dispatch overwrite the outer command's arguments"
    )


def test_wire_run_dispatch_pushes_and_pops_in_a_finally():
    body = _function_source("wireRunDispatch", exported=False)
    assert "runPartsStack.push(parts)" in body, (
        "wireRunDispatch()'s callback must push the newly-split parts "
        "array onto the stack before invoking any handler"
    )
    assert re.search(r"finally\s*\{[^}]*runPartsStack\.pop\(\)", body), (
        "wireRunDispatch()'s callback must pop its frame in a `finally` "
        "so the stack unwinds correctly even if a handler throws"
    )
    push_idx = body.index("runPartsStack.push(parts)")
    pop_idx = body.index("runPartsStack.pop()")
    assert push_idx < pop_idx, "the push must precede the pop"


def test_run_arg_text_and_count_read_the_stack_top_not_a_bare_variable():
    text_body = _function_source("runArgText")
    count_body = _function_source("runArgCount")
    for name, body in (("runArgText", text_body), ("runArgCount", count_body)):
        assert "currentRunParts()" in body, (
            "%s() must read the stack's top frame via currentRunParts(), "
            "not a bare module-level runParts variable" % name
        )
        assert "runParts" not in body.replace("runPartsStack", ""), (
            "%s() must not reference a bare `runParts` variable" % name
        )


def test_on_run_signature_is_unchanged():
    """The Design Rationale explicitly rejects a signature change --
    this is a purely internal mechanism change."""
    src = _run_ts_source()
    assert re.search(
        r"export function onRun\(name: string, "
        r"handler: \(arg: number\) => void\): void \{",
        src,
    ), "onRun()'s public signature must be unchanged by this ticket"


# ---------------------------------------------------------------------------
# The three corrected comments: OLD wrong phrasing gone, NEW correct
# phrasing present -- not just "some comment changed somewhere".
# ---------------------------------------------------------------------------


def test_run_parts_declaration_comment_no_longer_blames_messagebus():
    src = _run_ts_source()
    assert "MessageBus delivers these events one at a time" not in src, (
        "runPartsStack's declaration comment must no longer claim "
        "MessageBus serializes RUN dispatch -- RUN commands have not "
        "been MessageBus events since sprint 028"
    )
    assert "A stack, not a bare variable, because RUN dispatch nests" in src, (
        "runPartsStack's declaration comment must explain the actual "
        "safety mechanism (the push/pop stack), not the old wrong "
        "MessageBus reasoning"
    )


def test_on_run_jsdoc_no_longer_claims_its_own_fiber():
    src = _run_ts_source()
    assert (
        "their own fiber, so a long test (a full tour) doesn't block the"
        not in src
    ), "the old wrong onRun() fiber claim text must be gone"
    assert "NESTED, directly on the wire's own (protocol) fiber" in src, (
        "onRun()'s JSDoc must state that handlers run nested on the "
        "wire's own (protocol) fiber"
    )
    assert re.search(r"stalls\s+(?:\*\s+)?PING/STATUS/ESTOP", src), (
        "onRun()'s JSDoc must say that a blocking handler body stalls "
        "the wire (PING/STATUS/ESTOP), matching ticket 002's finding"
    )


def test_abort_preamble_in_test_ts_no_longer_says_its_own_fiber():
    src = _test_ts_source()
    assert "mid-execution on its own fiber" not in src, (
        "test.ts's RUN:abort preamble must no longer say the running "
        "tour's handler is on its own fiber -- it is nested, reentrant "
        "dispatch on the SAME protocol fiber"
    )
    assert "dispatches abort/clearestop reentrantly, NESTED inside" in src, (
        "test.ts's RUN:abort preamble must describe the actual "
        "mechanism: reentrant, nested dispatch on one fiber"
    )


def test_no_other_stale_fiber_claim_remains_in_run_ts_or_test_ts():
    """Re-grep both files for the three marker phrases and confirm
    every SURVIVING hit describes something else accurately --
    protocol.h/.cpp's own (correct, out-of-scope) comments are not
    read here at all, only run.ts and test.ts."""
    run_src = _run_ts_source()
    test_src = _test_ts_source()

    # test.ts: no hit of any of the three phrases should remain at all.
    for phrase in ("own fiber", "MessageBus", "forked"):
        assert phrase not in test_src, (
            "test.ts still contains the stale phrase %r" % phrase
        )

    # run.ts: "MessageBus"/"forked"/"own fiber" may still appear, but
    # ONLY in three known-accurate sites: runPartsStack's own corrected
    # declaration comment (explains the new stack mechanism in terms
    # of what it replaces), wireRunDispatch()'s own comment (correctly
    # describes what does NOT happen anymore -- contrasting today's
    # direct-call dispatch with the old, deleted MessageBus/forked-
    # fiber scheme), and onRun()'s corrected JSDoc (which explicitly
    # negates the old model: "not forked to a fiber of their own").
    decl_start = run_src.index("// Argument-snapshot STACK")
    decl_end = run_src.index("let runPartsStack: string[][]") + len(
        "let runPartsStack: string[][]")
    run_parts_stack_decl = run_src[decl_start:decl_end]
    wire_dispatch_source = _function_source("wireRunDispatch", exported=False)
    wire_dispatch_comment = _with_preceding_comment_block(
        run_src, wire_dispatch_source)
    on_run_doc_and_body = _with_preceding_comment_block(
        run_src, _function_source("onRun"))
    allowed_sources = "\n".join(
        (run_parts_stack_decl, wire_dispatch_comment, on_run_doc_and_body))

    remaining_lines = [
        line.strip() for line in run_src.splitlines()
        if re.search(r"own fiber|MessageBus|forked", line)
    ]
    allowed_lines = {line.strip() for line in allowed_sources.splitlines()}
    for line in remaining_lines:
        assert line in allowed_lines, (
            "run.ts has a stale fiber/MessageBus/forked claim outside "
            "the three known-accurate sites (runPartsStack's own "
            "declaration comment, wireRunDispatch()'s own comment, "
            "onRun()'s corrected JSDoc): %r" % line
        )
