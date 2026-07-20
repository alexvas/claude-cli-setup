## MODIFIED Requirements

### Requirement: Configure an interactive zsh environment
The system SHALL install a pinned oh-my-zsh setup for the `dev` user.

#### Scenario: Setting up zsh
- **WHEN** `docker/setup-zsh.sh` runs
- **THEN** it clones oh-my-zsh at the configured pinned git ref
- **AND** writes a minimal `.zshrc` with the `git` plugin enabled
- **AND** loads the Pi prompt fragment from `.pi-zsh-prompt`
- **AND** loads no prompt path other than `.pi-zsh-prompt`

#### Scenario: Only an obsolete prompt customization exists
- **WHEN** an obsolete prompt customization exists but `.pi-zsh-prompt` does not
- **THEN** zsh setup SHALL not load the obsolete customization
