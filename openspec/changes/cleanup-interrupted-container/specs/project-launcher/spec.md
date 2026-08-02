## ADDED Requirements

### Requirement: Clean up a direct Docker launch when the facade is terminated
The launcher SHALL handle host-sent `SIGTERM` to the active facade by terminating the exact container owned by the current launch, reaping the attached Docker client, and cleaning the launch's ephemeral runtime projection without affecting any other container.

#### Scenario: Host sends SIGTERM to an active facade
- **WHEN** the host sends `SIGTERM` to the facade during an attached interactive launch
- **THEN** the launcher force-removes the container using the exact allocated `pi-N` name
- **AND** reaps the attached `docker run` client
- **AND** attempts container removal before deleting the runtime projection
- **AND** terminates with conventional SIGTERM status 143

#### Scenario: Container-local Ctrl-C
- **WHEN** the user types `Ctrl-C` for the foreground application inside the interactive container
- **THEN** container-local signal behavior remains unchanged
- **AND** the launcher does not interpret that input as a facade termination request
- **AND** does not invoke termination-specific forced removal

#### Scenario: Terminated container already exited
- **WHEN** SIGTERM cleanup finds that the exact allocated container no longer exists
- **THEN** the launcher treats container cleanup as complete
- **AND** reaps the attached Docker client if necessary
- **AND** removes the runtime projection
- **AND** preserves status 143

#### Scenario: Container cleanup fails during facade termination
- **WHEN** force-removing the exact allocated container fails for an operational reason
- **THEN** the launcher preserves SIGTERM status 143
- **AND** reports the cleanup failure as supplemental diagnostic information
- **AND** still attempts to reap the Docker client and remove the runtime projection

#### Scenario: Cleanup ownership isolation
- **WHEN** SIGTERM cleanup runs while other `pi-N` containers exist
- **THEN** the launcher targets only the container name allocated by the terminated facade transaction
- **AND** does not enumerate, stop, or remove other containers

#### Scenario: Normal container completion
- **WHEN** the attached container exits normally or with an ordinary nonzero code without facade SIGTERM
- **THEN** existing run-result behavior remains unchanged
- **AND** termination-specific forced removal is not invoked
