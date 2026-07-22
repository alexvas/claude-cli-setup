# Verification results

Date: 2026-07-21

## Startup repair scope (task 4.4)

Verified with temporary Docker bind mounts and `CHOWN_WORK_ON_START=1`:

- host-directory `PROJECT_PATH_*` mounts are repaired to `dev:dev` with `ug+rwX`;
- unmounted `PROJECT_PATH_*` paths are not traversed or modified;
- the supported `/home/dev/.pi` mount is repaired to `dev:dev` with `ug+rwX`;
- non-project mounts such as `/home/dev/.cargo` remain unchanged;
- Git safe-directory registration remains limited to repaired project paths.

## Runtime assembly performance (task 4.5)

Evidence logs are in `/tmp/pi-ownership-verification/`.

| Measurement | Result |
|---|---:|
| Previous whole-home `chown -R dev:dev /home/dev` | approximately 120 s |
| Previous Pi-only build baseline | 229.81 s |
| Current targeted runtime ownership step | 0.2 s (`RUN chown dev:dev` roots only) |
| Current Pi-only build | 101.78 s |
| Current cached/fixed build | 2.83 s |

The current build logs contain no runtime `chown -R dev:dev /home/dev`. The runtime ownership step changes only destination roots (`.pi`, `.local`, `.rustup`, `.cargo`, `.cargo/bin`, and `mcp`); it does not recursively traverse their contents.

## Runtime verification

`docker/verify-runtime.sh pi-cli-pi:latest` passed:

```text
ownership ok
mount detection ok
ALL CHECKS PASSED
runtime tool and PATH checks passed for pi-cli-pi:latest
```
