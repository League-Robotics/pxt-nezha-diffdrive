# Local MakeCode blocks editor for this extension.
#
# The setup this automates is not guessable -- see tools/blocks_env.py's
# module docstring for why each step is there (the `file:` dep has to
# point INSIDE projects/, `?ws=fs` has to be passed twice, and the first
# open wedges unless deps are pre-installed).
#
# Every recipe forwards extra args to the script, so `--port N` and the
# rest work on any of them: `just blocks-stop --port 3299`.

_default:
    @just --list

# Set up the workspace, serve the editor, and open it on the fs workspace.
blocks *ARGS:
    python3 tools/blocks_env.py {{ARGS}}

# Same, without opening a browser (prints the URL instead).
blocks-serve *ARGS:
    python3 tools/blocks_env.py --no-open {{ARGS}}

# Reset the scratch project's blocks to an empty `on start` and open it.
blocks-reset *ARGS:
    python3 tools/blocks_env.py --reset {{ARGS}}

# Add the extension to a project made with the editor's New Project button.
blocks-add PROJECT *ARGS:
    python3 tools/blocks_env.py --add-extension {{PROJECT}} {{ARGS}}

# Stop whatever is serving the editor.
blocks-stop *ARGS:
    python3 tools/blocks_env.py --stop {{ARGS}}

# Show what docs/blocks-toolbox.csv would do to the block annotations.
blocks-plan *ARGS:
    python3 tools/blocks_toolbox.py --check {{ARGS}}

# The CSV is the source of truth for toolbox layout: edit it and re-run
# this, rather than hand-tuning weights in the source.
# Apply docs/blocks-toolbox.csv to the block annotations.
blocks-apply *ARGS:
    python3 tools/blocks_toolbox.py {{ARGS}}
