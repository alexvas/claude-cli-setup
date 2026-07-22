## 1. Create the protected extension setup script

- [x] 1.1 Resolve and record explicit versions/revisions for `@llblab/pi-codex-usage`, `pi-proxy`, and `@arcanemachine/pi-read`
- [x] 1.2 Create `docker/install-pi-extensions.sh` with strict mode, mounted-home checks, idempotent extension setup, and actionable errors
- [x] 1.3 Install or register all supported extensions from the script, using explicit npm versions or immutable Git references
- [x] 1.4 Move `rtk init -g --agent pi` and telemetry disabling into the script

## 2. Integrate and protect the script

- [x] 2.1 Remove Pi extension installation and rtk registration from `Dockerfile`
- [x] 2.2 Copy the script to `/home/dev/install-pi-extensions.sh` as `root:root` with read/execute permission for `dev` and no write permission
- [x] 2.3 Add or update the runtime/launcher workflow and documentation to invoke the script after `/home/dev/.pi` is mounted
- [x] 2.4 Preserve existing Pi, extension, and rtk behavior when the script is rerun

## 3. Verify mounted runtime setup

- [x] 3.1 Build the default image and verify the protected script's ownership and mode
- [x] 3.2 Run the script with the host `.pi` mount and confirm all extensions and rtk integration are present
- [x] 3.3 Confirm the script refuses to write image-layer `.pi` when the mount is absent
- [x] 3.4 Change one extension pin and confirm unrelated image stages remain cached
- [x] 3.5 Run strict OpenSpec validation and all available project checks
