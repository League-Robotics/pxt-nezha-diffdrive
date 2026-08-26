"""tests/host/test_boot_banner_source_pin.py -- a text-level regression
pin for `test/test.ts`'s boot banner, following
`test_run_abort_source_pin.py`'s own precedent of regex-asserting on
`.ts` source text without compiling it (this repository's `tests/host/`
cannot compile or execute PXT/simulator code at all -- see
`tests/host/README.md`'s "What this does NOT cover yet").

**What this is NOT.** This cannot prove the icon or the scrolled
string actually appear on a real display, that `tools/make_deploy.py`'s
substitution lands correctly in a real scratch build, or that the
banner does not visibly stutter or delay anything at real boot. Those
need either a real build (`tools/make_deploy.py`, covered by
`tests/tools/test_make_deploy_boot_banner.py` for the substitution
half) or a live robot (bench confirmation). All this proves is that the
specific source-text shapes this feature introduced are actually
present in `test/test.ts`, in the right relative order -- cheap
insurance against someone silently reverting or reordering the banner
wiring, nothing more.

Run with::

    uv run pytest tests/host/test_boot_banner_source_pin.py
"""
import pathlib
import re

# tests/host/test_boot_banner_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TEST_TS = _REPO_ROOT / "test" / "test.ts"


def _source() -> str:
    return _TEST_TS.read_text(encoding="utf-8")


def test_boot_banner_shows_the_rollerskate_icon():
    src = _source()
    assert re.search(r'basic\.showIcon\(\s*IconNames\.Rollerskate\s*\)', src), (
        'test/test.ts must call basic.showIcon(IconNames.Rollerskate) '
        'somewhere -- the boot banner icon.'
    )


def test_boot_banner_scrolls_a_string_containing_the_version_placeholder():
    src = _source()
    assert re.search(r'basic\.showString\([^)]*BOOT_VERSION[^)]*\)', src), (
        'test/test.ts must scroll a string that includes BOOT_VERSION -- '
        'the injected version, not a hardcoded literal.'
    )


def test_boot_banner_icon_precedes_the_scroll():
    """Acceptance criterion's own ordering: the icon, THEN the scrolled
    version -- not the other way around."""
    src = _source()
    icon = re.search(r'basic\.showIcon\(\s*IconNames\.Rollerskate\s*\)', src)
    scroll = re.search(r'basic\.showString\([^)]*BOOT_VERSION[^)]*\)', src)
    assert icon and scroll
    assert icon.start() < scroll.start(), (
        'basic.showIcon(IconNames.Rollerskate) must appear before the '
        'BOOT_VERSION scroll, not after it'
    )


def test_boot_version_placeholder_declared_in_dd_rr_shape():
    """The checked-in placeholder itself must already be DD.RR-shaped
    (two digits, a dot, two digits) -- tools/make_deploy.py's injection
    substitutes the VALUE, not the shape, so an unsubstituted build
    still renders something plausible-looking rather than an empty or
    malformed string."""
    src = _source()
    assert re.search(r'const BOOT_VERSION = "\d\d\.\d\d"', src), (
        'expected a `const BOOT_VERSION = "DD.RR"`-shaped placeholder '
        'declaration in test/test.ts'
    )


def test_boot_robot_placeholder_declared():
    src = _source()
    assert re.search(r'const BOOT_ROBOT = "\w+"', src), (
        'expected a `const BOOT_ROBOT = "..."` placeholder declaration '
        'in test/test.ts'
    )


def test_boot_banner_call_is_not_under_src_blocks():
    """Structural guard for the sprint's own flagged interpretation:
    the banner belongs in test/test.ts, never in src/blocks/ -- a
    banner there would hijack the display of every student program
    that imports this extension. Scans every src/blocks/*.ts file
    (none should exist as of this ticket, but the guard should still
    hold if one is ever added) for the same call shapes this module
    pins in test.ts."""
    blocks_dir = _REPO_ROOT / "src" / "blocks"
    if not blocks_dir.exists():
        return
    for p in blocks_dir.glob("*.ts"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r'IconNames\.Rollerskate', text), (
            f'{p} references IconNames.Rollerskate -- the boot banner '
            'must live only in test/test.ts, not in the student-facing '
            'extension'
        )
        assert 'BOOT_VERSION' not in text and 'BOOT_ROBOT' not in text, (
            f'{p} references the boot banner placeholders -- these '
            'belong only in test/test.ts'
        )


def test_boot_banner_runs_after_every_run_dispatch_registration():
    """Ordering guard: basic.showIcon()/basic.showString() block this
    fiber while displaying. If the banner ran before the RUN: handlers
    are registered, a command arriving in that window would have
    nothing to dispatch to -- so the banner call must appear textually
    AFTER the last diffDrive.onRun(...) registration."""
    src = _source()
    registrations = list(re.finditer(r'diffDrive\.onRun\(', src))
    assert registrations, 'expected at least one diffDrive.onRun(...) call'
    last_registration = registrations[-1]
    banner = re.search(r'basic\.showIcon\(\s*IconNames\.Rollerskate\s*\)', src)
    assert banner
    assert banner.start() > last_registration.start(), (
        'the boot banner (basic.showIcon(...)) must be registered after '
        'the last diffDrive.onRun(...) handler, not before it -- see '
        "this file's own comment at the banner call site"
    )
