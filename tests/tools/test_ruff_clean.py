"""tests/tools/test_ruff_clean.py -- the lint gate.

`pyproject.toml` has configured `ruff` since sprint 017 ticket 007
(`[tool.ruff.lint] select = ["F", "E9", "B"]` -- pyflakes, syntax
errors, bugbear; see that block's own comment for why the rule set is
narrow), and `ruff>=0.16` is a declared dev dependency. Until sprint 034
ticket 010 nothing ever RAN it: not a test, not a CI workflow. A
configured-but-unrun linter is worse than none, because the config
reads as a gate that is being enforced. It had accumulated ten findings
across four directories, most of them in `tests/dev/` and
`tests/system/` -- outside the two directories `uv run pytest` collects,
so no amount of running the test suite would ever have surfaced them.

**Why a test and not a CI workflow.** This repo has exactly one GitHub
workflow (`publish-extension.yml`, which publishes the generated
extension) and the developer signal here is `uv run pytest`. A gate
that only fires in CI would be a gate nobody sees until after they
push; a gate in the suite fires while the change is still in the
editor.

**Scope: `tools/` and `tests/`.** Not `src/` (C++), not the repo root
(the scratch and vendored trees under `pxt_modules/`, `.tmp/`,
`built/`). Those two directories are this project's whole Python
surface.

This file lints itself, which is the point: a lint gate that exempts
its own directory is one more place findings can accumulate unseen.

Run with::

    uv run pytest tests/tools/test_ruff_clean.py
"""

import pathlib
import shutil
import subprocess

import pytest

# tests/tools/test_ruff_clean.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The two directories that hold this project's Python. Relative, so the
#: paths ruff prints in a failure are the paths a developer types.
LINT_TARGETS = ("tools", "tests")


def _ruff_executable():
    """The concrete `ruff` binary, or None.

    Resolved from PATH (under `uv run pytest` the project venv's `bin/`
    is on it) and then from the venv beside this checkout, rather than
    shelling a bare `ruff` name and hoping: the same reasoning
    `test_typescript_typecheck.py` spells out for `tsc`. A linter
    resolved from somewhere else is a different linter, with a
    different rule set, reporting on this repo's code.
    """
    found = shutil.which("ruff")
    if found:
        return pathlib.Path(found)
    local = _REPO_ROOT / ".venv" / "bin" / "ruff"
    return local if local.is_file() else None


def test_ruff_check_is_clean():
    """`ruff check tools tests` must report no findings.

    The rule set is whatever `pyproject.toml` configures -- this test
    deliberately passes no `--select`, so tightening or loosening the
    rules is a one-line pyproject change and this gate follows it
    automatically rather than holding a second, drifting copy of the
    list.
    """
    ruff = _ruff_executable()
    if ruff is None:
        pytest.skip(
            "no `ruff` executable found on PATH or in .venv/bin -- run "
            "`uv sync` to install the dev dependency group (pyproject's "
            "`[dependency-groups] dev` declares `ruff>=0.16`), then "
            "re-run. `uv run pytest` puts it on PATH by itself, so "
            "seeing this skip means the suite was invoked outside the "
            "project environment."
        )
    result = subprocess.run(
        [str(ruff), "check", *LINT_TARGETS],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"ruff check {' '.join(LINT_TARGETS)} reported findings "
        f"(exit {result.returncode}). Fix them, or -- if a rule is "
        f"genuinely wrong for this project -- change the rule set in "
        f"pyproject.toml's [tool.ruff.lint] with a comment saying why, "
        f"the way B905 already is. Do not add a bare `# noqa`.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
