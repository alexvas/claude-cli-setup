# Delta: MCP Tool Servers

**Change ID:** `add-spec-from-project-code`
**Affects:** Dockerfile (builder stage), docker/build-mcp.sh, docker/mcp/, docker/setup-mcp-yarn.sh, .claude/settings.json

---

## ADDED

### Requirement: MCP Server Inventory

The container includes MCP servers for filesystem, ripgrep, fetch, git, uv, cargo, and astro-docs. Each is configured in `.claude/settings.json`.

#### Scenario: All MCP servers are available
- GIVEN the container is running
- WHEN Claude CLI initializes MCP
- THEN the following servers are available:
  - `mcp__cargo__*` — Rust toolchain (cargo build, test, clippy, fmt, doc, tree, etc.)
  - `mcp__ripgrep__*` — Code search (grep, search, count-matches, list-files)
  - `mcp__filesystem__*` — File operations (read, write, edit, search, list, move)
  - `mcp__fetch__*` — URL fetching
  - `mcp__git__*` — Git operations (add, commit, diff, log, status, branch)
  - `mcp__uv__*` — Python/uv tools (add, build, init, lock, run, sync, publish)
  - `mcp__astro-docs__*` — Astro framework documentation search

### Requirement: Rust MCP (cargo-mcp)

Cargo toolchain operations are exposed via cargo-mcp with fallback to rust-mcp-server.

#### Scenario: Cargo MCP tools
- GIVEN the container is running
- WHEN `cargo-mcp` is installed (preferred)
- THEN all cargo subcommands (build, check, test, clippy, fmt, doc, add, remove, update, tree, metadata, etc.) are available as MCP tools
- WHEN `cargo-mcp` installation failed
- THEN `rust-mcp-server` is used as fallback

### Requirement: Yarn MCP Setup

TypeScript-based MCP servers are managed via a Yarn Berry workspace at `/home/dev/mcp/`.

#### Scenario: MCP workspace build
- GIVEN the builder stage is running
- WHEN `docker/build-mcp.sh` executes
- THEN the Yarn Berry workspace at `/home/dev/mcp/` is built
- THEN the resulting bundle is copied to the runtime stage

### Requirement: MCP Configuration Structure

MCP servers are declared in `/home/dev/.claude/settings.json` as a flat list with server name, command, and args.

#### Scenario: Settings JSON format
- GIVEN the container starts
- WHEN Claude CLI reads `.claude/settings.json`
- THEN each MCP server is configured with:
  - `mcpServers.<name>.command` — path to executable
  - `mcpServers.<name>.args` — command arguments (array)
  - `mcpServers.<name>.env` — optional environment overrides

---

## REMOVED

(None)
