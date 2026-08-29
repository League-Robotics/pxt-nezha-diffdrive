#!/usr/bin/env python3
"""tools/publish_extension.py -- assemble and publish the MakeCode extension.

This repo is a whole engineering workspace: host tests, bench tools,
CLASI process artifacts, design docs, capture data. The MakeCode
extension students install is a small subset of it, and it is
published to its OWN repository,
https://github.com/League-Microbit/pxt-diff-drive, which holds nothing
but what an extension needs. That repository is generated, never
edited: this script builds it from two sources of truth and pushes the
result.

  1. `pxt.json`'s `files` list -- exactly what PXT ships to a consuming
     project. Every entry is copied at the same relative path, so the
     published tree is by construction the one PXT builds from here.
  2. `extension/` -- an overlay of files that exist ONLY in the
     published repo: its README (student-facing; it REPLACES this
     repo's engineering README, which `files` also lists), LICENSE, a
     small sample `test.ts`, tsconfig, .gitignore and the extension
     repo's own build-check workflow. Overlay `*.ts` files at the root
     become the published `testFiles`. `extension/DESIGN.md` documents
     the overlay for this repo's readers and is not copied.

The published `pxt.json` is this repo's with `testFiles` rewritten to
the overlay's and `"public": true` added; everything else (name,
version, dependencies, yotta config, disablesVariants) passes through
unchanged, so a version bump here is a release there.

Publishing (--publish) clones the target, replaces its whole tree with
the assembled one, commits if anything changed, pushes, and pushes a
`v<version>` tag if that tag does not exist yet. Tags are NEVER moved:
MakeCode pins a project to the tag it was added at and caches the
compiled native code by content hash under it, so a re-published
v1.0.10 with different contents would be two different extensions
wearing one name. A content change without a version bump is pushed
to the branch (so the repo tracks master) and reported as exactly that
in the summary.

Run by `.github/workflows/publish-extension.yml` on every push to
master, with a write deploy key for the target repo in
GIT_SSH_COMMAND; runs identically by hand:

    python3 tools/publish_extension.py                   # list the tree
    python3 tools/publish_extension.py --out DIR         # assemble only
    python3 tools/publish_extension.py --publish         # default remote
    python3 tools/publish_extension.py --publish --dry-run

Stdlib only, on purpose: it runs on a bare GitHub runner with no
`uv sync`.
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
OVERLAY_DIR = REPO / "extension"
# Overlay files that document the overlay itself, for THIS repo's
# readers -- never published.
OVERLAY_EXCLUDE = {"DESIGN.md"}
DEFAULT_REMOTE = "git@github.com:League-Microbit/pxt-diff-drive.git"
SOURCE_REPO = "League-Robotics/pxt-nezha-diffdrive"
# Commits in the generated repo are authored as the Actions bot
# whoever runs the script, so its `git log` reads as what it is:
# machine output of this script, not a person's edit.
BOT_NAME = "pxt-nezha-diffdrive publish"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
# Branch created when the target repo is still empty (its first push
# makes it GitHub's default branch); an existing repo's default branch
# is used as-is.
DEFAULT_BRANCH = "main"


def git(*args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=str(cwd), check=check,
                          text=True, capture_output=True)


def load_manifest(repo=REPO):
    with open(repo / "pxt.json") as fh:
        return json.load(fh)


def overlay_files(overlay=OVERLAY_DIR):
    """Relative paths (PurePosixPath) of every overlay file that gets
    published, sorted."""
    out = []
    for path in sorted(overlay.rglob("*")):
        if path.is_dir():
            continue
        rel = pathlib.PurePosixPath(path.relative_to(overlay).as_posix())
        if str(rel) in OVERLAY_EXCLUDE:
            continue
        out.append(rel)
    return out


def overlay_test_files(overlay=OVERLAY_DIR):
    """The published `testFiles`: overlay `*.ts` at the overlay root."""
    return [str(rel) for rel in overlay_files(overlay)
            if rel.parent == pathlib.PurePosixPath(".")
            and rel.suffix == ".ts"]


def published_manifest(manifest, test_files):
    """The pxt.json the published repo carries. Pure function: key
    order is preserved, `public` follows `license`, `testFiles`
    follows `files`."""
    out = {}
    for key, value in manifest.items():
        if key in ("testFiles", "public"):
            continue
        out[key] = value
        if key == "license":
            out["public"] = True
        if key == "files":
            out["testFiles"] = list(test_files)
    out.setdefault("public", True)
    out.setdefault("testFiles", list(test_files))
    return out


def assemble(out, repo=REPO, overlay=OVERLAY_DIR):
    """Write the published tree to `out` (created; must be empty).
    Returns the sorted list of relative paths written."""
    out = pathlib.Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to assemble into non-empty {out}")
    if not (overlay / "README.md").is_file():
        # The engineering README is in pxt.json's `files`; without an
        # overlay README it would be published as the extension's.
        raise SystemExit(f"{overlay}/README.md is missing")
    manifest = load_manifest(repo)
    missing = [f for f in manifest["files"] if not (repo / f).is_file()]
    if missing:
        raise SystemExit("pxt.json files not on disk: " + ", ".join(missing))

    out.mkdir(parents=True, exist_ok=True)
    written = set()
    for rel in manifest["files"]:
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, dst)
        written.add(rel)
    # Overlay last, so it wins over anything `files` listed.
    for rel in overlay_files(overlay):
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(overlay / rel, dst)
        written.add(str(rel))
    published = published_manifest(manifest, overlay_test_files(overlay))
    (out / "pxt.json").write_text(json.dumps(published, indent=4) + "\n")
    written.add("pxt.json")
    return sorted(written)


def source_revision(repo=REPO):
    """(sha, subject, dirty) of the source checkout. `dirty` means the
    published inputs -- pxt.json, its `files`, the overlay -- differ
    from HEAD, so the commit message can say the tree is not
    reproducible from the sha it names."""
    sha = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    subject = git("log", "-1", "--format=%s", cwd=repo).stdout.strip()
    inputs = ["pxt.json", "extension"] + list(load_manifest(repo)["files"])
    dirty = git("status", "--porcelain", "--", *inputs,
                cwd=repo).stdout.strip() != ""
    return sha, subject, dirty


def commit_message(source, version):
    sha, subject, dirty = source
    short = sha[:12] + ("-dirty" if dirty else "")
    return (f"Sync from {SOURCE_REPO}@{short}\n\n"
            f"{subject}\n\n"
            f"pxt.json version {version}\n"
            f"Source: https://github.com/{SOURCE_REPO}/commit/{sha}\n"
            f"Generated by tools/publish_extension.py; do not edit here.\n")


def _wipe_worktree(clone):
    for entry in clone.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def publish(tree, remote=DEFAULT_REMOTE, branch=None, dry_run=False,
            source=None):
    """Push the assembled `tree` to `remote`. Returns a report dict:
    remote, branch, version, tag, changed, tag_existed, commit."""
    tree = pathlib.Path(tree)
    version = json.loads((tree / "pxt.json").read_text())["version"]
    tag = "v" + version
    identity = ["-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}"]
    report = {"remote": remote, "version": version, "tag": tag,
              "dry_run": dry_run}
    with tempfile.TemporaryDirectory(prefix="pxt-diff-drive-") as tmp:
        clone = pathlib.Path(tmp) / "repo"
        git("clone", "--quiet", remote, str(clone), cwd=tmp)
        has_commits = git("rev-parse", "--verify", "-q", "HEAD",
                          cwd=clone, check=False).returncode == 0
        if has_commits:
            branch = branch or git("symbolic-ref", "--short", "HEAD",
                                   cwd=clone).stdout.strip()
        else:
            branch = branch or DEFAULT_BRANCH
            git("symbolic-ref", "HEAD", f"refs/heads/{branch}", cwd=clone)
        report["branch"] = branch

        _wipe_worktree(clone)
        shutil.copytree(tree, clone, dirs_exist_ok=True)
        git("add", "-A", cwd=clone)
        changed = git("diff", "--cached", "--quiet",
                      cwd=clone, check=False).returncode != 0
        report["changed"] = changed
        if changed:
            git(*identity, "commit", "--quiet", "-m",
                commit_message(source or source_revision(), version),
                cwd=clone)
            if not dry_run:
                git("push", "--quiet", "origin",
                    f"HEAD:refs/heads/{branch}", cwd=clone)

        tag_existed = git("ls-remote", "--tags", "origin",
                          f"refs/tags/{tag}", cwd=clone).stdout.strip() != ""
        report["tag_existed"] = tag_existed
        if not tag_existed:
            git(*identity, "tag", "-a", tag, "-m",
                f"{tag}: pxt.json version {version}", cwd=clone)
            if not dry_run:
                git("push", "--quiet", "origin", f"refs/tags/{tag}",
                    cwd=clone)
        report["commit"] = git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    return report


def summarize(report):
    lines = ["## Extension publish", ""]
    lines.append(f"- remote: `{report['remote']}`"
                 + ("  **(dry run -- nothing pushed)**" if report["dry_run"]
                    else ""))
    state = "updated" if report["changed"] else "unchanged"
    lines.append(f"- branch `{report['branch']}` @ `{report['commit'][:12]}`"
                 f" -- {state}")
    tag_state = "already existed" if report["tag_existed"] else "created"
    lines.append(f"- version {report['version']}: tag `{report['tag']}`"
                 f" {tag_state}")
    if report["changed"] and report["tag_existed"]:
        lines += ["",
                  f"> **Content changed but `{report['tag']}` already "
                  "exists.** Projects pinned to that tag will not see this "
                  "change; bump `version` in pxt.json to release it."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", metavar="DIR",
                    help="assemble the published tree into DIR and stop")
    ap.add_argument("--publish", nargs="?", const=DEFAULT_REMOTE,
                    metavar="REMOTE",
                    help=f"push to REMOTE (default {DEFAULT_REMOTE})")
    ap.add_argument("--branch", help="target branch (default: the remote's, "
                    f"or {DEFAULT_BRANCH} for an empty remote)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --publish: commit and tag locally, push nothing")
    ap.add_argument("--summary", metavar="FILE",
                    help="append the markdown summary to FILE "
                    "(e.g. $GITHUB_STEP_SUMMARY)")
    args = ap.parse_args(argv)

    if args.out:
        for rel in assemble(args.out):
            print(rel)
        return 0
    if not args.publish:
        with tempfile.TemporaryDirectory() as tmp:
            for rel in assemble(tmp):
                print(rel)
        return 0
    with tempfile.TemporaryDirectory(prefix="pxt-diff-drive-tree-") as tmp:
        assemble(tmp)
        report = publish(tmp, args.publish, branch=args.branch,
                         dry_run=args.dry_run)
    text = summarize(report)
    sys.stdout.write(text)
    if args.summary:
        with open(args.summary, "a") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
