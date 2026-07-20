## 1. Align executable interfaces

- [ ] 1.1 Change the build wrapper and its messages from nonexistent service `claude` to service `pi`
- [ ] 1.2 Audit Dockerfile and Compose build-network arguments and remove `SOCKS_PORT`, `SOCKS_HOST`, `EXTERNAL_IP`, and build-only gateway plumbing that has no consumer
- [ ] 1.3 Preserve and verify runtime `HOST_GATEWAY_IP` persistence and `host.docker.internal` mapping for host-service access
- [ ] 1.4 Update script docstrings, comments, and diagnostics to describe Pi and runtime host reachability accurately

## 2. Migrate shell identity

- [ ] 2.1 Introduce a Pi-oriented prompt fragment path and update generated shell configuration and comments
- [ ] 2.2 Add a safe legacy prompt fallback or migration path and prefer the new path when both exist
- [ ] 2.3 Verify zsh starts and loads the expected prompt fragment as user `dev`

## 3. Rewrite maintained documentation

- [ ] 3.1 Rewrite `README.md` to describe the current Pi image, Compose service, launcher, tools, configuration, build/run commands, and troubleshooting
- [ ] 3.2 Apply equivalent supported content and commands to `README.en.md`
- [ ] 3.3 Apply equivalent supported content and commands to `README.zh.md`
- [ ] 3.4 Remove references to retired Claude files, variables, targets, services, CLI commands, and SOCKS build bootstrap behavior
- [ ] 3.5 Document removal of inert legacy environment variables and any shell prompt migration behavior

## 4. Validate consistency

- [ ] 4.1 Search maintained code, specs, and documentation for unintended `claude` service/CLI and obsolete build-proxy references
- [ ] 4.2 Statically validate Python and shell scripts and ensure all documented repository paths exist
- [ ] 4.3 On a Docker host, run `docker compose config` and confirm only service `pi` and required runtime host mapping are present
- [ ] 4.4 On a Docker host, run the wrapper build path and documented Pi build/run smoke commands
- [ ] 4.5 Run launcher dry-run mode and confirm it continues to target service `pi`
