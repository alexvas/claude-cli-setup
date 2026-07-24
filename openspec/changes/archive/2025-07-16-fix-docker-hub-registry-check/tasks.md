## 1. Provider Endpoint Normalization

- [x] 1.1 Add focused Docker Hub alias normalization for Registry API requests.
- [x] 1.2 Apply the normalized endpoint consistently to authentication probes and manifest retrieval while preserving custom registry hosts.

## 2. Regression Coverage

- [x] 2.1 Update Docker Registry provider tests to assert that `docker.io` uses `registry-1.docker.io` and returns a digest candidate.
- [x] 2.2 Add or retain coverage proving non-Docker-Hub registry hostnames are not rewritten and missing digests remain unavailable.

## 3. Verification

- [x] 3.1 Run the focused Docker Registry provider test suite.
- [x] 3.2 Run project checks and manually verify `check-updates --only stages.base.node --no-cache` no longer receives the Docker website response.
