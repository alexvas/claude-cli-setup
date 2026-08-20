# Implementation Contract

Every checkbox is required for completion. Each phase is complete only when its RED → GREEN → INTROSPECT → VALIDATE sequence passes and its deliverables exist. GREEN work SHALL be limited to satisfying that phase's RED tests while preserving complete-replacement, disabled-trust, and post-install reapplication semantics.

Phase dependency DAG:

```text
Phase 1 ──> Phase 2
```

A phase MAY depend only on the earlier phases named in its `Depends on` line.

## 1. Corporate Trust Directory Bootstrap

**Depends on:** none

**Deliverables:** a failing-then-passing Dockerfile contract for `validate < mkdir < initial replacement < first network operation`; enabled-only parent-directory creation; preserved final bundle reapplication.

- [x] 1.1 **RED:** Add a failing Dockerfile test requiring enabled trust bootstrap operations to occur in the exact semantic order: strict bundle validation, `mkdir -p /etc/ssl/certs`, initial replacement of `/etc/ssl/certs/ca-certificates.crt`, then `apt-get update`.
- [x] 1.2 **RED:** Add a failing Dockerfile test requiring parent-directory creation to remain inside the explicit `CORPORATE_TRUST_ENABLED=true` branch and requiring the existing post-`ca-certificates` replacement to remain after package installation.
- [x] 1.3 **GREEN:** Create `/etc/ssl/certs` after successful bundle validation and before the initial bundle copy, only inside the enabled corporate-trust branch.
- [x] 1.4 **INTROSPECT:** Review the Dockerfile diff against disabled-build filesystem preservation, pre-network trust activation, complete-replacement semantics, and final bundle reapplication; remove any unrelated trust or package changes.
- [x] 1.5 **VALIDATE:** Run focused corporate-network Dockerfile and build-vector tests and record a passing result.

## 2. Build Acceptance and Regression Closure

**Depends on:** Phase 1

**Deliverables:** acceptance evidence for a missing-directory base filesystem; unchanged disabled build behavior; valid OpenSpec artifacts; complete project checks passing.

- [x] 2.1 **RED:** Add a focused shell or container acceptance harness that starts without `/etc/ssl/certs`, enables corporate trust, and proves validation, directory creation, and bundle installation complete before the simulated first network action.
- [x] 2.2 **RED:** Add a companion acceptance case proving disabled trust does not create `/etc/ssl/certs` when it is initially absent.
- [x] 2.3 **GREEN:** Complete only the acceptance wiring required by tasks 2.1–2.2 without changing bundle validation, proxy behavior, or runtime trust mounting.
- [x] 2.4 **INTROSPECT:** Trace enabled and disabled builds through the bootstrap and post-install replacement boundaries; record and correct any ordering gap, disabled-path mutation, permission regression, or loss of final replacement content.
- [x] 2.5 **VALIDATE:** Run the focused corporate-network acceptance and documentation suites and record a passing result.
- [x] 2.6 **VALIDATE:** Run the complete project test suite with no skipped or weakened regressions.
- [x] 2.7 **VALIDATE:** Run `openspec validate bootstrap-corporate-trust-directory` and confirm every modified specification scenario has passing automated coverage.
