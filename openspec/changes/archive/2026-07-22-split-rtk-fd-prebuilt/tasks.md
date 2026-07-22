## 1. Pin and fetch release artifacts

- [x] 1.1 Add `RTK_VERSION` with default `v0.43.0`, its official amd64 release URL, and SHA-256 digest
- [x] 1.2 Add `FD_VERSION` with default `v10.4.2`, its official amd64 release URL, and SHA-256 digest
- [x] 1.3 Create independent `rtk-prebuilt` and `fd-prebuilt` Docker stages that download, verify, and extract only their executables

## 2. Replace Cargo compilation and assemble runtime

- [x] 2.1 Remove the combined Cargo installation of `rtk` and `fd-find` from the toolchain stage
- [x] 2.2 Copy the verified `rtk` and `fd` executables into the runtime image from their independent artifact stages
- [x] 2.3 Preserve `rtk init -g --agent pi`, disable telemetry, and ensure generated integration files have `dev` ownership
- [x] 2.4 Keep runtime assembly network-free and preserve existing PATH and command locations

## 3. Verify correctness, cache behavior, and performance

- [x] 3.1 Extend build/runtime verification with pinned `rtk` and `fd` version assertions
- [x] 3.2 Verify checksum mismatch fails the corresponding artifact stage
- [x] 3.3 Build default and custom UID/GID images and run the existing runtime verification successfully
- [x] 3.4 Rebuild with only RTK or FD pins changed and confirm the other artifact stage remains cached
- [x] 3.5 Record build-time, image-size, and runtime-export improvements against the approximately 155.4-second combined Cargo baseline
- [x] 3.6 Run strict OpenSpec validation and all available project checks
