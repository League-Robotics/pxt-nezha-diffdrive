"""Bring up the local MakeCode blocks editor with this extension loaded.

`just blocks` runs this. It prepares the on-disk workspace `pxt serve`
expects, starts the server, and opens the editor on the one URL that
actually selects the filesystem workspace.

Everything here exists because of a specific trap. In order:

THE `file:` DEP MUST POINT INSIDE `projects/`.
    The editor resolves a `file:` dependency by looking up its last path
    segment as a *workspace project*, and pxt-core's `readPkgAsync` does
    `path.join(userProjectsDir, logicalDirname)` behind a guard that
    rejects anything climbing out of `projects/`. So the natural-looking
    `"nezha-diffdrive": "file:../.."` can never resolve, and the editor
    reports it only as a console line -- the toolbox just silently comes
    up without the category.

    MEASURED 2026-08-29, this worktree, `pxt serve` on :3232:
    `curl --path-as-is /api/pkg/blocktest/../..` and `/api/pkg/..` both
    answer with the literal body `Bad path :-(`; with the `file:../..`
    spec the page logged `invalid package nezha-diffdrive: cannot find
    '..' in the workspace.` and `.blocklyTreeLabel` read back as
    Basic..Math, Extensions, Advanced with no DiffDrive. After the
    symlink below the same read-back contained DiffDrive.

    Hence `link_extension()`: the extension root is published INTO
    `projects/` as a symlink so it is addressable as a project.

`?ws=fs` HAS TO BE PASSED TWICE.
    Without it the editor uses browser IndexedDB storage and My Projects
    looks empty -- the usual "my extension isn't there". The first load
    consumes the `#local_token` fragment and REWRITES the URL, dropping
    the query string with it, so the second navigation is what actually
    lands on the fs workspace. Measured same session: navigating once to
    `index.html?ws=fs#local_token=...` left `location.href` at
    `http://localhost:3232`.

THE FIRST OPEN AFTER A DEPENDENCY CHANGE USUALLY FAILS. RE-OPEN.
    Measured 2026-08-29, two distinct shapes, both on the first open
    after the dep changed:
      - `blocktest`: sat ~9 min on a blank canvas with an active
        `.ui.loader` and `pxt.mainPkg` deps still empty. Never finished.
        `pxt install` in the project plus a reload landed the full
        toolbox in ~2 min.
      - `Robot1` (dep added by --add-extension): open #1 ran ~100 s and
        then dropped back to the HOME SCREEN with no toolbox at all;
        open #2 came up in ~2 min with both Radio and DiffDrive.
    So: this script always pre-installs before opening, and a first open
    that stalls past ~4 min or bounces home is expected -- just open the
    project again. It is not a broken dependency.

Extensions themselves open JS-only, so blocks are exercised through a
consumer project that depends on the extension. Projects made with the
editor's own New Project button do NOT get the dependency; point
`--add-extension` at them.
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS = REPO_ROOT / "projects"
DEFAULT_PORT = 3232

STARTER_BLOCKS = (
    '<xml xmlns="https://developers.google.com/blockly/xml">'
    "<variables></variables>"
    '<block type="pxt-on-start" x="0" y="0"></block>'
    "</xml>\n"
)


def ext_name() -> str:
    """The extension's package name, from the repo-root pxt.json."""
    return json.loads((REPO_ROOT / "pxt.json").read_text())["name"]


def port_open(port: int) -> bool:
    """True if anything is already serving on this port.

    Must try every address family getaddrinfo returns: `pxt serve` binds
    the IPv6 loopback ONLY. MEASURED 2026-08-29 -- `lsof -nP -iTCP:3232
    -sTCP:LISTEN` on a healthy server reads `TCP [::1]:3232 (LISTEN)`
    with no IPv4 row, so an `AF_INET` 127.0.0.1 probe reports the port
    free and this script tries to start a second server on top of a
    running one.
    """
    try:
        infos = socket.getaddrinfo(
            "localhost", port, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror:
        return False
    for family, kind, proto, _canon, addr in infos:
        with socket.socket(family, kind, proto) as s:
            s.settimeout(0.4)
            if s.connect_ex(addr) == 0:
                return True
    return False


def link_extension() -> Path:
    """Publish the extension root into projects/ so `file:` can reach it."""
    PROJECTS.mkdir(exist_ok=True)
    link = PROJECTS / ext_name()
    if link.is_symlink():
        if os.readlink(link) == "..":
            return link
        link.unlink()
    elif link.exists():
        raise SystemExit(
            f"{link} exists and is not a symlink -- refusing to replace it."
        )
    # Relative, so the link keeps working if the checkout moves.
    link.symlink_to("..")
    print(f"linked {link.relative_to(REPO_ROOT)} -> ..")
    return link


def set_dependency(project: Path) -> None:
    """Point a project's pxt.json at the linked extension, preserving the rest."""
    cfg_path = project / "pxt.json"
    cfg = json.loads(cfg_path.read_text())
    deps = cfg.setdefault("dependencies", {})
    want = f"file:../{ext_name()}"
    if deps.get(ext_name()) == want:
        return
    deps["core"] = deps.get("core", "*")
    deps[ext_name()] = want
    cfg_path.write_text(json.dumps(cfg, indent=4) + "\n")
    print(f"{project.name}: dependencies[{ext_name()}] = {want}")


def make_consumer(name: str, reset: bool) -> Path:
    """Create (or refresh) the scratch project that exercises the blocks."""
    project = PROJECTS / name
    fresh = not project.exists()
    project.mkdir(parents=True, exist_ok=True)

    if fresh or reset:
        (project / "main.blocks").write_text(STARTER_BLOCKS)
        (project / "main.ts").write_text("")
        (project / "README.md").write_text(
            f"Scratch consumer project for exercising the {ext_name()} blocks\n"
            "in the local MakeCode editor. Created by tools/blocks_env.py.\n"
        )
    if not (project / "pxt.json").exists():
        (project / "pxt.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "dependencies": {"core": "*", "microphone": "*"},
                    "files": ["main.blocks", "main.ts", "README.md"],
                    "preferredEditor": "blocksprj",
                },
                indent=4,
            )
            + "\n"
        )
    set_dependency(project)
    print(f"{'created' if fresh else 'reusing'} project {project.relative_to(REPO_ROOT)}")
    return project


