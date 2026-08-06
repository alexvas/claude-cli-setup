## Context

The host cache already treats a selected artifact as immutable verified bytes and mounts it as an individual read-only file. The container installer currently interprets every mounted artifact as an npm gzip tarball implicitly and extracts it directly into the live Pi npm package directory. That couples the DTO to an unstated format and permits a failed extraction or replacement to leave a mixed package tree.

The current runtime inventory contains only npm package tarballs. Future runtime artifact formats must not be inferred from URLs or archive bytes. Acceptance collection also needs evidence that a declared offline policy was actually selected and must avoid choosing an unrelated concurrently started container with the same image.

## Goals / Non-Goals

**Goals:**
- Carry an explicit, closed install type from reviewed runtime selection to the container projection.
- Implement only `npm-tarball` now and reject every other type before package mutation.
- Transactionally replace an npm package directory only after archive layout and metadata validation.
- Make offline-policy and container-selection evidence attributable to the launch under test.

**Non-Goals:**
- Support a second artifact format, infer formats, or add a general package manager.
- Change the content-addressed cache, network ownership, public constructor commands, or existing reviewed runtime versions.
- Make acceptance scripts a required end-user workflow.

## Decisions

### Closed `install_type` in the runtime DTO

The reviewed runtime model, host effective selection, projection DTO, serializer, and parser will expose an explicit `install_type`. The only accepted value is `npm-tarball`; the installer asserts it before reading or extracting archive bytes. Unknown values fail projection validation or installer execution before the Pi home is changed.

A type field is chosen over URL suffix/content sniffing because the reviewed inventory owns artifact semantics and content inspection is ambiguous and may occur too late. A future format extends the closed enum and adds a separately tested installer.

### Stage, validate, then replace npm packages

For an npm artifact, the installer will create a package-specific staging directory under the same `node_modules` parent, extract only safe `package/` entries there, require the declared metadata file, and validate its JSON name and exact version. It will then replace the target directory by same-filesystem rename with rollback handling that preserves the prior installed package if publication fails. The final ownership validation remains after replacement.

Direct extraction is rejected because it can merge new and old files and expose partial output. Copying between arbitrary temporary locations is rejected because it loses rename atomicity.

### Strict npm archive contract

The npm installer accepts only a gzip tar whose relevant members are rooted beneath `package/`; entries outside that root, unsafe member types/paths, missing metadata, malformed metadata, or metadata not matching the projected package/version fail before target replacement. `tarfile` safety filtering remains defense in depth rather than the format contract.

### Evidence launch identity and offline provenance

The coordinator will write the selected offline wrapper path and a clearly labelled policy record into scenario 02 before invocation. The single-launch collector will pass a unique per-run Docker label through the constructor render path or otherwise derive a unique launch identifier, then inspect only the matching container. It will record that identifier alongside the observed container ID.

Using image ancestry alone is rejected because concurrent launches of the same image can be mistaken for the evidence launch.

## Risks / Trade-offs

- [Directory replacement briefly changes the package path] → Perform the swap before Pi starts and retain/restore the previous directory on failed replacement.
- [Tarball validation rejects unusual but technically extractable archives] → Limit accepted layout to the npm pack contract used by all current reviewed artifacts and cover it with fixtures.
- [An offline wrapper can still implement an ineffective policy] → Record the selected wrapper and policy assertion; the wrapper remains caller-owned host policy.
- [Container labels affect render plumbing] → Use a private, deterministic internal label and ensure user-facing command semantics are unchanged.
