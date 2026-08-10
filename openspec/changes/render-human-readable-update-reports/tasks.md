## 1. Update report presentation

- [x] 1.1 Add deterministic text rendering for `check-updates` with a status summary and complete per-dependency report.
- [x] 1.2 Route only text-mode `check-updates` results through the dedicated renderer while preserving generic rendering for other commands and the existing JSON payload.

## 2. Reviewable suggestions

- [x] 2.1 Render `--suggest` candidates as a labelled, review-only TOML fragment after the update report.
- [x] 2.2 Render an explicit no-suggestions message when no applicable outdated candidate exists, without producing an empty TOML block.

## 3. Verification

- [x] 3.1 Add focused tests for default text reports, all status/detail fields, deterministic ordering, and JSON compatibility.
- [x] 3.2 Add focused tests for applicable and empty `--suggest` text output, including no-mutation/cache-policy behavior.
- [x] 3.3 Run focused update/facade tests and the project static checks.

## 4. Compact identifiers and publication provenance

- [ ] 4.1 Carry an optional authoritative release/version publication time from supported provider responses through candidate/result serialization; use GitHub release `published_at`, npm version time, and PyPI's earliest selected-version upload time, and leave unsupported providers unknown.
- [ ] 4.2 Render five-hex-plus-ellipsis identifier abbreviations only in text `CURRENT`/`CANDIDATE` cells, preserve `sha256:` prefixes, and render `-` for a candidate equal to current.
- [ ] 4.3 Render known publication times in `YYYY-MM-DD HH:MM:SS GMT`, unknown or malformed times as `-`, and retain full values in additive JSON fields and reviewable suggestion TOML.
- [ ] 4.4 Add focused provider, result serialization, text/JSON/TOML compatibility, and no-mutation tests; run focused update/facade tests and project static checks.
