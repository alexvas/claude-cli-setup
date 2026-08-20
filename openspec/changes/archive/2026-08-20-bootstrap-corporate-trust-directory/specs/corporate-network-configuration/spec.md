## MODIFIED Requirements

### Requirement: Apply enabled trust at build and restarted runtime
When corporate trust is enabled, the Dockerfile SHALL validate the fixed complete bundle, ensure the parent directory for `/etc/ssl/certs/ca-certificates.crt` exists, and replace that system bundle before image-stage network operations. Pre-network parent-directory bootstrap SHALL be scoped to enabled corporate trust. When corporate trust is disabled, the constructor SHALL NOT perform that bootstrap or install a constructor-provided replacement bundle before the first network operation. The constructor SHALL bind-mount the same current host file read-only at that path for each launched container. A restarted or newly launched container SHALL receive a changed bundle without rebuilding the image; already-running containers and processes SHALL not be required to reload it. Any certificate-path or client-specific CA setting introduced by the constructor SHALL be scoped to enabled corporate trust and SHALL point to the replacement system bundle.

#### Scenario: Build bootstraps enabled corporate trust before package downloads
- **WHEN** an enabled trust bundle is used to build an image whose base does not contain `/etc/ssl/certs`
- **THEN** the Dockerfile SHALL validate the bundle before creating the missing parent directory
- **AND** SHALL create the parent directory before replacing the system CA bundle
- **AND** base-stage networked package and installer operations SHALL run after the system CA bundle replacement
- **AND** the final image SHALL contain the replacement bundle

#### Scenario: Disabled trust skips pre-network directory bootstrap
- **WHEN** corporate trust is absent or disabled and the base image does not contain `/etc/ssl/certs`
- **THEN** the constructor SHALL NOT create that directory as part of the corporate-trust bootstrap before the first network operation
- **AND** SHALL NOT install a constructor-provided replacement bundle
- **AND** this restriction SHALL NOT prohibit normal package installation from creating or populating the standard trust directory later in the build

#### Scenario: Runtime receives an updated bundle after restart
- **WHEN** the fixed host bundle changes after an image was built and a container is subsequently launched or restarted
- **THEN** the container SHALL receive the current file as a read-only mount at the system CA bundle path
- **AND** the image SHALL not need rebuilding for that launch
