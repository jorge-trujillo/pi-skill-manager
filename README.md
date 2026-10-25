# Pi Skill Marketplace Manager

A terminal tool for macOS/Linux (Python 3.10+) that discovers skills in Claude
marketplace repositories and links the ones you choose into your Pi agent
directory. Git must already be installed.

- **No repository scripts are run** — browsing and installing never executes
  anything from a marketplace.
- **No hooks, MCP configuration, commands, or external plugin repositories**
  are installed. Only skill directories are linked.
- **Nothing is rewritten** — skill files stay exactly as published; each
  installed skill is a symlink to the marketplace checkout.

## Quick start

```sh
# 1. Set up the environment (PyYAML is the only third-party dependency)
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 2. Add a marketplace repository (any cloneable HTTPS or SSH Git URL)
.venv/bin/python pi_skill_manager.py marketplace add https://github.com/owner/repo.git

# 3. See what skills it offers
.venv/bin/python pi_skill_manager.py skills list repo

# 4. Install one
.venv/bin/python pi_skill_manager.py skills install repo/plugin/skill-folder

# 5. Refresh skill discovery in Pi
/reload
```

Prefer point-and-click? Run the tool with no subcommand to open an interactive
curses menu:

```sh
.venv/bin/python pi_skill_manager.py
```

## How storage works

| What | Where |
|------|-------|
| Marketplace checkouts | `~/.pi/agent/marketplaces/<marketplace-id>/` |
| Installed skill symlinks | `~/.pi/agent/skills/<declared-name>` |

- The marketplace ID defaults to the repository basename; pass `--name` to
  choose a different one when the destination is taken. Manifest display names
  are separate from this ID.
- A skill's identity is `marketplace/plugin/relative-skill-directory`, including
  nested directories (a skill directly inside `skills/` uses `.`).
- When you install a skill, its whole directory is linked, so supporting files
  stay intact. Frontmatter must declare a safe name and a nonempty description;
  malformed skills and external `source` references are reported, never
  installed.
- Pass `--agent-dir <dir>` **before** any subcommand to redirect all storage
  somewhere else — useful for testing:

  ```sh
  .venv/bin/python pi_skill_manager.py --agent-dir /tmp/pi-test-agent skills installed
  ```

## CLI reference

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
```

Notes:

- Both `ssh://user@host/path` / `user@host:path` and HTTPS URLs are accepted.
  Local paths are not accepted by the public interface.
- Git runs without a shell and inherits your terminal, so authentication
  prompts work normally. Credentials are never stored.
- Expected failures (bad URL, conflict, dirty worktree, …) print an actionable
  message and return a nonzero exit code.

## Interactive menu

Launching without a subcommand opens a curses menu: **Add marketplace**,
**List marketplaces**, **Browse/install skills**, **Installed skills**,
**Update marketplace**, **Quit**.

- `Up/Down` (also `k/j`) move, `Enter` selects, `Escape` goes back, `q` leaves
  the current menu (and quits at the root).
- Skill lists use multiline cards that wrap to the terminal width; arrows
  select whole entries, not individual lines. Menus scroll, redraw on resize,
  and keep the selected card visible (oversized cards are clipped).
- Prompts accept `Enter` to submit, backspace to edit, and `Escape` to cancel.
- Installing/removing defaults to **Cancel**, so a stray Enter can't change
  anything. Results stay visible until you go back.
- When Git needs credentials, the menu temporarily hands over the normal
  terminal so authentication still works. If the tool is launched with
  redirected/non-terminal output, it exits with an error — use the CLI
  subcommands instead.

## Safety and limitations

- **Review source before installation.** Marketplace contents are untrusted
  executable instructions. Linking is not compatibility conversion: skills may
  require Claude-specific tools or separately installed dependencies, which
  this tool does not install. Use `/reload` in Pi to refresh skill discovery.
- Occupied destinations (including dangling links) are never overwritten.
  Declared names are checked against recursively discoverable skills in the
  selected skills directory. Whole-plugin installs preflight every entry and
  refuse all changes on any conflict; creation errors roll back newly made
  links. Re-installing an identical managed link is a no-op.
- Filesystem state defines ownership, not a registry. A managed entry is a
  top-level symlink targeting inside a validated managed checkout, including a
  broken target; links created by others into these checkouts also count as
  managed. Everything else is unmanaged and cannot be removed. Removal only
  unlinks the selected link, never its source; CLI removal is explicit with no
  prompt. Invalidated manifests can make links unmanaged until the manifest is
  repaired.
- The installed view covers only the selected agent skills directory — not Pi
  packages or project-local skill locations. Invalid existing frontmatter
  cannot supply a declared name for collision detection.
- Updates refuse dirty worktrees (including untracked files), then run
  `git pull --ff-only`. No reset, automatic merge, stash, unlink, or rename.
  Broken targets, invalid entries, and declared-name collisions are reported.
  Existing links immediately expose updated content.
- **Do not run concurrent instances**, or mutate checkout/skills paths while an
  operation is running. Version one has no interprocess locking and is not a
  sandbox against concurrent hostile filesystem modifications.

## Verification

```sh
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q skill_manager pi_skill_manager.py tests
```

Tests use temporary agent directories and local Git fixtures via a
Python-only `allow_local` test seam — never actual user skills or a
private/public remote. Coverage includes parsing/containment, unmanaged
preservation, broken links, collisions, plugin preflight/rollback,
fast-forward/dirty/diverged updates, CLI lifecycle, and POSIX pseudo-terminal
navigation, scrolling, resize, cancellation, and Git terminal handoff. PTY
restoration verifies canonical/echo/signal flags; macOS Python itself enables
IUTF8 at startup, so that flag is excluded. Real SSH credential challenges and
Linux terminal behavior require environment-specific manual verification. The
canonical approved design was copied to `PLAN.md`.

## License

[MIT](LICENSE)