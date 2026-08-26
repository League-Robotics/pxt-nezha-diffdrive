"""tests/host/test_otos_product_id_single_source.py -- the OTOS
expected product id (0x5F) must be written exactly once, in
platform/otos_port.h's kExpectedProductId, and startWorldTracking()
(blocks/world.ts) must derive its answer from worldTrackingReady()
rather than re-deriving readiness from a second copy of the literal.

Before this fix, world.ts's startWorldTracking() independently compared
otosBegin()'s raw return value against a hand-typed `0x5F`, and
shims.cpp carried a comment restating the same literal. If
kExpectedProductId ever changed, OtosPort::connected() (and therefore
worldTrackingReady()) would track the new id correctly while
startWorldTracking() kept comparing against the stale one -- a direct
disagreement between two functions a caller has every reason to expect
agree, since one is documented as reading the other's readiness.

Text-based rather than compiled: blocks/world.ts is TypeScript, and
shims.cpp is CODAL-bound (src/DESIGN.md's own layering table), so
neither is inside tests/host/'s compile reach -- the same situation
test_wire_constants_drift.py's own module docstring explains for its
four pairs, and the same fix (read the relevant files as plain text).

Run with::

    uv run pytest tests/host/test_otos_product_id_single_source.py
"""

import pathlib
import re

# tests/host/test_otos_product_id_single_source.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"

# Vendored kernel -- upstream-owned, excluded the same way the
# archaeology-marker ratchet excludes it.
_EXCLUDED = {_SRC_DIR / "core" / "diffdrive.h", _SRC_DIR / "core" / "diffdrive.cpp"}

_PRODUCT_ID_RE = re.compile(r"0[xX]5[fF]\b")


def _find_product_id_literal_occurrences():
    """Every `0x5F`/`0x5f` occurrence anywhere under src/ (excluding the
    vendored kernel), as (path-relative-to-src, line-number, line-text)
    triples."""
    hits = []
    for path in sorted(_SRC_DIR.rglob("*")):
        if not path.is_file() or path in _EXCLUDED:
            continue
        if path.suffix not in (".h", ".hpp", ".cpp", ".ts"):
            continue
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _PRODUCT_ID_RE.search(line):
                hits.append((path.relative_to(_SRC_DIR), lineno, line.strip()))
    return hits


def test_otos_expected_product_id_literal_appears_exactly_once():
    """0x5F -- the OTOS chip's expected product id -- must be written
    exactly once anywhere under src/: platform/otos_port.h's
    kExpectedProductId. This is what world.ts's old `otosBegin() ==
    0x5F` comparison violated; this test fails the moment a second
    independent copy of the literal reappears anywhere in src/."""
    hits = _find_product_id_literal_occurrences()
    files = sorted({str(path) for path, _, _ in hits})
    assert files == ["platform/otos_port.h"], (
        f"0x5F (the OTOS expected product id) appears outside "
        f"platform/otos_port.h: {hits} -- kExpectedProductId must be "
        f"the only place this literal is written; a second copy "
        f"silently stops tracking a future change to the expected id."
    )
    assert len(hits) == 1, (
        f"0x5F appears {len(hits)} times inside platform/otos_port.h "
        f"itself, expected exactly one (kExpectedProductId): {hits}"
    )
    _, _, line = hits[0]
    assert "kExpectedProductId" in line, (
        f"The one 0x5F occurrence in platform/otos_port.h is not "
        f"kExpectedProductId's own declaration: {line!r}"
    )


def _start_world_tracking_body():
    text = (_SRC_DIR / "blocks" / "world.ts").read_text()
    match = re.search(
        r"export function startWorldTracking\(\): boolean \{(.*?)\n    \}",
        text,
        re.DOTALL,
    )
    assert match, "startWorldTracking() was not found in blocks/world.ts"
    return match.group(1)


def test_start_world_tracking_delegates_to_world_tracking_ready():
    """startWorldTracking() must call otosBegin() for its side effect
    and then return worldTrackingReady()'s own answer, rather than
    independently re-deriving readiness from otosBegin()'s return
    value. Delegating this way is what makes the two functions
    structurally unable to disagree, for any product id
    platform/otos_port.h ever expects -- the previous shape (a local
    `== 0x5F` comparison) could disagree with worldTrackingReady() the
    moment the expected id changed without a matching edit here."""
    body = _start_world_tracking_body()
    assert "otosBegin()" in body, (
        f"startWorldTracking() no longer calls otosBegin() to probe/"
        f"init the sensor: {body!r}"
    )
    assert re.search(r"return\s+worldTrackingReady\(\)", body), (
        f"startWorldTracking() does not return worldTrackingReady()'s "
        f"own answer: {body!r}"
    )
    assert not _PRODUCT_ID_RE.search(body), (
        f"startWorldTracking() still contains its own product-id "
        f"comparison: {body!r}"
    )
