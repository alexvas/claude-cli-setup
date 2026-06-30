## 1. Selective permission helper

- [x] 1.1 Add a startup helper that recursively finds entries missing `g+w` and updates only those entries
- [x] 1.2 Ensure the permission traversal does not follow symbolic links and matches the existing startup repair scope

## 2. Startup integration

- [x] 2.1 Apply the selective `g+w` helper to each configured `PROJECT_PATH_*` directory alongside ownership repair
- [x] 2.2 Apply the same helper to `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, and `/home/dev/.npm-global`

## 3. Verification

- [x] 3.1 Verify the entrypoint script remains shell-valid after the change
- [x] 3.2 Validate the OpenSpec change after all artifacts are written
