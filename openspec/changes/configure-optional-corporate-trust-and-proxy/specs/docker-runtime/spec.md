## ADDED Requirements

### Requirement: Inject optional local corporate network settings at launch
The constructor SHALL incorporate validated optional local corporate trust and proxy settings into the direct Docker run vector independently of runtime dependency projections and host-access policy. An enabled trust bundle SHALL be mounted as one additional read-only file at `/etc/ssl/certs/ca-certificates.crt`; a configured proxy SHALL be emitted only through the defined proxy environment-variable contract. Neither configuration SHALL expose the reviewed inventory or alter runtime artifact mount restrictions.

#### Scenario: Launching with local corporate settings
- **WHEN** a launch has valid enabled corporate trust and a valid local proxy
- **THEN** the direct Docker vector SHALL include the read-only system-trust bundle mount and required proxy environment variables
- **AND** SHALL retain the existing runtime projection and selected artifact mount behavior

#### Scenario: Launching without local corporate settings
- **WHEN** corporate trust and proxy are both absent or disabled locally
- **THEN** the direct Docker vector SHALL not include a corporate trust mount or any proxy environment variable
- **AND** SHALL preserve existing host-access behavior
