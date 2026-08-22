## Why

`check-updates --suggest` currently emits only candidate leaf values under a repeated target table, which neither matches the complete reviewed block stored in the inventory nor can be appended to it as valid TOML. Operators need a compact, visually identifiable replacement fragment that can be reviewed and manually substituted for the corresponding complete configuration block without losing unchanged policy or platform settings.

## What Changes

- Replace candidate-only text suggestions with complete canonical TOML replacement fragments grouped by replaceable inventory block rather than individual update target.
- Build each fragment from the complete raw reviewed block, apply every applicable candidate affecting that block, and retain unchanged source, update-policy, override, validation, and non-updated platform artifact fields.
- Add a concise visual comment header before every replacement block; the header strips only leading `build.stages.` or `runtime.` from its display path while all TOML table headers remain complete canonical paths.
- Add matching visual block headers to the repository canonical `docker-constructor.toml` during migration; headers remain optional and non-semantic for other inventories.
- Preserve read-only operation, full candidate values, applicability policy, structured JSON suggestion data, result ordering, provider behavior, and exit-policy behavior.
- Preserve the explicit no-suggestion result when no applicable update exists.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `docker-build-reproducibility`: Replace candidate-only review suggestions with manually replaceable complete reviewed inventory blocks while retaining non-mutating update discovery.

## Impact

- Affects update suggestion construction and text rendering in `docker/versioning/updates.py` and `docker/constructor_cli.py`, plus raw inventory access needed to reconstruct reviewed blocks.
- Updates the canonical inventory comments, suggestion tests, CLI/read-only tests, documentation, and semantic scans.
- Does not add automatic application, inventory mutation, a patch format, external dependencies, or provider/network behavior changes.
