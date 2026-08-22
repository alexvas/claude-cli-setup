## Context

Replacement fragments are constructed as plain TOML text by the update-rendering layer, while the CLI facade later selects text versus JSON and already resolves the `--color` policy against the destination stream. The fragment boundary is a visual TOML comment, not inventory metadata.

## Goals / Non-Goals

**Goals:**
- Apply terminal-only gray styling to replacement-fragment comment headers when the existing policy enables ANSI.
- Preserve the plain fragment content for disabled colour, non-TTY automatic output, and JSON.

**Non-Goals:**
- Styling the replacement-block section label, TOML tables, or TOML values.
- Changing colour policy options, fragment construction, inventory content, or machine-readable output.

## Decisions

### Decorate at the CLI presentation boundary

The facade SHALL identify visual fragment-header lines after obtaining the plain text report and wrap only those lines with SGR 90 and reset sequences when its existing colour decision for the target stream is true — stdout for success/policy results, stderr for error results. This keeps `updates.py` output canonical, parseable, and independent of terminal capabilities.

Alternatives considered:
- **Emit ANSI from replacement-fragment construction**: rejected because it contaminates a domain-level TOML representation and cannot respect the target stream.
- **Style the entire suggestion section**: rejected because only block boundaries need visual separation and TOML remains intended for manual copying.

### Reuse the existing `--color` policy

`auto` follows the target stream's TTY detection (stdout for success/policy, stderr for errors), `always` enables styling irrespective of TTY detection, and `never` leaves headers plain. JSON does not take the text-rendering path and remains unchanged. No new flag or environment contract is introduced.

### Use SGR 90 for gray

SGR 90 is the agreed bright-black ANSI code and directly expresses the requested gray header styling. A reset sequence SHALL immediately follow each header so no TOML text inherits the style.

## Risks / Trade-offs

- [ANSI sequences could be copied from a terminal] → Styling is limited to headers; plain output remains available through `--color never`, and default automatic mode avoids ANSI for redirected output.
- [Terminal themes vary in how bright black appears] → Use the explicit standard SGR 90 requested for this change rather than introducing theme detection.

## Migration Plan

No migration is required. The change is presentation-only; reverting restores unstyled plain headers without affecting inventories or JSON consumers.
