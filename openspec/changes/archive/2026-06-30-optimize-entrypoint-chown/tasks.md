## 1. Entrypoint ownership helper

- [x] 1.1 Replace unconditional recursive `chown -R` logic with a helper that targets only entries not owned by `dev:dev`
- [x] 1.2 Ensure recursive traversal does not follow symbolic links for both project mounts and runtime cache directories

## 2. Startup integration

- [x] 2.1 Apply the selective ownership helper to each configured `PROJECT_PATH_*` directory before safe-directory registration
- [x] 2.2 Apply the same helper to `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, and `/home/dev/.npm-global`

## 3. Verification

- [x] 3.1 Verify the entrypoint script remains shell-valid after the change
- [x] 3.2 Validate the OpenSpec change after all artifacts are written