def clear_history(project: Path) -> None:
    """Drop the editor's _history file.

    The fs workspace 409-conflicts on saving `_history` and the editor
    then falls back SILENTLY to a memory workspace ("Auto-Save Disabled")
    -- edits stop reaching disk while everything still looks fine.
    """
    h = project / "_history"
    if h.exists():
        h.unlink()
        print(f"{project.name}: removed stale _history")


def pxt_install(project: Path) -> None:
    """Pre-resolve deps. See THE FIRST OPEN CAN WEDGE in the module docstring."""
    print(f"{project.name}: pxt install ...")
    r = subprocess.run(
        ["pxt", "install"], cwd=project, capture_output=True, text=True
    )
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit(f"pxt install failed in {project} (exit {r.returncode})")


def start_server(port: int):
    """Start `pxt serve`, returning (process, local_token_url_or_None).

    Stdout is streamed through so the server's own log stays visible; the
    `#local_token=` line is picked out of it on the way past.
    """
    # The websocket server is a SEPARATE port that defaults to 3233 no
    # matter what --port says, so without --wsport a second instance dies
    # with `EADDRINUSE ::1:3233` even on a free HTTP port.
    wsport = port + 1
    print(f"starting pxt serve on :{port} (ws :{wsport}, cwd {REPO_ROOT})")
    proc = subprocess.Popen(
        [
            "pxt", "serve", "--noBrowser", "--noauth", "--noSerial",
            "--port", str(port), "--wsport", str(wsport),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    token_url = None
    deadline = time.time() + 120
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        sys.stdout.write(line)
        sys.stdout.flush()
        if "#local_token=" in line:
            token_url = line.strip()
            break
    # The "Build failed: ... scandir 'libs'" above is harmless -- the npm
    # pxt-microbit ships no libs/, and the prebuilt editor in built/ serves
    # fine. Wait for the port rather than trusting the log.
    while time.time() < deadline and not port_open(port):
        time.sleep(0.5)
    if not port_open(port):
        proc.terminate()
        raise SystemExit("pxt serve never opened the port")
    return proc, token_url


def open_editor(port: int, token_url, started: bool) -> None:
    """Open the editor on the fs workspace. See `?ws=fs` HAS TO BE PASSED TWICE."""
    fs_url = f"http://localhost:{port}/index.html?ws=fs"
    if started and token_url:
        frag = token_url.split("#", 1)[1]
        first = f"http://localhost:{port}/index.html?ws=fs#{frag}"
        print(f"opening {first}")
        webbrowser.open(first)
        # That load consumes the token and rewrites the URL, dropping the
        # query. Give it a moment, then open the one that sticks.
        time.sleep(6)
    print(f"opening {fs_url}")
    webbrowser.open(fs_url)


def stop_server(port: int) -> int:
    r = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
    )
    pids = [p for p in r.stdout.split() if p.isdigit()]
    if not pids:
        print(f"nothing listening on :{port}")
        return 0
    for pid in pids:
        subprocess.run(["kill", pid])
        print(f"stopped pid {pid} on :{port}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument(
        "--project",
        default="blocktest",
        help="scratch consumer project under projects/ (default: blocktest)",
    )
    ap.add_argument(
        "--add-extension",
        metavar="PROJECT",
        help="add the extension dependency to an existing project and exit "
        "(for projects made with the editor's New Project button)",
    )
    ap.add_argument(
        "--reset",
        action="store_true",
        help="reset the consumer project's main.blocks/main.ts to an empty on-start",
    )
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    ap.add_argument(
        "--stop", action="store_true", help="stop whatever is serving on --port and exit"
    )
    args = ap.parse_args()

    if not shutil.which("pxt"):
        raise SystemExit("pxt CLI not found on PATH")

    if args.stop:
        return stop_server(args.port)

    link_extension()

    if args.add_extension:
        project = PROJECTS / args.add_extension
        if not (project / "pxt.json").exists():
            raise SystemExit(f"no project at {project}")
        set_dependency(project)
        pxt_install(project)
        print(f"\n{args.add_extension} now depends on {ext_name()} -- "
              "reload the editor tab to pick it up.")
        return 0

    project = make_consumer(args.project, args.reset)
    clear_history(project)
    pxt_install(project)

    started = False
    proc = None
    token_url = None
    if port_open(args.port):
        print(f":{args.port} already serving -- reusing it")
    else:
        proc, token_url = start_server(args.port)
        started = True

    if not args.no_open:
        open_editor(args.port, token_url if started else None, started)

    print(
        f"\neditor: http://localhost:{args.port}/index.html?ws=fs"
        f"\nproject: {args.project}  (DiffDrive sits between Math and Extensions)"
        "\nfirst open takes a couple of minutes. If it stalls past ~4 min or"
        "\ndrops back to the home screen, just open the project again."
    )
    if proc is None:
        return 0
    print("Ctrl-C to stop the server.\n")
    try:
        for line in proc.stdout:
            sys.stdout.write(line)
    except KeyboardInterrupt:
        proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
