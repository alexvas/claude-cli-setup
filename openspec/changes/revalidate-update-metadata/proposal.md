## Why

`check-updates` can return indefinitely stale provider metadata because a cached successful HTTP response may suppress all later upstream requests. Explicit update discovery should revalidate upstream state on every run while retaining a clearly identified cached fallback when a provider is temporarily unreachable.

## What Changes

- Replace TTL-based reuse of update-discovery HTTP responses with conditional revalidation using `ETag`/`If-None-Match` and `Last-Modified`/`If-Modified-Since` when validators are available.
- Perform a full upstream request on every check when no validator is available; a cache entry never suppresses revalidation.
- Fall back to a previously validated response for transient transport failures, retryable HTTP failures, and malformed fresh provider metadata, while marking all derived results as stale and preserving the failure reason and cache provenance; artifact and cryptographic integrity failures never use stale substitution.
- Treat `304 Not Modified` as freshly validated metadata and update validation time without refetching the body.
- Expose exhaustive `fresh`, `stale`, `unavailable`, and `not-applicable` metadata freshness in structured output, aggregate multi-request provider provenance per response, and report stale fallback diagnostics in text output without changing version classification, applicability, suggestions, or exit policy.
- Keep `--no-cache` as a strict bypass that neither reads nor writes revalidation state.
- Remove the reviewed metadata TTL policy and its cache format without backward compatibility because freshness is established by revalidation rather than elapsed time.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Update discovery always contacts or conditionally revalidates each selected upstream and distinguishes fresh, stale-fallback, and unavailable metadata without changing version policy.
- `update-check-reporting`: Text and JSON reports expose stale update metadata and its reason without changing the compact table columns or serialized version status.
- `user-cache-storage`: Persistent update metadata stores validators, validated bodies, timestamps, and provenance for revalidation and stale fallback rather than TTL-based response reuse.

## Impact

Affected areas include the HTTP transport/cache contract, provider response provenance, update result DTOs, text and JSON rendering, cache persistence, `--no-cache`, inventory cache-policy removal, and deterministic transport/provider/facade tests. Existing TTL cache files are discarded and repopulated in the new format. This change depends on `add-durable-filesystem-transactions` for validated atomic envelope replacement and durable removal, but deliberately adopts neither its journal protocol nor a broad transaction lock because metadata cache entries are disposable and independently keyed.
