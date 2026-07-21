## 1. Update base image

- [x] 1.1 Change the `FROM` line in the Dockerfile `base` stage from `node:24-bookworm-slim` to `node:24-trixie-slim`

## 2. Verify the build

- [x] 2.1 Perform a clean Docker build and confirm all `apt-get install` packages resolve from Debian 13 (Trixie)
- [x] 2.2 Run `./docker/verify-runtime.sh` and confirm all tools execute correctly on the Trixie base
- [x] 2.3 Confirm `node --version` still reports Node.js 24 inside the image
