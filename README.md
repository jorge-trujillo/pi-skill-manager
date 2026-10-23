# Pi Skill Marketplace Manager

A Python 3.10+ terminal tool for macOS/Linux that links individual Claude
marketplace skills into Pi. Git must already be installed. No repository scripts
are run during discovery. This tool does **not** install hooks, MCP configuration,
commands, or external plugin repositories.

## Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python pi_skill_manager.py
```

PyYAML is the only third-party dependency, used with `safe_load`. Install it only
inside `.venv`; curses is part of Python (your system Python must include it).

## Storage and identity

Default checkouts: `~/.pi/agent/marketplaces/<marketplace-id>/`.
Default installed directory symlinks: `~/.pi/agent/skills/<declared-name>`.
Use global `--agent-dir` **before** subcommands to isolate all storage.

Marketplace IDs derive from the repository basename; `--name` selects another
safe ID when a destination is occupied. Manifest display names are separate.
Skills have identities `marketplace/plugin/relative-skill-directory`, including
nested directories (a skill directly in `skills/` uses `.`). A plugin's relative
local `source` is resolved within the checkout; its `skills` tree is inspected
recursively. External sources and malformed skills are reported, not installed.
Frontmatter must declare a safe name and nonempty description. Names/frontmatter
are never rewritten. The entire directory is linked, retaining supporting files.

## CLI

```sh
.venv/bin/python pi_skill_manager.py marketplace add https://github.com/owner/repo.git --name example
.venv/bin/python pi_skill_manager.py marketplace add git@github.com:owner/repo.git
.venv/bin/python pi_skill_manager.py marketplace list
.venv/bin/python pi_skill_manager.py skills list example
.venv/bin/python pi_skill_manager.py skills install example/plugin/skill-folder
.venv/bin/python pi_skill_manager.py skills install-plugin example/plugin
.venv/bin/python pi_skill_manager.py skills installed
.venv/bin/python pi_skill_manager.py skills remove declared-name
.venv/bin/python pi_skill_manager.py marketplace update example
.venv/bin/python pi_skill_manager.py --agent-dir /tmp/pi-test-agent skills installed
```

SSH URLs (`ssh://user@host/path` or `user@host:path`) and HTTPS URLs are accepted;
local paths are not accepted by the public interface. Git runs without a shell
and inherits terminal/authentication capabilities. Credentials are not stored.
Expected failures print actionable errors and return nonzero.

## Menu

No subcommand opens curses: Add marketplace, List marketplaces, Browse/install
skills, Installed skills, Update marketplace, Quit. Up/down (also k/j) move,
Enter selects, Escape goes back, and q leaves the current menu (quits at root).
Skill lists use multiline cards in both the menu and CLI. Menu cards wrap to the
terminal width; arrows select whole entries, not individual lines. Menus scroll
and redraw on resize, keeping the selected card visible (oversized cards are
clipped to the viewport). Prompts use Enter to submit, backspace to edit,
and Escape to cancel. Browse marketplace → plugin → skill or Install all skills.
Install and remove prompts default to Cancel. Results remain visible until back.
Git temporarily receives the normal terminal so authentication remains usable.
A redirected/non-terminal launch gives an error; use CLI subcommands instead.

## Safety and limitations

- **Review source before installation.** Marketplace contents are untrusted
  executable instructions. Linking is not compatibility conversion. Skills may
  require Claude-specific tools or separately installed dependencies, which this
  tool does not install. Use `/reload` in Pi to refresh skill discovery.
- Occupied destinations (including dangling links) are never overwritten.
  Declared names are checked against recursively discoverable skills in the
  selected skills directory. Whole-plugin installs preflight every entry and
  refuse all changes on any conflict; creation errors roll back newly made links.
  Identical managed links are no-ops.
- Filesystem state defines ownership, not a registry. A managed entry is a
  top-level symlink targeting inside a validated managed checkout, including a
  broken target. Existing links created by others into these checkouts also count
  as managed. Everything else is unmanaged and cannot be removed. Removal only
  unlinks the selected link, never its source; CLI removal is explicit/no prompt.
  Invalidated manifests can make links unmanaged until the manifest is repaired.
- Installed view covers only the selected agent skills directory, not Pi packages
  or project-local skill locations. Invalid existing frontmatter cannot supply a
  declared name for collision detection.
- Updates refuse dirty worktrees (including untracked files), then use
  `git pull --ff-only`. No reset, automatic merge, stash, unlink or rename.
  Broken targets, invalid entries and declared-name collisions are reported.
  Existing links immediately expose updated content.
- **Do not run concurrent instances**, or mutate checkout/skills paths while an
  operation is running. Version one has no interprocess locking and is not a
  sandbox against concurrent hostile filesystem modifications.

## Verification

```sh
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q skill_manager pi_skill_manager.py tests
```

Tests use temporary agent directories and local Git fixtures via a Python-only
`allow_local` test seam, never actual user skills or a private/public remote.
Coverage includes parsing/containment, unmanaged preservation, broken links,
collisions, plugin preflight/rollback, fast-forward/dirty/diverged updates, CLI
lifecycle, and POSIX pseudo-terminal navigation, scrolling, resize, cancellation
and Git terminal handoff. PTY restoration verifies canonical/echo/signal flags;
macOS Python itself enables IUTF8 at startup, so that flag is excluded. Real SSH
credential challenges and Linux terminal behavior require environment-specific
manual verification. The canonical approved design was copied to `PLAN.md`.
