## Why

Replacement-fragment headers in text `check-updates --suggest` output blend into the surrounding TOML in ANSI-capable terminals, making manual review and block selection harder. The CLI already has a colour policy, but it does not apply it to these visual-only boundaries.

## What Changes

- Render only replacement-fragment visual comment headers (`# --- <display path> ---`) in ANSI bright black (SGR 90) when the existing colour policy permits ANSI output.
- Preserve plain headers when colour is disabled or unavailable, and preserve byte-for-byte ANSI-free JSON output.
- Keep the replacement-block section label and TOML content uncoloured so manually copied fragments remain plain apart from the terminal-only header decoration.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `docker-build-reproducibility`: Define terminal-aware presentation of visual replacement-fragment headers while preserving their plain TOML representation and all existing suggestion semantics.

## Impact

- Affects the text presentation layer in `docker/constructor_cli.py` and focused CLI rendering tests.
- Does not change inventory parsing, replacement-fragment construction, JSON payloads, update discovery, or the existing `--color` option contract.
