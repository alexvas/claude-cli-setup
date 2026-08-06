## 1. Build orchestration isolation

- [ ] 1.1 Remove gateway diagnosis and `HOST_GATEWAY_IP` persistence from the build execution transaction and its build result surface.
- [ ] 1.2 Preserve effective build projection publication and direct Docker build execution without gateway-dependent failure paths.
- [ ] 1.3 Update build orchestration tests to prove builds neither invoke gateway callbacks nor read or mutate `.env` gateway state.

## 2. Gateway workflow boundaries

- [ ] 2.1 Keep `doctor` as the explicit gateway diagnosis and rootless-repair path; update focused networking/doctor tests for the revised command ownership.
- [ ] 2.2 Verify runtime run-vector gateway mapping continues to use operational configuration independently of whether a build has run.

## 3. Documentation and verification

- [ ] 3.1 Update README.md, README.en.md, and README.zh.md to separate build from gateway diagnostics and rootless repair.
- [ ] 3.2 Run focused build, networking, doctor, launcher, and CLI tests plus project static checks.
