# Proposal: Spec from Current Project Code

**Change ID:** `add-spec-from-project-code`
**Created:** 2026-06-17
**Status:** Draft

---

## Problem Statement

- The project has no formal specifications — all knowledge lives in source code, README, and tribal knowledge
- New contributors have no reference for expected behavior, component contracts, or invariants
- No baseline exists for regression testing or impact analysis of future changes

## Proposed Solution

Extract specifications from the existing codebase via OpenSpec framework. Walking the code file-by-file, derive requirements and scenarios that describe what the system currently does, using GIVEN-WHEN-THEN scenarios.

This is NOT a refactor or redesign — it's documentation-in-code of current behavior.

## Scope

### In Scope
- Docker image build pipeline (Dockerfile, build_wrapper.py)
- Container runtime environment (entrypoint, compose, env vars)
- Python launcher TUI (launch-claude.py)
- MCP server toolchains (cargo, ripgrep, filesystem, fetch, git, uv, astro)
- Multi-language README documentation

### Out of Scope
- IDE integration internals (belongs to IDE extension, not this project)
- inf-splitter proxy internals
- SOCKS proxy setup on host
- Rootless Docker configuration beyond build_wrapper.py

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| Build system | No | Specs describe current behavior, no code changes |
| Runtime | No | Same |
| Launcher | No | Same |
| MCP tools | No | Same |
| Documentation | No | README already exists; specs supplement it |

## Architecture Considerations

- Specs follow the OpenSpec SDD workflow: `openspec/specs/` for source-of-truth, `openspec/changes/` for proposals
- Each component gets its own spec file, mirroring the Dockerfile/docker-compose separation
- No `project.md` exists yet — will be created in a separate change

## Success Criteria

- [ ] Build pipeline behavior documented with scenarios
- [ ] Runtime container behavior documented with scenarios
- [ ] Launcher TUI behavior documented with scenarios
- [ ] MCP toolchain surface documented with scenarios
- [ ] README sync convention documented with scenarios

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Specs go stale as code evolves | High | Low | OpenSpec workflow forces delta review on changes |
| Over-specifying implementation details | Med | Low | Keep scenarios behavioral, not implementation-level |
