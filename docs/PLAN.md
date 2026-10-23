# Python Skill Marketplace Manager

## Goal and approved scope

Create a Python terminal tool for macOS/Linux that imports individual skills from Claude marketplaces into Pi. Launch an interactive arrow-key menu by default, with CLI subcommands for automation using the same operations.

Support SSH and HTTPS Git URLs, local plugin sources declared in `.claude-plugin/marketplace.json`, individual skill and whole-plugin installation, installed-skill inspection, managed-skill removal, and marketplace updates. Do not install Claude hooks, MCP configurations, commands, or external plugin repositories. Skills may still require Claude-specific tools or separately installed dependencies; warn that linking is not compatibility conversion.

## Recommended approach

Use Python 3.10+, `argparse`, `pathlib`, `subprocess`, and standard-library `curses`. Use PyYAML with `safe_load` to parse skill frontmatter reliably rather than inventing a YAML parser. Declare PyYAML in `requirements.txt`; install dependencies only inside `.venv`. Git must already be installed and authentication remains Git's responsibility.

### Critical files

- `pi_skill_manager.py`: entry point; no arguments opens the menu.
- `skill_manager/core.py`: marketplace discovery, skill inspection, Git operations, symlink management, and typed errors.
- `skill_manager/cli.py`: argument parsing and readable output.
- `skill_manager/tui.py`: curses menus and prompts, invoking the shared core.
- `tests/`: unittest coverage with temporary homes and local Git fixtures; no real user skill mutations or network dependency.
- `requirements.txt`: PyYAML dependency.
- `.gitignore`: ignore `.venv`, bytecode, and test artifacts.
- `README.md`: setup, commands, keybindings, trust and compatibility limitations.
- `PLAN.md`: repository copy of this approved design, created during implementation.

## Storage and discovery

Defaults:

```text
~/.pi/agent/marketplaces/<marketplace-id>/     # Git checkout
~/.pi/agent/skills/<skill-name>               # directory symlink
```

Provide a shared `--agent-dir` option for isolated use/testing, defaulting to `~/.pi/agent`.

Derive a safe marketplace ID from the Git repository basename; reject an occupied destination and explain how to select another ID with `--name`. Display the manifest's marketplace name separately. Clone into a temporary sibling directory, validate the manifest, then rename into place. On failure, clean up only temporary files created by this operation.

Read each manifest plugin's relative local `source`, inspect its `skills` directory recursively for `SKILL.md`, and parse frontmatter for declared name and description. Identity is `<marketplace-id>/<plugin>/<skill-directory-relative-path>`; show the declared skill name and description alongside that identity. Reject paths resolving outside the checkout, ambiguous identifiers, and invalid manifests. Clearly report unsupported external sources and invalid skill entries without treating them as installable. Discovery must not execute repository scripts.

Use filesystem state rather than a separate registry: a managed entry is a symlink immediately under the selected skills directory whose absolute target is inside a validated managed checkout. Broken targets remain identifiable using the unresolved link path. Existing links into those checkouts are consequently treated as managed, regardless of their creator. Everything else is unmanaged. Never delete an unmanaged file, directory, or link.

## Operations and safeguards

- **Add marketplace:** validate SSH/HTTPS URL input; run Git with argument arrays, never a shell. Clone and validate as described above. Git subprocesses must inherit normal authentication capabilities; no credentials are stored by this tool.
- **List marketplaces / available skills:** inspect local disk only; group by marketplace and plugin and indicate installation status.
- **Install skill:** symlink its entire directory using an absolute target. Preflight destination occupancy, including dangling links, and declared-name collisions among existing discoverable skills. An identical existing managed link is a no-op. Do not rewrite skill names or frontmatter.
- **Install plugin:** preflight every proposed skill, including conflicts within the plugin. Refuse the entire operation on any conflict. Skip identical existing links; if creation fails partway through, roll back only links created by that operation.
- **Installed skills:** show managed and unmanaged entries, source/target where known, and broken-link status. Inspect recursively discoverable existing skills for collision detection, but expose removal only for managed top-level links. This view covers the selected agent skills directory, not every Pi package or project skill location.
- **Remove skill:** unlink only the selected managed symlink; never remove its source directory. Confirm in the menu, and recheck ownership immediately before unlinking.
- **Update marketplace:** refuse dirty worktrees and run `git pull --ff-only`. Do not reset, merge, or stash automatically. Afterward rescan and report broken installed targets, invalid skills, and newly introduced declared-name collisions; do not silently unlink or rename anything. Existing links expose updated content automatically.
- Report actionable errors without tracebacks for expected failures. Exit nonzero on CLI failures. Do not run two tool instances concurrently; document this limitation for the first version.

