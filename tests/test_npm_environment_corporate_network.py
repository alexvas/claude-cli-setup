"""Phase 4 — corporate network boundary (tasks 4.1–4.3, 4.6).

The standalone npm assembler must receive the same resolved credential-free
proxy and enabled corporate trust inputs as host-orchestrated dependency
acquisition, scoped only to the assembly process:

* enabled trust is mounted read-only at the fixed system trust path before
  npm network access, and disabled trust introduces no override (task 4.1);
* the execution boundary receives only the resolved credential-free proxy
  and CA policy — never credentials, relative trust paths, ambient
  environment, or extra network inputs (task 4.2);
* configured proxy endpoints and trust paths are never persisted in run
  vectors stored as evidence, argv stored in results, logs, exceptions,
  tree manifests, or assembled output trees (task 4.3).

Task 4.6 traces every local network-policy input to the process boundary and
proves the secret values are absent from published results and evidence.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import sys
import tempfile
import traceback
import unittest
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR.parent))

from docker.npm_environment import (
    AssemblyRun,
    CorporateNetworkPolicy,
    LockedNpmError,
    RootSpec,
    NPM_CONFIG_CAFILE,
    SYSTEM_CA_BUNDLE,
    PROXY_BYPASS_ENV_NAMES,
    PROXY_URL_ENV_NAMES,
    assembler_script_digest,
    assemble,
    build_tree_manifest,
    compute_assembler_identity,
    npm_policy_digest,
    npm_policy_env,
    preflight,
    redact_docker_argv,
    redact_run_vector,
    render_docker_argv,
    render_run_vector,
)

_IMAGE = "sha256:" + "a" * 64
_NODE = "24.18.0"
_NPM = "11.16.0"
_PLATFORM = "linux-x64"
_STAGING = Path("/tmp/npm-env-staging-4")
_NPM_CACHE = Path("/tmp/npm-env-cache-4")

_PROXY = "http://proxy.example.test:3128"
_NO_PROXY = "localhost,127.0.0.1,.internal"
_TRUST_BUNDLE = "/corp/trust/bundle.crt"


def _sri() -> str:
    import base64

    return "sha512-" + base64.b64encode(bytes([0xAB]) * 64).decode()


def _lock(roots: dict[str, str]) -> bytes:
    pkg_nodes = {
        f"node_modules/{name}": {
            "version": version,
            "resolved": f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz",
            "integrity": _sri(),
        }
        for name, version in roots.items()
    }
    return json.dumps(
        {
            "name": "root",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "requires": True,
            "packages": {
                "": {"name": "root", "version": "1.0.0", "dependencies": roots},
                **pkg_nodes,
            },
        }
    ).encode()


def _validated(roots: dict[str, str] | None = None):
    roots = roots or {"a": "1.0.0"}
    raw = _lock(roots)
    validated = preflight(
        raw,
        roots=tuple(RootSpec(n, v) for n, v in sorted(roots.items())),
        platform=_PLATFORM,
        node_version=_NODE,
        npm_version=_NPM,
    )
    return raw, validated


def _assembler():
    return compute_assembler_identity(
        image_digest=_IMAGE,
        node_version=_NODE,
        npm_version=_NPM,
        script_digest=assembler_script_digest(),
        policy_digest=npm_policy_digest(),
        platform=_PLATFORM,
    )


def _policy(
    *,
    proxy_url: str | None = _PROXY,
    proxy_no_proxy: str | None = _NO_PROXY,
    corporate_trust_bundle: str | None = _TRUST_BUNDLE,
) -> CorporateNetworkPolicy:
    return CorporateNetworkPolicy(
        proxy_url=proxy_url,
        proxy_no_proxy=proxy_no_proxy,
        corporate_trust_bundle=corporate_trust_bundle,
    )


def _vector(*, policy: CorporateNetworkPolicy | None = None):
    _raw, validated = _validated()
    return render_run_vector(
        validated=validated,
        assembler=_assembler(),
        staging=_STAGING,
        npm_cache=_NPM_CACHE,
        uid=1000,
        gid=1000,
        name="npm-assembler-net",
        corporate_network=policy,
    )


class _FakeExecutor:
    """Records argv and returns canned results."""

    def __init__(
        self,
        *,
        return_code: int = 0,
        stdout: str = "",
        stderr: str = "",
    ):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]):
        self.calls.append(argv)
        from docker.npm_environment import ProcessResult

        return ProcessResult(argv, self.return_code, self.stdout, self.stderr)


class _RaisingExecutor:
    """Raises the configured exception from every ``run`` call."""

    def __init__(self, exc: BaseException):
        self.exc = exc
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]):
        self.calls.append(argv)
        raise self.exc


class _AssemblerTestBase(unittest.TestCase):
    """Shared helper that runs ``assemble`` and cleans up its temp cache."""

    def _assemble(self, *, policy, executor):
        _raw, validated = _validated()
        tmp = tempfile.TemporaryDirectory(prefix="npm-env-net-")
        self.addCleanup(tmp.cleanup)
        cache_root = Path(tmp.name) / "cache"
        cache_root.mkdir()
        return assemble(
            validated=validated,
            assembler=_assembler(),
            cache_root=cache_root,
            executor=executor,
            corporate_network=policy,
        )


def _env_dict(argv: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    it = iter(argv)
    for token in it:
        if token == "--env":
            key, _, value = next(it).partition("=")
            result[key] = value
    return result


def _volumes(argv: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    it = iter(argv)
    for token in it:
        if token == "--volume":
            result.append(next(it))
    return result


class TestEnabledDisabledProjection(unittest.TestCase):
    """Task 4.1 — enabled/disabled proxy and CA projection."""

    def test_enabled_proxy_projected_into_env(self):
        env = dict(_vector(policy=_policy()).env)
        for name in PROXY_URL_ENV_NAMES:
            self.assertEqual(env.get(name), _PROXY, name)
        for name in PROXY_BYPASS_ENV_NAMES:
            self.assertEqual(env.get(name), _NO_PROXY, name)

    def test_disabled_proxy_emits_no_proxy_env(self):
        env = dict(_vector(policy=_policy(proxy_url=None, proxy_no_proxy=None)).env)
        for name in PROXY_URL_ENV_NAMES + PROXY_BYPASS_ENV_NAMES:
            self.assertNotIn(name, env)
        self.assertEqual(
            set(env),
            {"HOME", "npm_config_cache", "REVIEWED_NODE_VERSION",
             "REVIEWED_NPM_VERSION", NPM_CONFIG_CAFILE}
            | {name for name, _value in npm_policy_env()},
        )

    def test_enabled_trust_mounted_readonly_at_fixed_path(self):
        vector = _vector(policy=_policy())
        self.assertEqual(dict(vector.env)[NPM_CONFIG_CAFILE], SYSTEM_CA_BUNDLE)
        mounts = vector.mounts
        trust = [m for m in mounts if m.container == SYSTEM_CA_BUNDLE]
        self.assertEqual(len(trust), 1)
        self.assertEqual(trust[0].host, _TRUST_BUNDLE)
        self.assertEqual(trust[0].mode, "ro")

    def test_disabled_trust_emits_no_override(self):
        mounts = _vector(policy=CorporateNetworkPolicy()).mounts
        self.assertEqual(len(mounts), 3)
        self.assertFalse(any(m.container == SYSTEM_CA_BUNDLE for m in mounts))


class TestOnlyResolvedPolicyReceived(_AssemblerTestBase):
    """Task 4.2 — only the resolved credential-free proxy/CA policy."""

    def test_policy_rejects_proxy_credentials(self):
        with self.assertRaises(LockedNpmError) as ctx:
            CorporateNetworkPolicy(proxy_url="http://user:pass@proxy.example.test:3128")
        self.assertEqual(ctx.exception.reason, "invalid_proxy_policy")
        self.assertIn("credential", ctx.exception.detail)

    def test_policy_rejects_relative_trust_path(self):
        with self.assertRaises(LockedNpmError) as ctx:
            CorporateNetworkPolicy(corporate_trust_bundle="relative/bundle.crt")
        self.assertEqual(ctx.exception.reason, "invalid_trust_policy")

    def test_policy_rejects_no_proxy_without_proxy(self):
        with self.assertRaises(LockedNpmError) as ctx:
            CorporateNetworkPolicy(proxy_no_proxy="localhost")
        self.assertEqual(ctx.exception.reason, "invalid_proxy_policy")

    def test_executable_argv_receives_only_resolved_policy(self):
        executor = _FakeExecutor()
        result = self._assemble(policy=_policy(), executor=executor)
        self.assertIsInstance(result, AssemblyRun)
        argv = executor.calls[0]
        env = _env_dict(argv)
        base = {"HOME", "npm_config_cache", "REVIEWED_NODE_VERSION",
                "REVIEWED_NPM_VERSION"}
        self.assertEqual(
            set(env),
            base | set(PROXY_URL_ENV_NAMES) | set(PROXY_BYPASS_ENV_NAMES)
            | {NPM_CONFIG_CAFILE}
            | {name for name, _value in npm_policy_env()},
        )
        for name in PROXY_URL_ENV_NAMES:
            self.assertEqual(env[name], _PROXY)
        for name in PROXY_BYPASS_ENV_NAMES:
            self.assertEqual(env[name], _NO_PROXY)
        self.assertEqual(env[NPM_CONFIG_CAFILE], SYSTEM_CA_BUNDLE)

        volumes = _volumes(argv)
        self.assertIn(f"{_TRUST_BUNDLE}:{SYSTEM_CA_BUNDLE}:ro", volumes)
        self.assertEqual(volumes.count(f"{_TRUST_BUNDLE}:{SYSTEM_CA_BUNDLE}:ro"), 1)

        # No constructor-specific build-argument names, no env-file, no
        # --network, and no credential-bearing tokens reach the process.
        self.assertNotIn("--env-file", argv)
        self.assertNotIn("--network", argv)
        for token in argv:
            self.assertNotIn("PI_CORPORATE_PROXY_URL", token)
            self.assertNotIn("PI_CORPORATE_CA_PATH", token)
            self.assertNotIn("CORPORATE_TRUST_ENABLED", token)
            self.assertNotIn("@", token)


class TestNetworkConfigNonPersistence(_AssemblerTestBase):
    """Task 4.3 — redaction and non-persistence of network configuration."""

    def _secrets(self):
        return (_PROXY, _NO_PROXY, _TRUST_BUNDLE)

    def test_stored_run_vector_is_redacted(self):
        executor = _FakeExecutor(stdout="ok\n", stderr="warn\n")
        result = self._assemble(policy=_policy(), executor=executor)
        vector_text = json.dumps(
            {
                "env": list(result.run_vector.env),
                "mounts": [
                    (m.host, m.container, m.mode) for m in result.run_vector.mounts
                ],
            }
        )
        for secret in self._secrets():
            self.assertNotIn(secret, vector_text)
        self.assertIn("<redacted>", vector_text)

    def test_stored_argv_is_redacted(self):
        executor = _FakeExecutor(stdout="ok\n")
        result = self._assemble(policy=_policy(), executor=executor)
        argv_text = json.dumps(list(result.argv))
        for secret in self._secrets():
            self.assertNotIn(secret, argv_text)
        self.assertIn("<redacted>", argv_text)

    def test_logs_are_redacted_on_success(self):
        executor = _FakeExecutor(
            stdout=f"using proxy {_PROXY}\n",
            stderr=f"using trust {_TRUST_BUNDLE}\n",
        )
        result = self._assemble(policy=_policy(), executor=executor)
        for secret in self._secrets():
            self.assertNotIn(secret, result.stdout)
            self.assertNotIn(secret, result.stderr)

    def test_exception_detail_is_redacted_on_failure(self):
        executor = _FakeExecutor(
            return_code=1,
            stderr=f"npm ERR! failed {_PROXY} and {_TRUST_BUNDLE}",
        )
        with self.assertRaises(LockedNpmError) as ctx:
            self._assemble(policy=_policy(), executor=executor)
        for secret in self._secrets():
            self.assertNotIn(secret, ctx.exception.detail)
        self.assertIn("<redacted>", ctx.exception.detail)

    def test_executor_exception_is_structured_and_redacted(self):
        executor = _RaisingExecutor(
            RuntimeError(f"failed via {_PROXY} / {_NO_PROXY} / {_TRUST_BUNDLE}")
        )
        with self.assertRaises(LockedNpmError) as ctx:
            self._assemble(policy=_policy(), executor=executor)
        err = ctx.exception
        self.assertEqual(err.reason, "executor_failure")
        for secret in self._secrets():
            self.assertNotIn(secret, err.detail)
            self.assertNotIn(secret, str(err))
            for note in getattr(err, "__notes__", []):
                self.assertNotIn(secret, note)
        self.assertIn("<redacted>", err.detail)

        # The original exception must not remain reachable as __cause__ or
        # __context__, and the complete formatted traceback must be free of
        # every secret.
        self.assertIsNone(err.__cause__)
        self.assertIsNone(err.__context__)
        tb_text = "".join(traceback.format_exception(err))
        for secret in self._secrets():
            self.assertNotIn(secret, tb_text)
        self.assertIn("<redacted>", tb_text)

    def test_tree_manifest_and_output_tree_do_not_persist_secrets(self):
        executor = _FakeExecutor(stdout="ok\n")
        result = self._assemble(policy=_policy(), executor=executor)
        manifest = build_tree_manifest(result.staging)
        manifest_text = json.dumps(
            [dataclasses.asdict(entry) for entry in manifest.entries]
        )
        for secret in self._secrets():
            self.assertNotIn(secret, manifest_text)
            for path in result.staging.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes())

    def test_serialized_evidence_has_no_secrets(self):
        executor = _FakeExecutor(stdout="ok\n")
        result = self._assemble(policy=_policy(), executor=executor)
        evidence = json.dumps(
            {
                "argv": list(result.argv),
                "stdout": result.stdout,
                "stderr": result.stderr,
                "staging": str(result.staging),
                "run_vector": {
                    "env": list(result.run_vector.env),
                    "mounts": [
                        (m.host, m.container, m.mode)
                        for m in result.run_vector.mounts
                    ],
                },
            }
        )
        for secret in self._secrets():
            self.assertNotIn(secret, evidence)


class TestCorporateNetworkIntrospection(unittest.TestCase):
    """Task 4.6 — trace network policy to the boundary; no persistence."""

    def test_network_policy_is_explicit_not_ambient(self):
        import docker.npm_environment.execution as execution_module
        import docker.npm_environment.network as network_module
        import docker.npm_environment.run_vector as run_vector_module

        for module in (run_vector_module, execution_module, network_module):
            src = inspect.getsource(module)
            self.assertNotIn("os.environ", src, module.__name__)
            self.assertNotIn("os.getenv", src, module.__name__)
            self.assertNotIn("os.environb", src, module.__name__)

    def test_executable_vector_is_the_only_secret_carrier(self):
        vector = _vector(policy=_policy())
        # The executable plan necessarily carries the resolved values.
        self.assertIn(_PROXY, dict(vector.env).get("HTTPS_PROXY", ""))
        self.assertIn(_TRUST_BUNDLE, [m.host for m in vector.mounts])

        argv = render_docker_argv(vector)
        self.assertIn(f"HTTPS_PROXY={_PROXY}", argv)
        self.assertIn(f"{_TRUST_BUNDLE}:{SYSTEM_CA_BUNDLE}:ro", argv)

        # Redacted forms used for evidence carry none of them.
        redacted_vector = redact_run_vector(vector, (_PROXY, _NO_PROXY, _TRUST_BUNDLE))
        redacted_argv = redact_docker_argv(argv, (_PROXY, _NO_PROXY, _TRUST_BUNDLE))
        for secret in (_PROXY, _NO_PROXY, _TRUST_BUNDLE):
            self.assertNotIn(secret, json.dumps(list(redacted_vector.env)))
            self.assertNotIn(secret, json.dumps(list(redacted_argv)))
            self.assertNotIn(
                secret,
                json.dumps([m.host for m in redacted_vector.mounts]),
            )


if __name__ == "__main__":
    unittest.main()
