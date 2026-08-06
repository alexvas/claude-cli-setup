## ADDED Requirements

### Requirement: Install typed mounted runtime artifacts transactionally
The container installer SHALL dispatch every configured mounted runtime artifact by its closed `install_type` and SHALL reject an unsupported type before modifying the mounted Pi home. The only supported type in this change is `npm-tarball`.

#### Scenario: Rejecting an unsupported installation type
- **WHEN** a runtime projection declares an install type other than `npm-tarball`
- **THEN** projection validation or protected installation SHALL fail before extracting an artifact or modifying the target package directory

#### Scenario: Installing a valid npm tarball
- **WHEN** a verified mounted artifact is declared as `npm-tarball`
- **THEN** the installer SHALL extract only the npm `package/` payload into private staging beneath the target node_modules parent
- **AND** it SHALL validate the declared metadata file, package identity, and exact version in staging before publishing it
- **AND** it SHALL replace the target package directory without retaining stale files from a prior installed version

#### Scenario: Rejecting a malformed npm tarball
- **WHEN** an `npm-tarball` artifact has an unsafe or non-`package/` member, lacks the declared metadata file, or has malformed or mismatched package metadata
- **THEN** the installer SHALL fail without replacing the existing target package directory

#### Scenario: Recovering a failed package replacement
- **WHEN** target directory replacement fails after a prior package directory was preserved
- **THEN** the installer SHALL restore the prior directory when possible
- **AND** it SHALL report the failure without treating the extension as installed
