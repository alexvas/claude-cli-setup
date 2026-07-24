## Context

The three maintained README translations currently mix setup fields, build commands, Python runtime invariants, cache experiments, extension installation, launch commands, shell customization, storage cleanup, and troubleshooting at the same hierarchy. The recently added update section documents flags but not the user transaction required to update Pi or another component. The executable resolver and build/runtime decoupling sibling changes provide cleaner entry points that this documentation should adopt.

## Goals / Non-Goals

**Goals:**
- Make build, interactive launch, and component update immediately discoverable.
- Explain exactly how to update Pi and generalize the workflow safely.
- Show component lifecycle and installation ownership without duplicating selected versions.
- Consolidate infrequent operations under Maintenance.
- Keep all translations structurally and semantically equivalent.

**Non-Goals:**
- Preserve Dockerfile-development or cache-benchmarking notes; only user-facing cache cleanup belongs in Maintenance.
- Duplicate every resolver help option or system invariant.
- Automate application of update suggestions.
- Change the underlying component inventory.

## Decisions

### Organize by user jobs

Each README will use this top-level sequence:

```text
Requirements
1. Build the environment
2. Launch the environment
3. Update environment components
Maintenance
Troubleshooting
```

A separate Setup section will be removed. Any truly required input belongs at the exact action that consumes it. Optional launcher root configuration belongs under Launch.

### Put the concrete Pi update before generic reference

The update section will first show a focused `stages.pi-tools.pi` check and suggestion, manual inventory edit, validation, diff review, rebuild, and runtime verification. It will then explain other component paths and options. This follows progressive disclosure: solve the common job before documenting general machinery.

### Present components by lifecycle and ownership

A table will group base image, toolchain, Node CLIs, prebuilt binaries, shell runtime, Pi extensions, and Debian packages. Columns will identify representative components, installation location/ownership, and update mechanism. Concrete selected versions remain exclusively in `versions.toml`.

### Separate image refresh from mounted-state refresh

The general workflow will branch after rebuild. Image-owned components require image verification; `runtime.pi-extensions` additionally require running the protected installer against mounted `~/.pi`. The old standalone extension section is folded into this branch and Maintenance.

### Group options by intent

Interactive review covers `--only` and `--suggest`; machine/policy use covers `--json`, `--strict`, and `--fail-on-outdated`; advanced discovery covers prerelease and cache controls. `--suggest` is explicitly non-mutating.

### Make permission repair explicit and safe

Maintenance will explain both directions of rootless Docker ownership mismatch before commands, use `<docker-dev>:<docker-dev>` placeholders, recommend `chown -R` only for paths the user intends to own, and use `chmod -R ug+rwX`. Every translation will identify `docker-dev` as the user/group commonly mapped to host UID/GID `100999` and require adding the host user to that group.

## Risks / Trade-offs

- [Removing details makes invariants less visible] → Keep normative behavior in specs/tests and retain only user-actionable details in README.
- [Three translations drift] → Add structural token/order tests and review all translations in one change.
- [Sibling changes are not implemented first] → Declare implementation order and keep tests explicit about executable commands and build independence.
- [Permission commands can damage shared ownership] → Require placeholders, warnings, and narrowly scoped paths.

## Migration Plan

1. Implement and sync the executable resolver and build/runtime separation changes.
2. Add failing documentation structure and workflow tests.
3. Rewrite the Russian README as the reference information architecture.
4. Apply equivalent English and Chinese structures.
5. Run semantic-source, command, translation-equivalence, and full test suites.

## Resolved Questions

- Remove detailed Dockerfile and cache-development notes rather than moving them to a contributor document; retain only cache cleanup guidance under Maintenance.
- Show the `<docker-dev>:<docker-dev>` form in every translation, explain that it commonly represents rootless Docker UID/GID `100999`, and show how to add the host user to the group.
