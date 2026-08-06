## Why

`docker-constructor.py build` currently treats a failed `host.docker.internal` probe as fatal and writes operational gateway state to `.env`, even though image construction neither uses that mapping nor requires runtime connectivity. This prevents valid rootful builds on hosts where the probe is unavailable and contradicts the build command's isolation from runtime configuration.

## What Changes

- Remove gateway diagnosis and gateway-state persistence from the build transaction.
- Keep gateway diagnosis and explicit rootless repair in `doctor`.
- Preserve runtime launch's explicit gateway mapping without making a prior build a prerequisite.
- Update documentation so build is described as independent of gateway diagnostics and `.env` mutation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `build-networking`: Move gateway diagnosis and persistence responsibility out of build and into explicit diagnostics/runtime launch preparation.
- `docker-build-reproducibility`: Guarantee that image builds do not depend on host gateway reachability or operational gateway state.

## Impact

- Affected code: `docker/versioning/build_orchestration.py`, constructor build/run orchestration, networking integration, and focused tests.
- Affected documentation: build and rootless gateway workflow guidance in all README translations.
- Build no longer writes `HOST_GATEWAY_IP` to `.env`; gateway diagnosis remains available through `doctor` and is required only where runtime connectivity needs it.
