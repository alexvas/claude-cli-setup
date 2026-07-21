## Docker-host verification results

Verification evidence was collected from `/tmp/pi-cache-verification/` after a clean BuildKit cache reset. Runtime version checks and `docker/verify-runtime.sh pi-cli-pi:latest` passed as user `dev`.

### Build matrix

| Scenario | Pi | OpenSpec | Elapsed | Result |
|---|---:|---:|---:|---|
| Cold baseline | 0.80.10 | 1.6.0 | 524.88 s | Successful full build |
| Identical repeat | 0.80.10 | 1.6.0 | 3.49 s | All 35 deterministic Dockerfile steps reported `CACHED` |
| OpenSpec-only change | 0.80.10 | 1.5.0 | 15.02 s | OpenSpec install and required final assembly rebuilt; base, APT, Rust, uv/Python, Cargo, MCP, Pi, and pi-read remained cached |
| Pi-only change | 0.80.9 | 1.6.0 | 229.81 s | Pi and pi-read rebuilt; the independent OpenSpec 1.6.0 installation remained cached |

The identical repeat was approximately 150× faster than the cold build (99.3% elapsed-time reduction). The OpenSpec-only build was approximately 35× faster (97.1% reduction). The Pi-only build was 2.28× faster (56.2% reduction), but exposed additional final-assembly work described below.

### Cache-boundary observations

- The second identical build reused every deterministic Dockerfile step and only performed the final image export bookkeeping.
- Changing only `OPENSPEC_VERSION` executed the two `openspec-tools` steps (11.4 s total), then the late OpenSpec copy/symlink and following small final-stage steps. All unrelated expensive stages were cached.
- Changing only `PI_VERSION` executed Pi installation (6.3 s) and pi-read installation (22.2 s). The OpenSpec installation stage was cached as required.
- Because Pi is copied at the start of the linear runtime stage, a Pi change also re-executed copies of stable `.local` (1.1 s), `.rustup` (11.7 s), Cargo/MCP content, zsh setup (5.2 s), OpenSpec final assembly, and image export (54.1 s).

### Timing hotspots in the cold build

| Step | Elapsed |
|---|---:|
| Cargo install of rtk and fd | 155.4 s |
| Recursive runtime `chown -R dev:dev /home/dev` | 120.1 s |
| Base APT packages and locale | 61.9 s |
| Final image export | 57.2 s |
| Rust toolchain installation | 45.1 s |
| pi-read installation | 26.2 s |
| OpenSpec npm installation | 12.1 s |
| Copy `.rustup` into runtime | 11.6 s |

The recursive chown is tracked separately by `optimize-runtime-home-ownership` and is excluded from the follow-up opportunities below.

### Image and cache measurements

- Final image: `pi-cli-pi:latest`, 3.53 GB (`docker system df -v` reported 3.534 GB unique).
- Largest project-owned runtime layers from `docker history`:
  - `.rustup`: 1.58 GB
  - shared APT/runtime base layer: 552 MB
  - `.local` (uv, managed Python, ty): 205 MB
  - Pi prefix: 188 MB
  - Cargo binaries: 33.4 MB
  - OpenSpec prefix: 19.7 MB
  - zsh setup: 15.6 MB
- The recursive chown consumed 120.1 s but produced only a 61.4 kB metadata layer; its cost is traversal and snapshotting rather than retained image bytes.
- Total BuildKit cache: 19.47 GB; reclaimable: 13.32 GB. Large reusable cache mounts included Cargo target (822.9 MB), Cargo registry/download data (238.9 MB), and npm/other tool caches.
- A directly comparable pre-change image-size measurement was not present in the supplied logs; 3.53 GB and the layer inventory are the recorded post-change baseline for future comparisons.

### Normal BuildKit cache pruning

Cache mounts are disposable acceleration and are not required for correctness. Use normal pruning first:

```bash
# Review current usage
docker buildx du

# Interactively remove unused build cache
docker builder prune

# Remove cache not used for seven days
docker builder prune --filter 'until=168h'

# Deliberate full reset for cold-build verification or troubleshooting only
docker builder prune -af
```

The measured host had 13.32 GB reclaimable, so age-based pruning is preferable to repeatedly deleting warm Cargo/npm caches needed by normal builds.

## Follow-up optimization opportunities

These are observations, not scope additions to this completed cache-boundary change.

1. **Move stable runtime assembly before versioned Pi assembly.** Create a stable runtime ancestor containing toolchain copies, zsh, and the entrypoint; assemble OpenSpec before Pi and put the more frequently changed Pi overlay last. This avoids re-copying `.rustup` and rerunning zsh when only Pi changes. `COPY --link` should also be evaluated for independent linked layers.
2. **Reduce the Rust runtime footprint.** `.rustup` alone contributes 1.58 GB. Evaluate `rustup --profile minimal` and add only runtime-required components; retain clippy/rustfmt explicitly if the developer contract requires them. This also reduces copy and export time.
3. **Split rtk and fd installation boundaries.** Their combined Cargo step costs 155.4 s. Independent pinned stages/RUN steps would allow parallelism and prevent an rtk-only update from rebuilding fd (and vice versa). Published prebuilt artifacts may be faster if their integrity can be verified.
4. **Avoid repeated pi-read network installation.** pi-read costs 22–26 s on each Pi change. Pin its immutable revision and evaluate a git/download cache or an independently prepared package artifact while preserving Pi compatibility checks.
5. **Audit shared base packages.** The base APT layer is 552 MB. Confirm whether compilers, headers, `rpm`, and other large packages must be in the interactive runtime; move genuinely build-only dependencies into `toolchain` without reducing the documented developer toolset.
6. **Reduce export cost through image-size work.** Export takes 54–57 s for a 3.53 GB image. The Rust profile and base-package audits offer the largest likely reductions; smaller runtime layers will also reduce storage duplication across Pi/OpenSpec variants.
7. **Collapse trivial metadata layers where cache boundaries are not useful.** Use `COPY --chmod=755` for setup/entrypoint scripts and combine adjacent stable symlink/setup operations where doing so does not broaden invalidation.
