"""tests/tools/test_publish_extension.py -- the extension publisher.

`tools/publish_extension.py` generates the student-facing extension
repository (League-Microbit/pxt-diff-drive) from this one. Two things
must hold, and each has a way of failing silently: the published tree
must be exactly pxt.json's `files` plus the `extension/` overlay --
nothing from tests/, tools/, docs/ or the CLASI process leaks, and the
overlay README replaces the engineering one -- and the publish step
must never move a release tag, since MakeCode pins projects to tags.
The publish path is exercised for real against a local bare repo, so a
regression in the clone/wipe/commit/tag sequence fails here rather
than on the first push to GitHub.

Run with::

    uv run pytest tests/tools/test_publish_extension.py
"""

import json
import pathlib
import subprocess
import sys

import pytest

# tests/tools/test_publish_extension.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import publish_extension as pe  # noqa: E402  (path must be set up first)

_SOURCE = ("0123456789abcdef0123456789abcdef01234567", "subject line", False)


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True,
                          text=True, capture_output=True).stdout


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    _git("init", "-q", "--bare", "--initial-branch=main", str(remote),
         cwd=tmp_path)
    return str(remote)


def _clone(remote, dst):
    _git("clone", "-q", remote, str(dst), cwd=dst.parent)
    return dst


# --- manifest rewrite -------------------------------------------------------

def test_published_manifest_rewrites_test_files_and_marks_public():
    src = {"name": "n", "version": "1.2.3", "description": "d",
           "license": "MIT", "dependencies": {"core": "*"},
           "files": ["README.md", "src/a.ts"],
           "testFiles": ["test/test.ts", "test/testrig.ts"],
           "supportedTargets": ["microbit"]}
    out = pe.published_manifest(src, ["test.ts"])
    assert out["testFiles"] == ["test.ts"]
    assert out["public"] is True
    assert out["files"] == src["files"]
    keys = list(out)
    assert keys[:5] == ["name", "version", "description", "license", "public"]
    assert keys.index("testFiles") == keys.index("files") + 1
    assert keys[-1] == "supportedTargets"
    assert src["testFiles"] == ["test/test.ts", "test/testrig.ts"]  # untouched


def test_published_manifest_without_license_still_marks_public():
    out = pe.published_manifest({"name": "n", "files": []}, [])
    assert out["public"] is True and out["testFiles"] == []


# --- assembly ---------------------------------------------------------------

def test_assemble_ships_manifest_files_overlay_and_nothing_else(tmp_path):
    out = tmp_path / "ext"
    written = pe.assemble(out)
    manifest = pe.load_manifest()

    for rel in manifest["files"]:
        assert (out / rel).is_file(), rel
    # The overlay README replaces the engineering README `files` lists.
    assert (out / "README.md").read_text() == \
        (pe.OVERLAY_DIR / "README.md").read_text()
    assert (out / "README.md").read_text() != \
        (pe.REPO / "README.md").read_text()
    for rel in ("LICENSE", "tsconfig.json", ".gitignore", "test.ts",
                ".github/workflows/makecode.yml"):
        assert (out / rel).is_file(), rel
    # Nothing that is not the extension.
    assert not list(out.rglob("DESIGN.md"))
    for stray in ("tests", "tools", "docs", "clasi", ".clasi", ".claude",
                  "test", "captures", "reports", "pyproject.toml"):
        assert not (out / stray).exists(), stray

    published = json.loads((out / "pxt.json").read_text())
    assert published["testFiles"] == ["test.ts"]
    assert published["public"] is True
    for key in ("name", "version", "description", "license",
                "dependencies", "files", "supportedTargets"):
        assert published[key] == manifest[key], key

    on_disk = sorted(str(p.relative_to(out)) for p in out.rglob("*")
                     if p.is_file())
    assert on_disk == written


def test_assemble_refuses_non_empty_target(tmp_path):
    (tmp_path / "stray").write_text("")
    with pytest.raises(SystemExit):
        pe.assemble(tmp_path)


def test_assemble_refuses_overlay_without_readme(tmp_path):
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    with pytest.raises(SystemExit, match="README.md is missing"):
        pe.assemble(tmp_path / "out", overlay=overlay)


# --- publish, against a local bare repo -------------------------------------

def test_publish_creates_branch_commit_and_tag_then_is_idempotent(tmp_path):
    remote = _bare_remote(tmp_path)
    tree = tmp_path / "tree"
    pe.assemble(tree)

    r1 = pe.publish(tree, remote, source=_SOURCE)
    assert r1["changed"] and not r1["tag_existed"]
    assert r1["branch"] == "main"

    clone = _clone(remote, tmp_path / "clone1")
    assert (clone / "pxt.json").is_file()
    assert (clone / "src/blocks/motion.ts").is_file()
    assert (clone / ".github/workflows/makecode.yml").is_file()
    assert _git("tag", cwd=clone).split() == [r1["tag"]]
    assert _git("rev-parse", "HEAD", cwd=clone).strip() == r1["commit"]
    log = _git("log", "-1", "--format=%an%n%ae%n%s", cwd=clone).splitlines()
    assert log == [pe.BOT_NAME, pe.BOT_EMAIL,
                   f"Sync from {pe.SOURCE_REPO}@0123456789ab"]

    # Same tree again: nothing to commit, tag untouched.
    r2 = pe.publish(tree, remote, source=_SOURCE)
    assert not r2["changed"] and r2["tag_existed"]
    assert r2["commit"] == r1["commit"]


