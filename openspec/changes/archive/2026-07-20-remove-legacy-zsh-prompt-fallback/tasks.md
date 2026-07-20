## 1. Remove legacy shell fallback

- [x] 1.1 Remove the `.claude-cli-zsh-prompt` fallback branch from `docker/setup-zsh.sh`
- [x] 1.2 Confirm the generated `.zshrc` sources only `/home/dev/.pi-zsh-prompt`
- [x] 1.3 Verify the generated shell configuration loads only the Pi prompt path

## 2. Align specifications and documentation

- [x] 2.1 Sync the modified `docker-runtime` requirement to the main spec
- [x] 2.2 Remove legacy fallback and migration wording from `README.md`
- [x] 2.3 Remove equivalent wording from `README.en.md` and `README.zh.md`
- [x] 2.4 Remove prompt migration instructions; document only the supported Pi prompt path
- [x] 2.5 Document safe Docker storage inspection and cleanup without recommending manual containerd snapshot deletion

## 3. Verify

- [x] 3.1 Run Python and shell syntax checks
- [x] 3.2 Build the `pi` image and verify only `/home/dev/.pi-zsh-prompt` is loaded by zsh
- [x] 3.3 Confirm `locate` results disappear after appropriate Docker cache/image cleanup and database refresh
- [x] 3.4 Validate the change with `openspec validate --strict`
