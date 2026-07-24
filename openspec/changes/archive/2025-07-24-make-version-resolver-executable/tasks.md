## 1. Specify direct execution

- [x] 1.1 Add RED tests for a portable Python 3 shebang and executable Git file mode on `docker/versions.py`
- [x] 1.2 Add RED subprocess parity tests comparing direct and `python3` invocation for successful output, expected errors, and exit codes

## 2. Expose the executable interface

- [x] 2.1 Add the shebang and executable bit without changing wrapper imports or command behavior
- [x] 2.2 Update maintained command references and `.env.example` from interpreter-prefixed to direct resolver invocation
- [x] 2.3 Update documentation/source consistency tests to require the direct canonical form while allowing interpreter compatibility where appropriate

## 3. Validate compatibility

- [x] 3.1 Run direct-execution, CLI, import-boundary, semantic-source, and rendering test suites under a sanitized environment
- [x] 3.2 Compare representative `validate`, `env`, `compose --help`, and `check-updates --help` output and exit codes across both invocation forms
- [x] 3.3 Run full local tests, strict OpenSpec validation, and `git diff --check`
