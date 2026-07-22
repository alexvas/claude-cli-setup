# Verification results

## Task 3.5 — prebuilt artifact performance

| Measurement | Result |
|---|---:|
| Baseline combined Cargo step (`rtk` + `fd`) | 155.4 s |
| Current `rtk-prebuilt` stage | 3.13 s |
| Current `fd-prebuilt` stage | 1.71 s |
| Current full build | 4.69 s |
| Current image export | 6.34 s |
| Runtime `/home/dev/.rustup` | 624 MB |
| Runtime `/home/dev/.cargo` | 20 MB |
| Runtime image size | 613,030,187 bytes |

The prebuilt artifact stages replace the previous sequential Cargo compilation step. The measured full build and export are substantially below the previous combined Cargo-step baseline. The independent artifact stages remain separately cacheable: changing `RTK_VERSION` rebuilt `rtk-prebuilt` while `fd-prebuilt` remained cached.
