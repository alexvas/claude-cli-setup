## ADDED Requirements

### Requirement: Separate image builds from runtime project selection
The canonical image-build operation SHALL resolve versioned build inputs without requiring runtime-only project paths, Compose fragments, or host bind-mount configuration.

#### Scenario: Building without runtime configuration
- **WHEN** a user launches the canonical build with no `.env`, `PROJECT_PATH_*`, or custom `COMPOSE_FILE`
- **THEN** the resolver SHALL build service `pi` successfully using the reviewed version inventory
- **AND** SHALL NOT require a real host project directory merely to evaluate the build

#### Scenario: Preserving required version inputs
- **WHEN** the build-safe Compose configuration is rendered
- **THEN** all version and artifact arguments SHALL still come from the validated effective inventory
- **AND** missing version inputs SHALL NOT gain concrete Compose or Dockerfile fallbacks
