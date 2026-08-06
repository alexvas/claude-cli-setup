## 1. Update report presentation

- [ ] 1.1 Add deterministic text rendering for `check-updates` with a status summary and complete per-dependency report.
- [ ] 1.2 Route only text-mode `check-updates` results through the dedicated renderer while preserving generic rendering for other commands and the existing JSON payload.

## 2. Reviewable suggestions

- [ ] 2.1 Render `--suggest` candidates as a labelled, review-only TOML fragment after the update report.
- [ ] 2.2 Render an explicit no-suggestions message when no applicable outdated candidate exists, without producing an empty TOML block.

## 3. Verification

- [ ] 3.1 Add focused tests for default text reports, all status/detail fields, deterministic ordering, and JSON compatibility.
- [ ] 3.2 Add focused tests for applicable and empty `--suggest` text output, including no-mutation/cache-policy behavior.
- [ ] 3.3 Run focused update/facade tests and the project static checks.
