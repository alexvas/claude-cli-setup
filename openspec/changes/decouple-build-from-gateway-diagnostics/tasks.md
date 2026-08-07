## 1. Build orchestration isolation

- [x] 1.1 Remove gateway diagnosis and `HOST_GATEWAY_IP` persistence from the build execution transaction and its build result surface.
- [x] 1.2 Preserve effective build projection publication and direct Docker build execution without gateway-dependent failure paths.
- [x] 1.3 Update build orchestration tests to prove builds neither invoke gateway callbacks nor read or mutate `.env` gateway state.

## 2. Gateway workflow boundaries

- [x] 2.1 Keep `doctor` as the explicit gateway diagnosis and rootless-repair path; update focused networking/doctor tests for the revised command ownership.
- [x] 2.2 Persist a successful `doctor` diagnosis to `.env` for fresh runtime launches, while keeping build free of `.env` access.

## 3. Documentation and verification

- [x] 3.1 Update README.md, README.en.md, and README.zh.md to separate build from gateway diagnostics and rootless repair.
- [x] 3.2 Run focused build, networking, doctor, launcher, and CLI tests plus project static checks.
