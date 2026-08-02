## 1. Establish Removal Contracts

- [x] 1.1 Confirm `replace-compose-with-direct-docker` has completed protected entrypoint installation, ownership repair, rtk registration, and focused validation before removing the compatibility endpoint.
- [x] 1.2 Add failing image/source contract tests asserting that `docker/install-pi-extensions.sh` and `/home/dev/install-pi-extensions.sh` are absent.
- [x] 1.3 Replace wrapper-oriented tests with failing contracts for constructor-managed entrypoint installation, mounted-home rejection, package metadata/ownership validation, and rtk setup.

## 2. Remove the Wrapper

- [x] 2.1 Delete `docker/install-pi-extensions.sh`.
- [x] 2.2 Remove the wrapper `COPY`, ownership, and mode setup from `Dockerfile` while retaining the protected Python installer modules required by the entrypoint.
- [x] 2.3 Verify the entrypoint remains the only image startup path that invokes protected extension installation and does so as `dev` after root-owned Pi-home repair.

## 3. Migrate Runtime Verification

- [x] 3.1 Update `docker/verify-runtime.sh` to verify automatic extension installation outcomes and assert that the legacy image path is absent.
- [x] 3.2 Update Stage 6 evidence and host-script tests to launch through the constructor-managed runtime path instead of executing `/home/dev/install-pi-extensions.sh`.
- [x] 3.3 Update semantic-source and source-contract tests to inspect `docker/runtime_installer.py` and `docker/entrypoint.sh`, removing shell-wrapper allowlists and assumptions.
- [x] 3.4 Add or retain failure-path coverage proving a missing Pi-home mount, failed integrity check, failed package installation, failed metadata/ownership validation, or failed rtk setup prevents Pi launch.

## 4. Update Live Contracts and Documentation

- [x] 4.1 Remove manual wrapper commands from `README.md`, `README.en.md`, and `README.zh.md`; document `docker/docker-constructor.py run` as the supported setup path.
- [x] 4.2 Update maintained OpenSpec diagrams and prose that identify `install-pi-extensions.sh` as the current installer, without rewriting archived changes.
- [x] 4.3 Remove or update current inventory fixture comments and other non-archived live references to the deleted wrapper.
- [x] 4.4 Search the repository for `install-pi-extensions.sh` and `/home/dev/install-pi-extensions.sh`; ensure remaining matches are limited to historical archives or this removal change.

## 5. Validate the Breaking Migration

- [x] 5.1 Run focused constructor runtime-installer, entrypoint, source-contract, documentation, runtime verification, and Stage 6 host-script tests without Docker or network where fakes are available.
- [x] 5.2 Run shell/static checks, Python compile checks, and `git diff --check`.
- [x] 5.3 Run the full non-Docker test suite and record or resolve all regressions caused by removal of the wrapper contract.
- [x] 5.4 Build and inspect the runtime image when Docker is available, proving the legacy path is absent and constructor-managed launch still installs/validates extensions and rtk configuration.
- [x] 5.5 Run `openspec validate remove-install-pi-extensions-wrapper --strict` and confirm all tasks, delta requirements, docs, and implementation agree.
