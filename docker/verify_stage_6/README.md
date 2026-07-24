# Stage 6 host verification

Each task script runs independently and writes command logs plus `evidence.json`
under `/tmp/pi-stage6/<task>` by default.

```bash
python3 docker/verify_stage_6/task_6_2.py
python3 docker/verify_stage_6/task_6_3.py
python3 docker/verify_stage_6/task_6_4.py
python3 docker/verify_stage_6/task_6_5.py
python3 docker/verify_stage_6/task_6_6.py
```

Use `--dry-run` to inspect commands without invoking Docker.

Task 6.3 preserves the image previously referenced by `pi-cli-pi:latest`: it
builds and tags the experimental override image, then restores the default tag.
Tasks 6.4 and 6.6 recreate their own `<output-dir>/pi-home`, install all
inventory-configured extensions, and then mount it read-only for acceptance.
An explicitly supplied `--pi-home` is reused and is never deleted. Use
`--skip-extension-install` only when that explicit directory is complete.
Task 6.5 does not require a Pi home.

## Inputs

- `inputs/python-3.14.5.toml`: isolated experimental default/policy used by
  task 6.3 to build the available `3.14.6` as an override and by task 6.5 as
  the Python toolchain cache-invalidation case. It is not the normative
  project policy and must not replace `/versions.toml`.
- `inputs/bad-rtk-sha256.toml`: structurally valid wrong checksum for Docker
  rejection testing.
- `inputs/bad-node-digest.toml`: structurally valid wrong base digest.
- `inputs/cache-rust-profile.toml`: Rust profile cache invalidation case.
- `inputs/cache-runtime-extensions.toml`: runtime-inventory-only invalidation
  case.

Task 6.5 accepts additional valid cases:

```bash
python3 docker/verify_stage_6/task_6_5.py \
  --case openspec=/path/to/valid-openspec-case.toml \
  --case rtk=/path/to/valid-rtk-case.toml
```