def test_publish_replaces_stale_files_and_never_moves_a_tag(tmp_path):
    remote = _bare_remote(tmp_path)
    tree = tmp_path / "tree"
    pe.assemble(tree)
    r1 = pe.publish(tree, remote, source=_SOURCE)

    # A content change without a version bump.
    (tree / "README.md").write_text("# changed\n")
    (tree / "src/blocks/stop.ts").unlink()
    dirty = (_SOURCE[0], "second subject", True)
    r2 = pe.publish(tree, remote, source=dirty)
    assert r2["changed"] and r2["tag_existed"]
    assert r2["commit"] != r1["commit"]

    clone = _clone(remote, tmp_path / "clone")
    assert (clone / "README.md").read_text() == "# changed\n"
    assert not (clone / "src/blocks/stop.ts").exists()
    assert _git("log", "-1", "--format=%s", cwd=clone).strip() == \
        f"Sync from {pe.SOURCE_REPO}@0123456789ab-dirty"
    # The tag still points at the first publish.
    assert _git("rev-list", "-n1", r1["tag"], cwd=clone).strip() == r1["commit"]
    summary = pe.summarize(r2)
    assert "already exists" in summary and "bump `version`" in summary


def test_publish_dry_run_pushes_nothing(tmp_path):
    remote = _bare_remote(tmp_path)
    tree = tmp_path / "tree"
    pe.assemble(tree)
    r = pe.publish(tree, remote, source=_SOURCE, dry_run=True)
    assert r["changed"] and not r["tag_existed"]
    assert _git("ls-remote", "--heads", "--tags", remote,
                cwd=tmp_path).strip() == ""
    assert "dry run" in pe.summarize(r)


def test_main_refuses_to_publish_a_dirty_source_tree(tmp_path, monkeypatch):
    # The first hand-run publish (2026-08-29) shipped another session's
    # uncommitted edits under v1.0.10; --publish now refuses unless the
    # inputs match HEAD.
    remote = _bare_remote(tmp_path)
    monkeypatch.setattr(pe, "source_revision",
                        lambda repo=pe.REPO: ("a" * 40, "wip", True))
    with pytest.raises(SystemExit, match="refusing to publish"):
        pe.main(["--publish", remote])
    assert _git("ls-remote", "--heads", "--tags", remote,
                cwd=tmp_path).strip() == ""
    # --dry-run never pushes, so it needs no guard; --allow-dirty is the
    # explicit override and labels the commit as dirty.
    pe.main(["--publish", remote, "--dry-run"])
    assert _git("ls-remote", "--heads", remote, cwd=tmp_path).strip() == ""
    pe.main(["--publish", remote, "--allow-dirty"])
    clone = _clone(remote, tmp_path / "clone")
    assert _git("log", "-1", "--format=%s", cwd=clone).strip().endswith("-dirty")


# --- the version comes from config, never from pxt.json or thin air --------

def test_config_version_is_read_from_dotconfig_yaml():
    assert pe.config_version() == pe.load_manifest()["version"]


@pytest.mark.parametrize("manifest_version,version,expected", [
    ("1.20260829.1", "1.20260829.1", 0),
    ("1.0.11", "1.20260829.1", 1),          # pxt.json edited by hand
    ("0.20260829.2", "0.20260829.2", 1),    # in sync, but major 0
    # Both faults at once: pxt.json drifted AND the config version has a
    # major MakeCode would never serve. The major is checked on the
    # CONFIG version -- the one that would actually be released.
    ("1.0.11", "0.1.0", 2),
])
def test_check_version_catches_drift_and_unreleasable_majors(
        manifest_version, version, expected):
    assert len(pe.check_version(manifest_version, version)) == expected


def test_a_major_zero_version_is_refused_because_makecode_would_not_serve_it():
    """MEASURED: the extension repo carries v1.0.11, and semver sorts
    v0.20260829.2 BELOW it, so such a release reaches nobody. This is
    the trap commit 07e1e87 named; the failure is silent, which is why
    it is a hard refusal rather than a warning."""
    problems = pe.check_version("0.20260829.2", "0.20260829.2")
    assert len(problems) == 1
    assert "reach nobody" in problems[0]
    assert "--major 1" in problems[0]


def test_sync_version_rewrites_only_the_version_and_keeps_formatting(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "dotconfig.yaml").write_text(
        "# comment\nversion: 1.20260830.7\n")
    original = ('{\n    "name": "nezha-diffdrive",\n'
                '    "version": "1.0.11",\n'
                '    "description": "has \\"quotes\\" in it",\n'
                '    "files": ["README.md"]\n}\n')
    (repo / "pxt.json").write_text(original)

    assert pe.sync_version(repo) == ("1.0.11", "1.20260830.7")
    after = (repo / "pxt.json").read_text()
    assert json.loads(after)["version"] == "1.20260830.7"
    # Only the version line changed -- formatting, key order and the
    # description's escaped quotes all survive.
    assert after == original.replace('"1.0.11"', '"1.20260830.7"')
    assert pe.sync_version(repo) == ("1.20260830.7", "1.20260830.7")


def test_assemble_refuses_when_pxt_json_and_config_disagree(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(pe, "config_version",
                        lambda repo=pe.REPO: "9.9.9-not-the-manifest")
    with pytest.raises(SystemExit, match="single source of truth"):
        pe.assemble(tmp_path / "out")
