# Implementation Tasks: Spec from Current Project Code

**Change ID:** `add-spec-from-project-code`

---

## Phase 1: Build Pipeline Specs

- [ ] 1.1 Walk Dockerfile, document build stages and their contracts
- [ ] 1.2 Walk build_wrapper.py, document rootful/rootless build paths
- [ ] 1.3 Walk docker/*.sh scripts, document bootstrap sequences

**Quality Gate:**
- [ ] Every Dockerfile stage has at least one scenario
- [ ] Build wrapper scenarios cover rootful and rootless

---

## Phase 2: Runtime Specs

- [ ] 2.1 Document docker-compose.yml service definition and env vars
- [ ] 2.2 Document entrypoint.sh behavior and chown logic
- [ ] 2.3 Document volume mount contract (1:1 host paths)

**Quality Gate:**
- [ ] All runtime env vars appear in a scenario
- [ ] Entrypoint contract is unambiguous

---

## Phase 3: Launcher Specs

- [ ] 3.1 Document IDE project discovery from lock files
- [ ] 3.2 Document TUI navigation and project selection
- [ ] 3.3 Document container launch sequence (compose override generation)
- [ ] 3.4 Document --dry-run, --tui, --light, --no-forward flags

**Quality Gate:**
- [ ] All CLI flags have a scenario
- [ ] Main path (auto-detect) and TUI path both covered

---

## Phase 4: MCP Tool Specs

- [ ] 4.1 Document MCP server inventory (cargo, ripgrep, filesystem, fetch, git, uv, astro)
- [ ] 4.2 Document .claude/settings.json MCP configuration

**Quality Gate:**
- [ ] Each MCP server listed with purpose and tool list

---

## Phase 5: Documentation Specs

- [ ] 5.1 Document README sync convention (ru, en, zh)
- [ ] 5.2 Document .env.example as configuration contract

**Quality Gate:**
- [ ] README sync convention has a scenario
- [ ] .env.example structure documented

---

## Completion Checklist

- [ ] All phases complete
- [ ] All quality gates passed
- [ ] Specs committed under `openspec/specs/`
- [ ] Ready for `/openspec-archive`
