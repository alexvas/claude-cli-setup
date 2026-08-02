## 1. RED: Build-verification contracts

- [ ] 1.1 Add failing inventory/effective-projection tests requiring Node `24.18.0-trixie-slim` with the current digest.
- [ ] 1.2 Add build-verification tests showing an exact Node tag and matching `node --version` pass, while a floating major tag is rejected as not exact-verifiable.
- [ ] 1.3 Add a failing rustfmt fixture where Rust `1.97.1` has rustfmt installed through its rustup toolchain but `rustfmt --version` reports `1.9.0-stable`.
- [ ] 1.4 Add failing rustfmt provenance fixtures for a missing component, a binary outside the configured toolchain, malformed rustup output, and a mismatched toolchain.
- [ ] 1.5 Confirm conditional rustfmt/clippy checks remain absent when the corresponding components are not configured.
- [ ] 1.6 Run focused verification tests and confirm failures reach the intended expectation/provenance boundaries without Docker.

## 2. GREEN: Exact Node and rustfmt provenance verification

- [ ] 2.1 Update `docker-constructor.toml` to pin `tag = "24.18.0-trixie-slim"` while retaining digest `sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573`.
- [ ] 2.2 Update Node expected-value extraction to require an exact semver tag and produce a clear verification failure for floating tags.
- [ ] 2.3 Replace rustfmt numeric-version equality with rustup component/path provenance checks for the configured effective Rust toolchain.
- [ ] 2.4 Preserve `rustc`, `cargo`, clippy, and non-Rust build-tool contracts, including existing injected runner behavior.
- [ ] 2.5 Improve mismatch details to report expected toolchain/path facts and observed rustup output without leaking unrelated data.
- [ ] 2.6 Update generated-projection and verifier test fixtures for the exact Node tag and independent rustfmt banner.
- [ ] 2.7 Re-run focused tests until green.

## 3. INTROSPECT: Reproducibility review

- [ ] 3.1 Verify the resolved Node image tag and digest remain declarative inventory inputs rendered through `NODE_BASE_IMAGE`, without Dockerfile hard-coding.
- [ ] 3.2 Verify Node comparison is exact-semver based and cannot silently pass arbitrary `24.x` images.
- [ ] 3.3 Verify rustfmt passes only when supplied by the configured rustup toolchain and installed as its component, independent of banner version numbering.
- [ ] 3.4 Verify component checks remain conditional and diagnostics preserve expected/observed facts.
- [ ] 3.5 Confirm runtime verification, launcher behavior, extensions, projection identity, and evidence behavior are unchanged.

## 4. VALIDATE: Automated and Docker-host checks

- [ ] 4.1 Run focused inventory, effective-projection, and constructor build-verification tests.
- [ ] 4.2 Run the complete unit suite with `python3 -m unittest discover -s tests -q`.
- [ ] 4.3 Run `python3 -m compileall -q docker tests`.
- [ ] 4.4 Run `openspec validate fix-build-verification-rustfmt-node-tag --strict` and `git diff --check`.
- [ ] 4.5 On a Docker host, rebuild the image through the facade and run `verify --scope build` against the rebuilt exact image.
- [ ] 4.6 Confirm Node `v24.18.0`, rustc/cargo `1.97.1`, rustfmt rustup path/component provenance, clippy, and all other configured build checks pass.
