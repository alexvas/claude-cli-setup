# Delta: Python Launcher (launch-claude.py)

**Change ID:** `add-spec-from-project-code`
**Affects:** launch-claude.py

---

## ADDED

### Requirement: IDE Project Discovery

The launcher discovers active IDE projects from `~/.claude/ide/*.lock` files.

#### Scenario: Valid lock file
- GIVEN `~/.claude/ide/3000.lock` contains JSON with `transport: "ws"`, a valid `pid`, and `workspaceFolders`
- AND the PID is a live process
- WHEN `uv run launch-claude.py` runs
- THEN the project at port 3000 is listed as an available project

#### Scenario: Dead process lock
- GIVEN `~/.claude/ide/3000.lock` exists with `transport: "ws"` but the PID is dead
- WHEN `uv run launch-claude.py` runs
- THEN the project at port 3000 is NOT included (stale lock skipped)

#### Scenario: Non-ws transport
- GIVEN `~/.claude/ide/3000.lock` contains `transport: "http"` or other non-ws value
- WHEN the launcher processes lock files
- THEN the project is skipped

#### Scenario: No lock files
- GIVEN `~/.claude/ide/` directory exists but contains no `.lock` files
- WHEN `uv run launch-claude.py` runs
- THEN no IDE projects are discovered, launcher prints a warning

### Requirement: Main Project Auto-Detection

When `CLAUDE_CODE_SSE_PORT` env var is set, the matching IDE project is automatically selected as the main project.

#### Scenario: Auto-select by port
- GIVEN `CLAUDE_CODE_SSE_PORT=3000` is in the environment
- AND a live IDE project at port 3000 exists
- WHEN `uv run launch-claude.py` runs (without --tui)
- THEN project at port 3000 is selected as the main project
- THEN no TUI is shown

#### Scenario: Stale SSE port
- GIVEN `CLAUDE_CODE_SSE_PORT=3000` is in the environment
- AND no live IDE project at port 3000 exists
- WHEN `uv run launch-claude.py` runs (without --tui)
- THEN the launcher falls back to TUI or exits with an error

### Requirement: TUI for Interactive Selection

When `--tui` is passed (or auto-detection fails), a terminal UI allows selecting the main project and additional projects.

#### Scenario: TUI project selection
- GIVEN `--tui` flag is passed
- AND multiple IDE projects are discovered
- WHEN user navigates and selects a main project with Space/Enter
- THEN the selected project is highlighted
- WHEN user confirms the selection
- THEN the container is launched with the selected project as PROJECT_PATH_1

#### Scenario: Light theme
- GIVEN `--tui --light` flags are passed
- WHEN the TUI renders
- THEN colors use a light-background palette

### Requirement: Container Launch

The launcher generates a temporary compose override and launches a named container.

#### Scenario: Container launch with IDE integration
- GIVEN a main IDE project is selected
- AND `--no-forward` is NOT passed
- WHEN the container is launched
- THEN a temp override YAML is generated with `ENABLE_IDE_INTEGRATION=true`
- THEN a temp init script is generated that creates lock files and starts socat forwarding
- THEN the container name is `claude-N` where N is the next unused number

#### Scenario: Container launch without IDE
- GIVEN no IDE projects are available
- WHEN the container is launched
- THEN `ENABLE_IDE_INTEGRATION=false` is set
- THEN no socat forwarding is configured

#### Scenario: Additional projects
- GIVEN additional projects are selected in TUI
- WHEN the container is launched
- THEN compose fragment files are generated for `PROJECT_PATH_2`, `PROJECT_PATH_3`
- THEN `COMPOSE_FILE` env var includes all generated fragments

#### Scenario: Dry run
- GIVEN `--dry-run` flag is passed
- WHEN the launcher runs
- THEN the `docker compose` command is printed but NOT executed

#### Scenario: No port forward
- GIVEN `--no-forward` flag is passed
- WHEN the init script is generated
- THEN no socat port forwarding lines are included

### Requirement: Container Naming

Containers are named `claude-N` where N is the next available number.

#### Scenario: First container
- GIVEN no `claude-*` containers exist
- WHEN `next_container_num()` is called
- THEN it returns 1

#### Scenario: Existing containers
- GIVEN containers `claude-1` and `claude-2` exist
- WHEN `next_container_num()` is called
- THEN it returns 3

#### Scenario: Gap in numbering
- GIVEN containers `claude-1` and `claude-3` exist
- WHEN `next_container_num()` is called
- THEN it returns 2 (fills the gap)

---

## REMOVED

(None)
