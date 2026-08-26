## Context

The current read-through HTTP cache can return a stored response without contacting upstream, and a reviewed TTL of `None` makes that response permanent. Providers parse ordinary `HttpResponse` values, so cache provenance is currently lost before update classification and rendering. See proposal.md and the delta specs for the required behavior.

## Goals / Non-Goals

**Goals:**
- Make every explicit update check establish freshness through a full or conditional upstream request.
- Preserve a last-known-good provider-validated body for clearly marked transient fallback.
- Carry provenance from transport through provider, domain result, and renderers.
- Preserve authentication and representation isolation and strict `--no-cache` behavior.

**Non-Goals:**
- Artifact caching or retention.
- Background refresh, configurable retry loops, or serving stale data for permanent failures.
- Changing candidate selection, applicability, suggestion, or exit policies.

## Decisions

### Separate cached HTTP representation from validation provenance

Persist an envelope containing request key, auth and Accept scopes, body, response validators, `body_fetched_at`, and `validated_at`. A cache hit is no longer an early return. The transport sends validators and returns a response carrying provenance: network body, conditionally validated body, or stale fallback candidate.

Provider parsing remains authoritative. A newly fetched body is committed only after provider parsing succeeds. To avoid coupling the generic transport to each parser, the provider/coordinator acknowledges successful consumption through a cache publication boundary; malformed bodies leave the prior validated envelope intact.

Alternative considered: cache every HTTP 200 immediately. Rejected because malformed upstream data could destroy the only safe fallback.

### Define freshness as a total, separate result axis

Add immutable provenance to provider and update result DTOs with four exhaustive values: `fresh`, `stale`, `unavailable`, and `not-applicable`. `fresh` covers HTTP-derived results whose required responses are all newly fetched or validated by `304`; `stale` requires at least one used fallback plus its reason and timestamps; `unavailable` means at least one required HTTP response has no usable fresh or fallback body; `not-applicable` covers non-HTTP providers such as `git-ref` and paths that make no HTTP request. Classification consumes available bodies exactly as before. Renderers inspect provenance only after domain classification.

Alternative considered: nullable freshness scoped only to successful HTTP results. Rejected because an explicit total enum makes unavailable and non-HTTP behavior testable and avoids ambiguous field omission. Encoding stale as a new update status was also rejected because freshness and version state are orthogonal.

### Bound stale fallback to retryable failures

The transport/coordinator recognizes network exceptions, timeouts, 408, 429, and 5xx as fallback-eligible. A fresh HTTP 200 is also fallback-eligible when the owning provider cannot decode it or rejects its metadata schema and a prior validated envelope exists; the fresh body is never committed. This parser rejection is metadata validation, not artifact/checksum/signature integrity validation. Authentication, authorization, not-found, identity mismatch, and integrity failures remain visible and never trigger stale substitution.

### Aggregate provenance per required HTTP request

Treat each request made by a provider as an independent cache/parse acknowledgment unit. A GitHub release request and each checksum asset request have distinct identities and envelopes. The provider accumulates contributing provenance after parsing each response, then reduces it with precedence `unavailable > stale > fresh`; `not-applicable` is used only when no HTTP metadata request contributes. Any stale required subrequest makes an otherwise available final result stale. A required subrequest without fresh data or fallback makes the result unavailable, even if earlier subrequests were fresh or stale.

This avoids acknowledging an unparsed checksum body merely because release metadata parsed successfully and retains all stale reasons for reporting.

### Retire TTL policy without compatibility

Remove reviewed `[cache].ttl` from the inventory schema as an unknown unsupported field. Delete the legacy TTL cache implementation and discard its stored entries rather than adding a migration path. Validators determine request economy; endpoints without validators receive a full GET. `--no-cache` builds an uncached transport and disables all publication and fallback.

### Preserve compact reporting

Always serialize the four-state freshness value. Stale-only diagnostics enter `Details:` and the summary gains a stale count; unavailable continues to use existing provider diagnostics, while not-applicable adds no warning. Table columns remain unchanged. Timestamps use the existing supported UTC RFC 3339 profile.

## Risks / Trade-offs

- [Every check now makes network requests] → Use conditional validators and retain existing provider filtering.
- [Some servers return unusable validators] → Fall back to a full request and never infer freshness from age.
- [Cache publication acknowledgment complicates boundaries] → Keep a small typed response/provenance contract and test transport, provider parsing, and coordinator separately.
- [Existing TTL entries lack validation provenance] → Discard them unconditionally and repopulate the new cache after a successful parse.
- [Stale data can hide a newer release during outages] → Disclose stale state, reason, and timestamps in all output modes.

## Delivery Plan

1. Delete the TTL cache format and `[cache].ttl` policy, discarding existing TTL entries.
2. Introduce the validated-envelope format and provenance DTOs.
3. Add conditional request and provider acknowledgment behavior.
4. Propagate freshness through update results and renderers.
5. Update examples and documentation; no backward-compatible configuration or cache migration is provided.
