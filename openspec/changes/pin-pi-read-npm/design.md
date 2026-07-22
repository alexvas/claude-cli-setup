## Context

The Compose service bind-mounts the host `${HOME}/.pi` onto `/home/dev/.pi`. Extensions installed into `/home/dev/.pi` while building the image are therefore hidden at runtime. The current Dockerfile also installs `pi-read` directly into the image and runs `rtk init` during image assembly, before the caller's mounted Pi home exists.

## Goals / Non-Goals

**Goals:**

- Move supported Pi extension installation and rtk registration to a runtime setup script.
- Run setup against the actual mounted `/home/dev/.pi` directory.
- Support the following extensions:
  - `@llblab/pi-codex-usage`;
  - `pi-proxy`;
  - `@arcanemachine/pi-read`.
- Pin every package installation to an explicit version or immutable Git reference.
- Protect the script from modification by `dev` while allowing `dev` to execute it.

**Non-Goals:**

- Automatically installing extensions on every container start unless explicitly invoked by the runtime workflow.
- Changing extension source code or behavior.
- Keeping image-layer extension registrations that are hidden by the host mount.

## Decisions

### Use one protected setup script

Create `docker/install-pi-extensions.sh` and copy it to `/home/dev/install-pi-extensions.sh` as root-owned content. The target mode SHALL allow read and execute access for `dev` and SHALL deny write access. The script SHALL use strict shell settings, report each installation/registration, and fail on required setup errors.

### Install after the runtime home mount is available

Remove extension installation from the Dockerfile's Pi tools stage. The script must be run after `/home/dev/.pi` is mounted, so Pi's package metadata and installed extensions are written to the user's actual runtime home. The exact invocation point must be explicit in the launcher/entrypoint workflow or documented as a required setup command; silently writing to the image home is not acceptable.

### Pin extension sources

Npm-installed extensions SHALL include explicit versions in the script. Resolve and record the initial versions/revisions for all four extensions before implementation.

### Register rtk in the same workflow

Move `rtk init -g --agent pi` and telemetry disabling into the protected script, after the Pi home is mounted. Keep the operation idempotent so rerunning the script does not duplicate configuration.

## Risks / Trade-offs

- [The script is never invoked] → Add an explicit launcher/setup step and document the command; verify the mounted home after setup.
- [An extension source is unpinned] → Require version/revision discovery before implementation and fail review if any install line is floating.
- [A host `.pi` mount is unavailable] → Fail with a clear message rather than modifying image-layer content.
- [Runtime setup requires network access] → Keep the setup separate from image build and report registry/Git failures clearly.
- [The protected script is copied with the wrong mode] → Verify numeric ownership and mode in the image and ensure `dev` cannot write it.
