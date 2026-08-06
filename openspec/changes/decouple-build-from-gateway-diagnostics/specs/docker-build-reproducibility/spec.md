## MODIFIED Requirements

### Requirement: Separate image builds from runtime project selection
The canonical direct Docker image-build operation SHALL resolve versioned build inputs without requiring runtime-only project paths, generated fragments, host bind-mount configuration, host gateway reachability, or operational gateway state.

#### Scenario: Building without runtime configuration
- **WHEN** a user runs `./docker/docker-constructor.py build` with no dotenv file or `PROJECT_PATH_*`
- **THEN** the resolver SHALL build the tagged Pi runtime image using the validated build section of `docker-constructor.toml`
- **AND** SHALL NOT probe `host.docker.internal`, require a reachable host gateway, read or write `HOST_GATEWAY_IP`, or mutate `.env`
- **AND** SHALL NOT require a real host project directory merely to evaluate the build

#### Scenario: Preserving required version inputs
- **WHEN** the direct Docker build command is rendered
- **THEN** all version and artifact arguments SHALL come from the validated effective build projection
- **AND** missing version inputs SHALL NOT gain concrete Dockerfile or Python fallbacks
