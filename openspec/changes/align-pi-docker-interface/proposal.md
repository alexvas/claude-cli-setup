## Why

The repository has migrated its Compose service and runtime from Claude to Pi, but the build wrapper, README translations, comments, prompt filenames, and part of the OpenSpec contract still refer to the old `claude` service and obsolete build-network behavior. As a result, documented commands and `docker/build_wrapper.py build` can target a nonexistent service, while users are told to configure proxy inputs that the Dockerfile no longer consumes.

## What Changes

- Standardize the public Compose service name and all build/run commands on `pi`.
- Update the build wrapper to build the actual `pi` service.
- Remove obsolete build-network arguments and proxy claims that are no longer consumed by the Dockerfile, while retaining runtime host mapping required to reach host services.
- Rewrite Russian, English, and Chinese README sections to describe the current Pi image, included tools, launcher, build procedure, and troubleshooting commands.
- Rename or clarify remaining Claude-specific internal labels when they are no longer compatibility requirements.
- Align OpenSpec requirements with the actual Pi-oriented interface.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `build-networking`: The build wrapper targets service `pi`, and Compose only passes build-network arguments that are actually consumed while retaining the runtime host mapping.
- `docker-runtime`: User-facing documentation and shell configuration identify the environment consistently as Pi rather than the retired Claude image.

## Impact

- Affects `docker/build_wrapper.py`, `docker-compose.yml`, `.env.example`, Docker/shell comments and filenames where safe, all README translations, and existing OpenSpec specs.
- Corrects currently broken documented and wrapper-driven build commands.
- Removing unused configuration may affect users who still carry legacy `SOCKS_*` variables, but those values currently have no build effect.
