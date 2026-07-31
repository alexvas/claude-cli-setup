"""Host-side build verification — compare container observations with
effective build expectations without injecting build metadata into
the container.

All process boundaries are injectable so tests remain daemon-independent.

Observation contracts
---------------------

Every build stage in the effective projection maps to a unique
observation key, a container-side ``--version`` command, and a
normalization rule.  The API reads the projection, issues one
``docker run --rm <image> <tool> --version`` per stage, normalizes
both the container output and the projection-derived expectation,
and compares them.

+------------------+------------------+-----------------------------+-----------------------------+
| Key              | Command suffix   | Expected source             | Normalization               |
+==================+==================+=============================+=============================+
| ``node.version`` | ``node            | ``[node].image`` → tag      | Strip leading ``v``/``V``   |
|                  | --version``       | version (e.g.               | from both sides, then       |
|                  |                   | ``node:22.11.0-bookworm``   | strip trailing newline.     |
|                  |                   | → ``"22.11.0"``)            |                             |
+------------------+------------------+-----------------------------+-----------------------------+
| ``rust.version`` | ``rustc           | ``[rust].version``          | Extract the first           |
|                  | --version``       | (e.g. ``"1.83.0"``)         | ``X.Y.Z`` token from        |
|                  |                   |                             | the multi-word output,      |
|                  |                   |                             | strip trailing newline.     |
+------------------+------------------+-----------------------------+-----------------------------+
| ``rust.cargo``   | ``cargo           | ``[rust].version``          | Same as *rust.version*.     |
|                  | --version``       |                             |                             |
+------------------+------------------+-----------------------------+-----------------------------+
| ``uv.version``   | ``uv --version``  | ``[uv].version``            | Extract first ``X.Y.Z``     |
|                  |                   | (e.g. ``"0.6.17"``)         | token, strip newline.       |
+------------------+------------------+-----------------------------+-----------------------------+
| ``python.version``| ``python3         | ``[python].version``        | Extract first ``X.Y.Z``     |
|                  | --version``       | (e.g. ``"3.14.0"``)         | token, strip newline.       |
+------------------+------------------+-----------------------------+-----------------------------+
| ``ty.version``   | ``ty --version``  | ``[ty].version``            | Extract first ``X.Y.Z``     |
|                  |                   | (e.g. ``"v0.9.0"``)         | token; v-strip both sides,  |
|                  |                   |                             | strip newline.              |
+------------------+------------------+-----------------------------+-----------------------------+
| ``rtk.version``  | ``rtk --version`` | ``[rtk].version``           | Extract first ``X.Y.Z``     |
|                  |                   | (e.g. ``"0.1.29"``)         | token, strip newline.       |
+------------------+------------------+-----------------------------+-----------------------------+
| ``fd.version``   | ``fd --version``  | ``[fd].version``            | Extract first ``X.Y.Z``     |
|                  |                   | (e.g. ``"10.1.0"``)         | token, strip newline.       |
+------------------+------------------+-----------------------------+-----------------------------+
| ``pi.version``   | ``pi --version``  | ``[pi].version``            | v-strip both sides, strip   |
|                  |                   | (e.g. ``"v1.4.236"``)       | newline.                    |
+------------------+------------------+-----------------------------+-----------------------------+
| ``openspec.version``| ``openspec        | ``[openspec].version``      | Extract first ``X.Y.Z``     |
|                     | --version``       | (e.g. ``"v0.15.0"``)        | token; v-strip both sides,  |
|                     |                   |                             | strip newline.              |
+------------------+------------------+-----------------------------+-----------------------------+
| ``rust.rustfmt``  | ``rustfmt         | ``[rust].version`` →        | Extract first ``X.Y.Z``     |
|                   | --version``       | ``"1.83.0"`` (rustfmt       | token, strip newline.       |
|                   |                   | tracks the rustc version     |                             |
|                   |                   | minus any ``-stable``        |                             |
|                   |                   | suffix).                     |                             |
+------------------+------------------+-----------------------------+-----------------------------+
| ``rust.clippy``   | ``cargo clippy    | ``[rust].version`` →        | Extract first ``X.Y.Z``     |
|                   | --version``       | ``"0.1.83"`` (clippy        | token, strip newline.       |
|                   |                   | version derived from its     |                             |
|                   |                   | own numbering convention,    |                             |
|                   |                   | ``0.1.{rust-minor}``).       |                             |
+------------------+------------------+-----------------------------+-----------------------------+
| ``oh-my-zsh.      | ``git -C          | ``[oh-my-zsh].revision``    | Strip trailing newline.     |
| revision``        | /home/dev/        | (e.g. ``"eea3ac1a68…"``)     |                             |
|                   | .oh-my-zsh        |                             |                             |
|                   | rev-parse HEAD``  |                             |                             |
+------------------+------------------+-----------------------------+-----------------------------+

All observation commands are issued as
``("docker", "run", "--rm", image, *command_suffix)``.  The effective
build projection is read from the host only — it is NEVER mounted,
volume-bound, or ``docker cp``'d into the container.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


# ── Process boundary (identical contract to docker/launcher.py) ──────


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    def run(self, argv: Sequence[str]) -> ProcessResult:
        """Execute *argv* and return the outcome."""
        ...


# ── Observation contracts — the authoritative per-tool mapping ──────


@dataclass(frozen=True)
class ObservationContract:
    """Defines how a single build stage is observed inside the container.

    The *expected_value* is derived at runtime from the loaded effective
    build projection via :func:`_extract_expected_value` — it is never
    stored in the contract itself.
    """
    key: str
    """Unique observation key (e.g. ``"node.version"``)."""
    command_suffix: tuple[str, ...]
    """Arguments appended to ``docker run --rm <image>``
    (e.g. ``("node", "--version")``)."""


# Observation contracts in the documented deterministic order.
# Expected values are derived at runtime from the effective build
# projection — see :func:`_extract_expected_value`.
_CONTRACTS: tuple[ObservationContract, ...] = (
    ObservationContract(
        key="node.version",
        command_suffix=("node", "--version"),
    ),
    ObservationContract(
        key="rust.version",
        command_suffix=("rustc", "--version"),
    ),
    ObservationContract(
        key="rust.cargo",
        command_suffix=("cargo", "--version"),
    ),
    ObservationContract(
        key="rust.rustfmt",
        command_suffix=("rustfmt", "--version"),
    ),
    ObservationContract(
        key="rust.clippy",
        command_suffix=("cargo", "clippy", "--version"),
    ),
    ObservationContract(
        key="uv.version",
        command_suffix=("uv", "--version"),
    ),
    ObservationContract(
        key="python.version",
        command_suffix=("python3", "--version"),
    ),
    ObservationContract(
        key="ty.version",
        command_suffix=("ty", "--version"),
    ),
    ObservationContract(
        key="rtk.version",
        command_suffix=("rtk", "--version"),
    ),
    ObservationContract(
        key="fd.version",
        command_suffix=("fd", "--version"),
    ),
    ObservationContract(
        key="pi.version",
        command_suffix=("pi", "--version"),
    ),
    ObservationContract(
        key="openspec.version",
        command_suffix=("openspec", "--version"),
    ),
    ObservationContract(
        key="oh-my-zsh.revision",
        command_suffix=("git", "-C", "/home/dev/.oh-my-zsh", "rev-parse", "HEAD"),
    ),
)


# ── Expected-value extraction ────────────────────────────────────────


def _extract_node_version(image: str) -> str:
    """Extract ``X.Y.Z`` from a Node image reference.

    >>> _extract_node_version("node:22.11.0-bookworm-slim")
    '22.11.0'
    >>> _extract_node_version("node:18.19.0-bookworm-slim@sha256:abc")
    '18.19.0'
    """
    ref = image.split("@")[0]
    tag = ref.split(":")[-1]
    return tag.split("-")[0]


def _extract_expected_value(key: str, projection: dict) -> str:
    """Derive the normalized expected value for *key* from *projection*.

    *projection* is the plain-data dict returned by
    :func:`docker.versioning.rendering.serialize_effective_build` (i.e.
    the parsed effective build projection TOML).
    """
    if key == "node.version":
        return _extract_node_version(projection["node"]["image"])
    elif key == "rust.version":
        return projection["rust"]["version"]
    elif key == "rust.cargo":
        return projection["rust"]["version"]
    elif key == "rust.rustfmt":
        return projection["rust"]["version"]
    elif key == "rust.clippy":
        v = projection["rust"]["version"]
        minor = v.split(".")[1]
        return f"0.1.{minor}"
    elif key == "uv.version":
        return projection["uv"]["version"]
    elif key == "python.version":
        return projection["python"]["version"]
    elif key == "ty.version":
        return projection["ty"]["version"].lstrip("v")
    elif key == "rtk.version":
        return projection["rtk"]["version"]
    elif key == "fd.version":
        return projection["fd"]["version"]
    elif key == "pi.version":
        return projection["pi"]["version"].lstrip("v")
    elif key == "openspec.version":
        return projection["openspec"]["version"].lstrip("v")
    elif key == "oh-my-zsh.revision":
        return projection["oh-my-zsh"]["revision"]
    raise KeyError(f"Unknown observation key: {key}")


def _applicable_contracts(
    projection: dict,
) -> tuple[ObservationContract, ...]:
    """Return the subset of :data:`_CONTRACTS` that apply to *projection*.

    Rust component contracts (``rust.rustfmt``, ``rust.clippy``) are
    only included when the corresponding component name appears in
    ``projection["rust"]["components"]``.
    """
    components: tuple[str, ...] = tuple(
        projection.get("rust", {}).get("components", ())
    )
    result: list[ObservationContract] = []
    for c in _CONTRACTS:
        if c.key == "rust.rustfmt" and "rustfmt" not in components:
            continue
        if c.key == "rust.clippy" and "clippy" not in components:
            continue
        result.append(c)
    return tuple(result)


# ── Normalization ────────────────────────────────────────────────────

import re as _re

_VERSION_TOKEN = _re.compile(r"\d+\.\d+\.\d+")


def _strip_v(s: str) -> str:
    """Strip a leading ``v`` or ``V`` and trailing whitespace."""
    s = s.strip()
    if s.startswith("v") or s.startswith("V"):
        s = s[1:]
    return s


def _extract_x_y_z(s: str) -> str:
    """Return the first ``X.Y.Z`` token found in *s*."""
    m = _VERSION_TOKEN.search(s.strip())
    return m.group(0) if m else s.strip()


def _extract_v_stripped_x_y_z(s: str) -> str:
    """Strip leading ``v``/``V``, then extract the first ``X.Y.Z`` token."""
    return _extract_x_y_z(_strip_v(s))


def _normalize(key: str, value: str) -> str:
    """Apply the per-contract normalization to observed or expected output."""
    if key in ("node.version",):
        return _strip_v(value)
    elif key in ("rust.version", "rust.cargo", "uv.version",
                 "python.version", "rtk.version", "fd.version"):
        return _extract_x_y_z(value)
    elif key in ("ty.version", "pi.version", "openspec.version",
                 "rust.rustfmt", "rust.clippy"):
        return _extract_v_stripped_x_y_z(value)
    elif key == "oh-my-zsh.revision":
        return value.strip()
    return value.strip()


# ── Toml loader ──────────────────────────────────────────────────────


def _load_build_projection(path: Path) -> dict:
    """Load and return the effective build projection dict from *path*.

    Raises ``OSError`` when the file is missing or unreadable.
    """
    import tomllib
    with path.open("rb") as fh:
        return tomllib.load(fh)


# ── Observation models ───────────────────────────────────────────────


@dataclass(frozen=True)
class BuildObservation:
    """A single container-side observation extracted from a command run."""
    key: str
    """Human-readable label (e.g. ``"node.version"``)."""
    command: tuple[str, ...]
    """Full argv executed (e.g.
    ``("docker", "run", "--rm", "img", "node", "--version")``)."""
    expected_value: str
    """Normalized host-side expectation from the effective build
    projection (e.g. ``"22.11.0"`` — no ``v`` prefix)."""
    observed_value: str | None = None
    """Raw container stdout (``None`` if the command could not run)."""
    ok: bool = False
    """``True`` when the normalized observation matches *expected_value*."""


@dataclass(frozen=True)
class BuildVerificationResult:
    """Complete result of a build verification pass."""
    image: str
    observations: tuple[BuildObservation, ...]
    all_ok: bool
    """``True`` when every observation is ``ok``."""
    errors: tuple[str, ...]
    """Non-observation errors (image missing, projection unreadable, etc.)."""


# ── Request ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VerifyBuildRequest:
    """Request to verify a built image against host-side expectations."""
    image: str
    """Docker image to inspect (e.g. ``"pi-cli-pi:latest"``)."""
    effective_projection_path: Path
    """Path to the host-side effective build projection TOML file."""
    runner: ProcessRunner
    """Injected process boundary for ``docker run ...`` invocations."""


# ── Public API ───────────────────────────────────────────────────────


def verify_build(request: VerifyBuildRequest) -> BuildVerificationResult:
    """Run observation commands inside *image* and compare the outputs
    against the host-side effective build projection.

    The effective build projection is read from the host only — it is
    NEVER mounted or passed into the container.
    """
    errors: list[str] = []
    observations: list[BuildObservation] = []

    # 1. Load the host-side projection.
    try:
        projection = _load_build_projection(request.effective_projection_path)
    except (OSError, ValueError) as exc:
        return BuildVerificationResult(
            image=request.image,
            observations=(),
            all_ok=False,
            errors=(f"cannot read effective build projection: {exc}",),
        )

    # 2. Determine applicable contracts (rust components conditional).
    contracts = _applicable_contracts(projection)

    # 3. Run each observation.
    for contract in contracts:
        cmd = ("docker", "run", "--rm", request.image, *contract.command_suffix)
        expected = _extract_expected_value(contract.key, projection)
        try:
            result = request.runner.run(cmd)
        except Exception as exc:
            errors.append(f"{contract.key}: command error: {exc}")
            observations.append(BuildObservation(
                key=contract.key,
                command=cmd,
                expected_value=expected,
                observed_value=None,
                ok=False,
            ))
            continue

        observed_raw = result.stdout if result.return_code == 0 else result.stderr
        normalized_obs = _normalize(contract.key, observed_raw)
        normalized_exp = _normalize(contract.key, expected)
        ok = normalized_obs == normalized_exp
        observations.append(BuildObservation(
            key=contract.key,
            command=cmd,
            expected_value=expected,
            observed_value=observed_raw,
            ok=ok,
        ))

    # 4. Assemble result.
    all_ok = all(o.ok for o in observations) and len(errors) == 0
    return BuildVerificationResult(
        image=request.image,
        observations=tuple(observations),
        all_ok=all_ok,
        errors=tuple(errors),
    )
