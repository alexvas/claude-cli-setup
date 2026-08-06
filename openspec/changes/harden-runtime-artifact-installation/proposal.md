## Why

Runtime artifacts are currently assumed to be npm tarballs by the installer without carrying that format contract in the container-safe runtime DTO. The direct extraction path also writes into the live package directory, which can leave partial or stale package contents after an interrupted or failed install.

## What Changes

- Add an explicit runtime artifact/install type to the reviewed selection and container-safe runtime projection.
- Support and assert the `npm-tarball` type for every current runtime extension; reject unsupported types before extraction.
- Make npm-tarball installation transactional: validate and extract into private staging, then replace the target package directory only after validation succeeds.
- Reject malformed npm tarballs that do not have the required `package/` layout and package metadata.
- Improve acceptance-evidence provenance by recording the offline wrapper/policy used and reliably identifying the inspected launch container.

## Capabilities

### New Capabilities
- `runtime-artifact-installation`: Typed, transactional installation of verified mounted runtime artifacts.

### Modified Capabilities
- `docker-runtime`: Runtime projections carry the selected artifact installation type and runtime installation rejects unsupported or malformed artifact formats.

## Impact

Affected areas include `docker/versioning` runtime selection/projection serialization, `docker/runtime_installer.py`, constructor rendering/validation, installer and orchestration tests, and Docker acceptance-evidence scripts. Current reviewed runtime entries remain npm artifacts; no new public facade command is introduced.
