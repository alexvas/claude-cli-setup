## MODIFIED Requirements

### Requirement: Repair mount ownership on startup
The system SHALL be able to fix ownership of mounted work directories before dropping privileges.

#### Scenario: CHOWN_WORK_ON_START enabled
- **WHEN** the container starts as root and `CHOWN_WORK_ON_START` is `1` or `true`
- **THEN** the entrypoint SHALL recursively scan each configured `PROJECT_PATH_*` directory and only change ownership for files and directories that are not owned by `dev:dev`
- **AND** the recursive scan SHALL NOT follow symbolic links
- **AND** marks each mounted git directory as a global safe directory for user `dev`
- **AND** the entrypoint SHALL apply the same selective ownership repair to `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, and `/home/dev/.npm-global`
- **AND** finally executes the requested command as `dev`
