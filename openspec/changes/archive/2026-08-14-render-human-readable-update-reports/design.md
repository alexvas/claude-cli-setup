## Context

`check-updates` produces a structured `CommandResult` containing complete per-target records and, in suggestion mode, structured candidate changes. The generic text renderer has no command-specific handling and falls back to Python dictionary formatting. The update module already owns deterministic table and TOML suggestion renderers, while JSON consumers depend on the existing structured payload.

## Goals / Non-Goals

**Goals:**
- Provide a concise text summary plus an aligned, deterministic per-target update report.
- Render `--suggest` as a visibly separate TOML fragment containing only applicable outdated candidates.
- Keep JSON output, provider discovery, filtering, exit codes, and non-mutating suggestion behavior unchanged.
- Keep domain result serialization independent from terminal presentation.

**Non-Goals:**
- Applying suggestions automatically or editing the inventory.
- Changing update selection, applicability rules, cache policy, or provider protocols.
- Redesigning text output for unrelated constructor commands.

## Decisions

### Add command-aware text presentation at the facade boundary

The facade SHALL recognize the `check-updates` result shape and render it through dedicated presentation helpers rather than `str(dict)`. This retains the read-only service as a structured-domain boundary and avoids making it depend on terminal output. The generic renderer remains the fallback for other commands.

Alternative: return a pre-rendered string from the service. Rejected because it would entangle machine-oriented domain data with text formatting and risk JSON drift.

### Reuse canonical update renderers and add a summary

The implementation SHALL use the update result records to render a stable summary and table. It SHALL reuse or adapt the existing table renderer, including safe handling for absent current values, candidates, and reasons. Summary counts SHALL make the number of applicable outdated items immediately visible while preserving statuses in the table.

Alternative: print only outdated entries. Rejected because unavailable, skipped, and inapplicable records provide important review context.

### Compact display identifiers without weakening machine or review values

The text table SHALL shorten a plain hexadecimal revision, digest, or checksum to its first five hexadecimal characters followed by `...`. A `sha256:`-prefixed digest SHALL retain its prefix and shorten only its hexadecimal payload. When the candidate is exactly equal to the current value, the text table SHALL render the candidate as `-` rather than repeat it. These are presentation-only transformations: JSON and reviewable TOML suggestions retain complete values.

### Carry authoritative publication time as optional provenance

Providers MAY supply an authoritative release/version publication time. It SHALL mean the publication time of the selected release or version, not HTTP response time, cache time, Git commit time, or a later supplemental artifact upload time. The canonical structured result carries it as an optional UTC RFC 3339 value and JSON exposes it additively without shortening. Text output renders a known value as `YYYY-MM-DD HH:MM:SS GMT` and an absent, unavailable, or malformed upstream value as `-`; optional time metadata MUST NOT change update selection, applicability, or command success.

GitHub-release and uv-python candidates can use the GitHub release `published_at` value; npm can use the registry version publication time; PyPI can use the earliest upload time for the selected version as that version's publication time. The supported timestamp profile is `YYYY-MM-DDTHH:MM:SS[.fraction](Z|+00:00)`, with one through six fractional digits when present; lowercase `t`/`z`, leap seconds, `-00:00`, non-zero offsets, and higher-precision fractions are unknown. Providers without authoritative version/release publication time report no value.

### Treat suggestions as review-only TOML

When `--suggest` is present, text output SHALL append a labelled TOML fragment generated only from applicable outdated results. It SHALL state that the fragment is not applied automatically. When no candidate is applicable, it SHALL say so rather than emit an ambiguous blank block.

Alternative: print the serialized `suggestions` mapping. Rejected because it is not copyable TOML and duplicates JSON-oriented structure.

## Risks / Trade-offs

- [Long paths can make terminal tables wide] → use deterministic columns and permit normal terminal wrapping rather than truncating data; compact only identifier cells in text mode.
- [Presentation helpers could diverge from JSON] → derive both from the existing canonical serialized/result model and cover both modes with focused tests; JSON and TOML retain complete identifiers.
- [Publication dates vary by provider] → expose only authoritative release/version dates and render `-` rather than infer one from a response, cache, commit, or artifact timestamp.
- [A TOML fragment might be mistaken for an automatic update] → label it explicitly as review-only and preserve the no-mutation guarantee.

## Migration Plan

No data migration is required. Replace text-mode presentation, add optional publication provenance to structured results, and add regression tests for default and suggestion output. Rollback consists of reverting the presentation change; existing JSON fields and inventory remain untouched.

## Open Questions

None.