Treat marketplace contents as untrusted executable instructions. Show the source before installation and explain that supporting dependencies and Claude-specific behavior are not installed automatically. Pi can refresh skill discovery with `/reload`.

## Interfaces

### Interactive terminal

Main menu: Add marketplace, List marketplaces, Browse/install skills, Installed skills, Update marketplace, Quit.

Use up/down to move, Enter to select, Escape to go back, and `q` to quit menus. Add a scrolling viewport and handle terminal resize. Browsing follows marketplace → plugin → individual skill or Install all skills. Show descriptions and installation status. Prompt for a Git URL and optional marketplace ID when adding. Show operation results and conflicts before returning to menus. Restore terminal state around Git execution so authentication prompts and errors remain usable. Fail helpfully when interactive mode is launched without a usable terminal.

### CLI

```text
python3 pi_skill_manager.py
python3 pi_skill_manager.py marketplace add <git-url> [--name <id>]
python3 pi_skill_manager.py marketplace list
python3 pi_skill_manager.py marketplace update <id>
python3 pi_skill_manager.py skills list [marketplace-id]
python3 pi_skill_manager.py skills install <marketplace>/<plugin>/<skill-path>
python3 pi_skill_manager.py skills install-plugin <marketplace>/<plugin>
python3 pi_skill_manager.py skills installed
python3 pi_skill_manager.py skills remove <installed-link-name>
```

Document global `--agent-dir` placement before subcommands. CLI removal is explicit and does not prompt; interactive removal requires confirmation.

## Verification

**Agent**

- Run the implemented unittest suite in `.venv` against temporary directories. Verify manifest/frontmatter parsing, path containment, managed/unmanaged identification, broken links, declared-name collisions, whole-plugin refusal and rollback, and preservation of unmanaged entries.
- Exercise CLI add/list/install/install-plugin/installed/remove/update using temporary local Git fixtures through the core's test seam. Verify symlink targets, supporting-file accessibility, fast-forward updates, disappeared targets, and refusal of dirty or diverged checkouts. Public URL validation must still reject local paths.
- Inspect both interfaces to confirm they call the same core operations, and inspect dependency setup to confirm libraries are installed only in `.venv` and declared in `requirements.txt`.
- Launch the menu in a pseudo-terminal and exercise navigation, scrolling, back/quit, confirmation cancellation, and terminal restoration. Confirm non-terminal launch gives an actionable error. Do not clone the user's private Git repository or modify their actual Pi directories during verification.

## Implementation Steps

1. Create repository `PLAN.md`, project skeleton, virtualenv/dependency setup, and documented storage/interface contracts.
2. Implement marketplace cloning, validation, discovery, and skill frontmatter parsing with isolated fixture tests.
3. Implement installed-skill inspection, conflict preflight, individual/plugin symlink installation, safe removal, and fast-forward update checks with filesystem and Git behavior tests.
4. Implement CLI commands and the shared agent-directory option; exercise end-to-end operations in temporary directories.
5. Implement the curses menu, scrolling, prompts, confirmations, resize handling, and Git terminal handoff; verify pseudo-terminal behavior.
6. Finish README documentation and run the verification checks, fixing failures before delivery.
