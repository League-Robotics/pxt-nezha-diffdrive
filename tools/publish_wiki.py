#!/usr/bin/env python3
"""Publish a Markdown doc from this repo to the Robot Garage wiki
(DokuWiki at http://robot-garage.home/).

    uv run python tools/publish_wiki.py docs/robot-connections.md nezha-diffdrive:connecting
    uv run python tools/publish_wiki.py --dry-run docs/robot-connections.md x:y   # print DokuWiki text

The wiki's JSON-RPC API accepts anonymous writes (its own
`agents:start` page says so), so this needs no credentials. The repo
Markdown is the SOURCE OF TRUTH; the wiki page is a rendering of it,
and the page gets a banner saying so plus the git revision it came
from. **Re-run this after editing the source doc** -- nothing does it
automatically. The docs that are published, and their page ids, are
listed in `PUBLISHED` below so a reader of either side can find the
other.

The Markdown -> DokuWiki conversion here covers what this repo's docs
use: ATX headings, fenced code blocks, inline code, bold/italic,
bulleted and numbered lists, pipe tables, and links. Anything fancier
comes through as-is.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

WIKI = "http://robot-garage.home"
RPC = WIKI + "/lib/exe/jsonrpc.php/"

# (repo path, wiki page id) -- the republish list. Keep this in step with
# the "Published to" line at the top of each source doc.
PUBLISHED = [
    ("docs/robot-connections.md", "nezha-diffdrive:connecting"),
]

_REPO = pathlib.Path(__file__).resolve().parent.parent


def rpc(method, **params):
    req = urllib.request.Request(RPC + method, data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.load(r)
    err = body.get("error") or {}
    if err.get("code", 0) != 0:
        raise RuntimeError(f"{method}: {err}")
    return body.get("result")


def _inline(text):
    """Inline Markdown -> DokuWiki: code, bold, italic, links."""
    text = re.sub(r"`([^`]+)`", r"''\1''", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"**\1**", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"//\1//", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"[[\2|\1]]", text)
    return text


def md_to_dokuwiki(md):
    out = []
    lines = md.splitlines()
    i = 0
    in_code = False
    code_lang = ""
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip()
                out.append(f"<code {code_lang}>" if code_lang else "<code>")
            else:
                in_code = False
                out.append("</code>")
            i += 1
            continue
        if in_code:
            out.append(line)
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            eq = "=" * max(2, 7 - level)
            out.append(f"{eq} {_inline(m.group(2)).strip()} {eq}")
            i += 1
            continue
        if line.startswith("|"):
            # pipe table: header row, separator, body rows
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            header = rows[0]
            body = [r for r in rows[1:] if not re.match(r"^\|[\s:|-]+\|?$", r)]
            def cells(r):
                return [c.strip() for c in r.strip().strip("|").split("|")]
            out.append("^ " + " ^ ".join(_inline(c) for c in cells(header)) + " ^")
            for r in body:
                out.append("| " + " | ".join(_inline(c) for c in cells(r)) + " |")
            continue
        m = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if m:
            depth = len(m.group(1)) // 2 + 1
            out.append("  " * depth + "* " + _inline(m.group(2)))
            i += 1
            continue
        m = re.match(r"^(\s*)\d+\.\s+(.*)$", line)
        if m:
            depth = len(m.group(1)) // 2 + 1
            out.append("  " * depth + "- " + _inline(m.group(2)))
            i += 1
            continue
        out.append(_inline(line))
        i += 1
    return "\n".join(out) + "\n"


def banner(src_rel):
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO,
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rev = "unknown"
    return (f"<WRAP info>**Generated from ''{src_rel}'' in the pxt-nezha-diffdrive "
            f"repo (rev {rev}) by ''tools/publish_wiki.py''.** Edit the Markdown there "
            "and re-run the tool; edits made here are overwritten on the next "
            "publish.</WRAP>\n\n")


def publish(src, page, dry_run=False):
    src_path = (_REPO / src) if not pathlib.Path(src).is_absolute() else pathlib.Path(src)
    md = src_path.read_text()
    src_rel = str(src_path.relative_to(_REPO)) if src_path.is_relative_to(_REPO) else str(src_path)
    text = banner(src_rel) + md_to_dokuwiki(md)
    if dry_run:
        sys.stdout.write(text)
        return
    rpc("core.savePage", page=page, text=text, summary=f"publish {src_rel}")
    print(f"published {src_rel} -> {WIKI}/doku.php?id={page}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", help="Markdown file (repo-relative)")
    ap.add_argument("page", nargs="?", help="wiki page id, e.g. nezha-diffdrive:connecting")
    ap.add_argument("--all", action="store_true", help="republish everything in PUBLISHED")
    ap.add_argument("--dry-run", action="store_true", help="print the DokuWiki text, publish nothing")
    a = ap.parse_args()
    if a.all:
        for src, page in PUBLISHED:
            publish(src, page, a.dry_run)
        return 0
    if not (a.source and a.page):
        ap.error("give SOURCE and PAGE, or --all")
    publish(a.source, a.page, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
