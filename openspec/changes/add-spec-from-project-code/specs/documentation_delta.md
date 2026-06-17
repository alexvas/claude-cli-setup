# Delta: Documentation

**Change ID:** `add-spec-from-project-code`
**Affects:** README.md, README.en.md, README.zh.md, .env.example

---

## ADDED

### Requirement: Multi-language README

Documentation is maintained in three languages: Russian (primary), English, and Chinese. All three must be kept in sync.

#### Scenario: README synchronization
- GIVEN a change is made to README.md (Russian)
- WHEN the change is ready for commit
- THEN README.en.md must be updated with the equivalent English text
- THEN README.zh.md must be updated with the equivalent Chinese text
- THEN all three files must describe the same configuration options, commands, and architecture

#### Scenario: Language header
- GIVEN a reader opens README.md
- WHEN they view the first line
- THEN they see navigation links: **Русский** | [English](README.en.md) | [中文](README.zh.md)

### Requirement: .env.example as Configuration Contract

The `.env.example` file serves as the documented interface for all configurable parameters.

#### Scenario: All env vars are documented
- GIVEN `.env.example` is the canonical config reference
- WHEN a new environment variable is added to docker-compose.yml
- THEN `.env.example` must include the variable with:
  - A descriptive comment explaining its purpose
  - The default value (commented out if optional)
  - Cross-references to related vars if applicable

#### Scenario: .env is gitignored
- GIVEN the repository is initialized
- WHEN `.env` contains actual secrets (API keys, tokens)
- THEN `.gitignore` includes `.env`
- THEN `.env` is never committed to the repository

---

## REMOVED

(None)
