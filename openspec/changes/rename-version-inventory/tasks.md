## 1. Stage 1 — Inventory Path Contract

### RED

- [x] 1.1 Add failing tests requiring default discovery of root `docker-constructor.toml` with no fallback to `versions.toml`.
- [x] 1.2 Add failing tests for generated and in-image default paths, authoritative-output protection, CLI help, and filename-agnostic explicit `--inventory` behavior.

### GREEN

- [x] 1.3 Rename the authoritative file and update resolver constants, discovery, generated output defaults, path-safety rules, and user-facing diagnostics.
- [x] 1.4 Preserve arbitrary explicit inventory paths for fixtures, experiments, and external callers.

### INTROSPECT

- [x] 1.5 Centralize lifecycle path constants where appropriate and confirm the authoritative, generated, and runtime locations cannot be confused.

### VALIDATE

- [x] 1.6 Run inventory, effective rendering, CLI, update-discovery, and path-security tests without Docker.

## 2. Stage 2 — Runtime and Verification Consumers

### RED

- [x] 2.1 Add failing source-contract tests requiring `/usr/local/share/pi-cli/docker-constructor.toml` in the image, extension installer, runtime smoke check, and versioned-image verifier.
- [x] 2.2 Add failing fake-Docker acceptance tests for ownership, read-only mode, inventory comparison, and stale runtime paths.

### GREEN

- [x] 2.3 Update Dockerfile copy/ownership paths, runtime scripts, verification tools, generated evidence defaults, and acceptance harnesses.
- [x] 2.4 Rename semantically meaningful generated artifacts and fixture comments while retaining arbitrary temporary filenames where filename identity is not under test.

### INTROSPECT

- [x] 2.5 Confirm every runtime consumer reads the same root-owned effective inventory and no fallback path can mask a missing file.

### VALIDATE

- [x] 2.6 Run source-contract, versioned-image, runtime, and acceptance tests with mocks/fakes; do not require Docker.

## 3. Stage 3 — Documentation and Active Specifications

### RED

- [x] 3.1 Add failing semantic-source and documentation tests requiring `docker-constructor.toml` across maintained README translations and supported command examples.
- [x] 3.2 Add failing stale-reference checks covering maintained source, scripts, tests, and active OpenSpec changes while excluding archived history and filename-agnostic fixtures.

### GREEN

- [x] 3.3 Update Russian, English, and Chinese documentation, help text, examples, semantic-source allowlists, and repository-owned scripts.
- [x] 3.4 Update all active OpenSpec proposals, designs, specs, and tasks that prescribe the old authoritative or effective inventory path.
- [x] 3.5 Document migration from `versions.toml` to `docker-constructor.toml` without introducing a compatibility fallback.

### INTROSPECT

- [x] 3.6 Review every remaining `versions.toml` occurrence and classify it as archived history, intentionally arbitrary fixture data, or a defect.

### VALIDATE

- [x] 3.7 Run documentation, semantic-source, source-contract, strict validation for every active OpenSpec change, and `git diff --check`.

## 4. Stage 4 — Integrated Rename Verification

### RED

- [x] 4.1 Add an integration test that operates on a repository fixture containing only `docker-constructor.toml` and exercises validate, env rendering, update checks, and effective output generation.

### GREEN

- [x] 4.2 Complete any remaining path migrations exposed by the integrated fixture without changing inventory schema or selected values.

### INTROSPECT

- [x] 4.3 Compare the renamed authoritative file content with its predecessor and confirm the change is path-only except for self-descriptive comments.
- [x] 4.4 Verify concurrent direct-Docker artifacts consistently consume the new name and cannot reintroduce the old defaults when applied.

### VALIDATE

- [x] 4.5 Run the full local test suite, compile/import checks, strict OpenSpec validation, and repository-wide stale-reference search without Docker.
- [x] 4.6 If Docker-host evidence is later collected by the direct-Docker change, require its bundle to demonstrate the new generated and in-image inventory paths rather than adding a separate Docker run for this rename.
