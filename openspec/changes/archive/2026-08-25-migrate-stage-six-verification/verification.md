## Stage 6 coverage review

The retired harness mixed static repository contracts with image-build and runtime evidence. The latter is intentionally obsolete here because this change replaces only Dockerfile-static verification.

| Former scenario/input | Classification | Maintained coverage or reason |
|---|---|---|
| 6.2 inventory validation, image build, runtime verification, inspect/history | Obsolete procedural E2E | Image construction and runtime E2E are outside this change; inventory behavior remains covered by the versioning tests. |
| 6.3 Python override validation/build/runtime selection | Obsolete procedural E2E | Override projection and build-vector behavior remain covered by `TestBuildArgEmission`; building/running an override image is outside static scope. |
| `python-3.14.5.toml` | Obsolete invalid input | It no longer satisfies the current closed inventory schema; renderer/inventory unit tests use maintained fixtures. |
| 6.4 tool version matrix and baked inventory checks | Static portion covered; runtime portion obsolete | `TestDockerfileBuildContract.test_reviewed_inputs_and_retired_surfaces_are_not_baked`; executable version checks require a built image and are outside scope. |
| 6.5 repeated-build and scoped cache invalidation | Obsolete procedural E2E | BuildKit cache performance/invalidation evidence requires image builds and is outside Dockerfile-static scope. |
| `cache-rust-profile.toml`, `cache-runtime-extensions.toml` | Obsolete invalid inputs | Inputs exist only to drive the retired BuildKit experiment and no longer satisfy the current schema. |
| 6.6 provider/version tests and compileall | Covered by ordinary unittest discovery | Existing provider, inventory, renderer, and migration contract tests are discovered by the canonical unittest command. |
| 6.6 bad artifact checksum and base digest builds | Obsolete procedural E2E | Docker download/build rejection is image E2E; static checksum transport is covered by `TestDockerfileBuildContract.test_renderer_build_arguments_are_declared_and_consumed`. |
| `bad-rtk-sha256.toml`, `bad-node-digest.toml` | Obsolete invalid inputs | Inputs only drive deleted Docker failure builds and no longer satisfy the current schema. |
| 6.6 invalid Python override builds | Covered without Docker | Existing inventory/effective-configuration and build-renderer tests reject invalid override values before Docker. |
| 6.6 custom UID/GID runtime ownership | Static portion covered; runtime portion obsolete | `TestDockerfileBuildContract.test_renderer_build_arguments_are_declared_and_consumed`; container ownership E2E is outside scope. |
| 6.6 repository diff and OpenSpec validation | Replaced by validation checklist | `git diff --check` and strict OpenSpec validation are repository checks, not Dockerfile contracts. |

## Dockerfile contract inventory

| Repository invariant | Maintained test |
|---|---|
| Local `COPY` sources exist and remain visible in build context | `TestDockerfileBuildContract.test_local_copy_sources_exist_and_are_visible_in_context` |
| Constructor build arguments exactly match Dockerfile declarations and are consumed | `TestDockerfileBuildContract.test_renderer_build_arguments_are_declared_and_consumed` plus existing `TestBuildArgEmission` renderer tests |
| Constructor target `runtime` names a Dockerfile stage | `TestDockerfileBuildContract.test_constructor_target_stage_exists` |
| Startup file copy and sole entrypoint agree | `TestDockerfileBuildContract.test_runtime_startup_files_and_entrypoint_agree` |
| Reviewed inventory, Compose, Stage 6, and legacy installer surfaces are not baked | `TestDockerfileBuildContract.test_reviewed_inputs_and_retired_surfaces_are_not_baked` |
| Corporate trust bootstrap precedes network/package activity and is reapplied | `TestDockerfileCorporateTrustBootstrap.test_enabled_bootstrap_order_and_final_reapplication` |
| Corporate trust input is build-context visible and proxy/trust arguments are stage-scoped | Existing `TestDockerfileTrustReplacementRed` and `TestDockerfileProxyArgsRed` tests |

## Scope boundary

No image build/runtime E2E, Trivy or CVE scan, SBOM generation, or GitHub Actions implementation is part of this change. Image security scanning is planned separately in `add-container-image-security-scan`.
