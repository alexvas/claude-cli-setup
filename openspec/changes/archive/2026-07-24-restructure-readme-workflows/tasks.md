## 1. Lock the user workflows

- [x] 1.1 Confirm `decouple-docker-build-from-runtime-mounts` and `make-version-resolver-executable` behavior is available, or adjust this change's implementation order before editing documentation
- [x] 1.2 Add RED consistency tests requiring equivalent Build, Launch, Update, Maintenance, and Troubleshooting structure in all README translations
- [x] 1.3 Add RED tests for the focused Pi update path, manual non-mutating suggestion review, grouped option semantics, validation, rebuild, verification, and extension refresh
- [x] 1.4 Add RED tests for component taxonomy, installation ownership, Debian boundary, executable commands, and safe host permission guidance without selected-version duplication

## 2. Restructure the maintained README files

- [x] 2.1 Rewrite the Russian README around the three primary actions: build the image, launch through project-selection TUI, and update managed components
- [x] 2.2 Add a component lifecycle table covering base image, toolchain, Node CLIs, prebuilt binaries, shell runtime, Pi extensions, and Debian packages
- [x] 2.3 Lead the update section with a concrete focused Pi workflow and follow it with the generalized inventory/provider workflow
- [x] 2.4 Group update options into interactive review, automation/policy, and advanced discovery/cache controls
- [x] 2.5 Consolidate image verification, mounted extension refresh, permission repair, Docker storage cleanup, and user-facing cache cleanup under Maintenance
- [x] 2.6 Replace generic Setup and obsolete troubleshooting with action-local prerequisites and focused EACCES guidance using `<docker-dev>:<docker-dev>`, `ug+rwX`, host UID/GID `100999`, and host group membership setup for rootless Docker
- [x] 2.7 Remove Python implementation/override details, detailed Dockerfile and cache-development notes, BuildKit cache experiments, shell-prompt internals, and the standalone extension section from the primary flow
- [x] 2.8 Apply equivalent information architecture and semantics to English and Chinese translations

## 3. Validate documentation

- [x] 3.1 Run documentation consistency, semantic-source, source-contract, and command-example tests
- [x] 3.2 Manually follow the documented Pi update path through non-mutating suggestion and inventory validation without applying an upstream update
- [x] 3.3 Review all translations side by side for workflow order, commands, component membership, warnings, and maintenance equivalence
- [x] 3.4 Run full local tests, strict OpenSpec validation, and `git diff --check`
