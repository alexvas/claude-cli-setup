## ADDED Requirements

### Requirement: Bound assembler network and process execution
The assembler SHALL apply deterministic reviewed limits to npm registry request duration, retry count, retry delay, and total Docker-backed assembly duration. These limits SHALL be part of the fixed assembler policy identity. Exhausting npm request or retry limits SHALL produce a structured assembler failure containing bounded, redacted npm diagnostics rather than waiting indefinitely. Exceeding the constructor-owned total assembly deadline SHALL produce a timeout-specific structured operational failure.

#### Scenario: Registry request remains unresponsive
- **WHEN** a locked package request does not complete within the reviewed npm request and retry limits
- **THEN** npm assembly SHALL terminate finitely with a structured assembler failure containing bounded, redacted npm diagnostics
- **AND** SHALL NOT require Constructor to classify the npm failure as network-specific
- **AND** SHALL NOT publish the partial environment

#### Scenario: Total assembly deadline expires
- **WHEN** the assembler container remains active beyond the reviewed total assembly deadline
- **THEN** the constructor SHALL terminate the execution and force-remove the named assembler container
- **AND** SHALL report an actionable timeout failure

#### Scenario: Fixed limits affect assembler identity
- **WHEN** any reviewed npm request, retry, or total execution limit changes
- **THEN** the assembler policy identity SHALL change
- **AND** an output assembled under the prior policy SHALL NOT validate as an output of the new policy

### Requirement: Retain bounded redacted assembler diagnostics
The assembler SHALL make ongoing execution observable to an authorized text-mode caller while retaining only bounded diagnostic output. Before display, return, or persistence, diagnostics SHALL redact resolved proxy endpoints, trust paths, and caller-supplied secrets. Diagnostic collection SHALL NOT grow without bound for a long-running process.

#### Scenario: Long-running npm installation emits output
- **WHEN** npm emits progress or warnings before the assembler exits during a text-mode build
- **THEN** redacted output SHALL become visible before process completion
- **AND** the constructor SHALL retain only a bounded diagnostic tail

#### Scenario: Structured caller executes assembly
- **WHEN** assembly runs for a JSON-output build or another non-streaming caller
- **THEN** assembler output SHALL NOT be interleaved with the caller's structured stdout
- **AND** a failure SHALL include a bounded redacted diagnostic

#### Scenario: Diagnostic contains network configuration
- **WHEN** assembler output contains a configured proxy endpoint, trust path, or supplied secret
- **THEN** every displayed, returned, and persisted representation SHALL replace that value with a redaction marker

### Requirement: Distinguish canonical and serialized assembler evidence digests
The constructor SHALL retain the canonical assembler evidence-body digest as the value bound into assembled-output identity and semantic in-image verification. It SHALL separately compute and carry the SHA-256 digest of the exact serialized assembler evidence bytes used for host snapshot admission. Snapshot admission SHALL verify the serialized bytes against only the serialized-evidence digest and SHALL independently parse and validate the canonical body digest. Both digest bindings SHALL be represented in the derived build input without substituting one meaning for the other.

#### Scenario: Assembler evidence enters the build snapshot
- **WHEN** a verified assembled environment is admitted into the constructor snapshot
- **THEN** the exact evidence bytes SHALL match the serialized-evidence digest
- **AND** the parsed evidence body SHALL match its canonical evidence-body digest and assembled-output identity
- **AND** changing either digest binding SHALL invalidate the derived build input

### Requirement: Clean failed assembler executions without discarding reusable cache
On timeout, cancellation, interruption, executor failure, or nonzero exit, the assembler SHALL force-remove its named container and remove mutable staging. It SHALL preserve prior immutable published environments and the shared opaque npm download cache. Abandoned same-input staging SHALL be detected under the existing private input-identity coordination boundary and handled without adopting it as valid output.

#### Scenario: User interrupts assembly
- **WHEN** the invoking user interrupts a running assembler container
- **THEN** the container SHALL be force-removed and mutable staging SHALL be removed
- **AND** the interruption SHALL propagate to the caller

#### Scenario: Assembly fails after downloads
- **WHEN** npm downloads package bytes but assembly subsequently fails or times out
- **THEN** no partial environment SHALL be published
- **AND** safe opaque npm cache entries and prior published environments SHALL remain available

#### Scenario: Same-input staging is abandoned
- **WHEN** locked assembly encounters mutable staging left by an execution that no longer owns the coordinated operation
- **THEN** it SHALL fail closed or securely replace that staging under the input-identity lock
- **AND** SHALL NOT treat abandoned staging as evidence of a completed environment
