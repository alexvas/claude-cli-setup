"""Shared test helpers for versioning tests — TOML builders, fixtures path."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "versions"


def write_toml(content: str, *, dir: Optional[Path] = None) -> Path:
    """Write TOML content to a temp file, return its Path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False, dir=dir
    )
    try:
        f.write(content)
        f.flush()
        return Path(f.name)
    finally:
        f.close()


def minimal_toml(**overrides: str) -> str:
    """Return minimal valid TOML with every required section, plus overrides.

    Each keyword arg replaces a dot-path section with raw TOML content.
    Use an empty string to remove a section entirely.
    """
    def g(key: str, default: str) -> str:
        """Return override if present, else default. Empty override = removed."""
        if key in overrides:
            return overrides[key]
        return default

    return f"""\
schema = 1

[build.stages.base.node]
tag = "24-trixie-slim"
{g("base.node", 'digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"')}

[build.stages.base.node.source]
{g("build.stages.base.node.source", 'type = "docker-registry"\nregistry = "docker.io"\nrepository = "library/node"')}

[build.stages.base.node.update]
{g("build.stages.base.node.update", '''provider = "docker-registry"
stable_only = true
track = "tag-digest"''')}

[build.stages.toolchain.rust]
{g("build.stages.toolchain.rust", 'version = "1.0.0"\nprofile = "minimal"\ncomponents = ["rustfmt", "clippy"]')}

[build.stages.toolchain.rust.source]
{g("build.stages.toolchain.rust.source", 'type = "rust-channel"\nmanifest = "https://static.rust-lang.org/dist/channel-rust-1.0.0.toml"')}

[build.stages.toolchain.rust.update]
{g("build.stages.toolchain.rust.update", '''provider = "rust-channel"
channel = "stable"
stable_only = true''')}

[build.stages.toolchain.rust.rustup.source]
{g("build.stages.toolchain.rust.rustup.source", 'type = "static-url"\nchecksum_url = "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init.sha256"')}

[build.stages.toolchain.rust.rustup.update]
{g("build.stages.toolchain.rust.rustup.update", '''provider = "static-url"
stable_only = true''')}

[build.stages.toolchain.rust.rustup.artifacts.linux-amd64]
{g("build.stages.toolchain.rust.rustup", 'url = "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init"\nsha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"')}

[build.stages.toolchain.uv]
{g("build.stages.toolchain.uv", 'version = "0.1.0"')}

[build.stages.toolchain.uv.source]
{g("build.stages.toolchain.uv.source", 'type = "github-release"\nrepository = "astral-sh/uv"\ntag = "0.1.0"')}

[build.stages.toolchain.uv.artifacts.linux-amd64]
url = "https://github.com/astral-sh/uv/releases/download/0.1.0/uv-x86_64-unknown-linux-gnu.tar.gz"
sha256 = "0a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f6789"

[build.stages.toolchain.uv.update]
{g("build.stages.toolchain.uv.update", 'provider = "github-release"\nstable_only = true\nrequired_platforms = ["linux-amd64"]')}

[build.stages.toolchain.python]
{g("build.stages.toolchain.python", 'version = "3.14.6"')}

[build.stages.toolchain.python.source]
{g("build.stages.toolchain.python.source", 'type = "uv-python"\nimplementation = "cpython"')}

[build.stages.toolchain.python.update]
{g("build.stages.toolchain.python.update", 'provider = "uv-python"\nimplementation = "cpython"\nstable_only = true')}

[build.stages.toolchain.python.override]
{g("build.stages.toolchain.python.override", 'constraint = ">=3.14.6"\nallow_prerelease = false\nscheme = "numeric"')}

[build.stages.toolchain.ty]
{g("build.stages.toolchain.ty", 'version = "0.0.61"')}

[build.stages.toolchain.ty.source]
{g("build.stages.toolchain.ty.source", 'type = "pypi"\npackage = "ty"')}

[build.stages.toolchain.ty.update]
{g("build.stages.toolchain.ty.update", 'provider = "pypi"\nstable_only = true')}

[build.stages.rtk-prebuilt.rtk]
{g("build.stages.rtk-prebuilt.rtk", 'version = "v0.43.0"')}

[build.stages.rtk-prebuilt.rtk.source]
{g("build.stages.rtk-prebuilt.rtk.source", 'type = "github-release"\nrepository = "rtk-ai/rtk"\ntag = "v0.43.0"')}

[build.stages.rtk-prebuilt.rtk.artifacts.linux-amd64]
url = "https://github.com/rtk-ai/rtk/releases/download/v0.43.0/rtk_amd64.deb"
sha256 = "eb571d784b3269521722ebe2f0dc2409e89da6bd70bf097ddb21e9d4b3b240b9"

[build.stages.rtk-prebuilt.rtk.update]
{g("build.stages.rtk-prebuilt.rtk.update", 'provider = "github-release"\nstable_only = true\ntag_prefix = "v"\nrequired_platforms = ["linux-amd64"]')}

[build.stages.fd-prebuilt.fd]
{g("build.stages.fd-prebuilt.fd", 'version = "v10.4.2"')}

[build.stages.fd-prebuilt.fd.source]
{g("build.stages.fd-prebuilt.fd.source", 'type = "github-release"\nrepository = "sharkdp/fd"\ntag = "v10.4.2"')}

[build.stages.fd-prebuilt.fd.artifacts.linux-amd64]
url = "https://github.com/sharkdp/fd/releases/download/v10.4.2/fd_10.4.2_amd64.deb"
sha256 = "0e44eb5fca93f09bc6f5430b90acdf44c8e069d0a903700aeb4820629337b67b"

[build.stages.fd-prebuilt.fd.update]
{g("build.stages.fd-prebuilt.fd.update", 'provider = "github-release"\nstable_only = true\ntag_prefix = "v"\nrequired_platforms = ["linux-amd64"]')}

[build.stages.pi-tools.pi]
{g("build.stages.pi-tools.pi", 'version = "0.80.10"')}

[build.stages.pi-tools.pi.source]
{g("build.stages.pi-tools.pi.source", 'type = "npm"\npackage = "@earendil-works/pi-coding-agent"')}

[build.stages.pi-tools.pi.update]
{g("build.stages.pi-tools.pi.update", 'provider = "npm"\nstable_only = true')}

[build.stages.openspec-tools.openspec]
{g("build.stages.openspec-tools.openspec", 'version = "1.6.0"')}

[build.stages.openspec-tools.openspec.source]
{g("build.stages.openspec-tools.openspec.source", 'type = "npm"\npackage = "@fission-ai/openspec"')}

[build.stages.openspec-tools.openspec.update]
{g("build.stages.openspec-tools.openspec.update", 'provider = "npm"\nstable_only = true')}

[build.stages.runtime.oh-my-zsh]
{g("build.stages.runtime.oh-my-zsh", 'revision = "70ad5e3df8f7bed68aa6672029496926e632aedd"')}

[build.stages.runtime.oh-my-zsh.source]
{g("build.stages.runtime.oh-my-zsh.source", 'type = "git"\nrepository = "https://github.com/ohmyzsh/ohmyzsh.git"')}

[build.stages.runtime.oh-my-zsh.update]
{g("build.stages.runtime.oh-my-zsh.update", 'provider = "git-ref"\nref = "master"')}

[runtime.pi-extensions.pi-read]
{g("runtime.pi-extensions.pi-read", 'version = "0.2.0"')}

[runtime.pi-extensions.pi-read.source]
{g("runtime.pi-extensions.pi-read.source", 'type = "npm"\npackage = "@arcanemachine/pi-read"')}

[runtime.pi-extensions.pi-read.artifact]
{g("runtime.pi-extensions.pi-read.artifact", 'url = "https://registry.npmjs.org/@arcanemachine/pi-read/-/pi-read-0.2.0.tgz"\nintegrity = "sha512-VO9pV15PFTBOfcNq9hgKJ3K6k4Bb0ndDlX6N5ReNTOa/r66/Ppfc9N/hexsK5veMHGl1YbjCo3wOnL5jJu17/Q=="')}

[runtime.pi-extensions.pi-read.update]
{g("runtime.pi-extensions.pi-read.update", 'provider = "npm"\nstable_only = true')}

[runtime.pi-extensions.pi-read.override]
{g("runtime.pi-extensions.pi-read.override", 'constraint = ">=0.2.0"\nallow_prerelease = false\nscheme = "numeric"')}

[runtime.pi-extensions.pi-read.validation]
{g("runtime.pi-extensions.pi-read.validation", 'metadata_file = "package.json"')}

[runtime.pi-extensions.pi-codex-usage]
version = "0.9.1"

[runtime.pi-extensions.pi-codex-usage.source]
type = "npm"
package = "@llblab/pi-codex-usage"

[runtime.pi-extensions.pi-codex-usage.artifact]
url = "https://registry.npmjs.org/@llblab/pi-codex-usage/-/pi-codex-usage-0.9.1.tgz"
integrity = "sha512-r5iMe57KgKPWSvx5/fKCwT+s/haysaEs40OMdTtisAFR1njppvNAhlgNOBl7+nDm6j88XTee3m0Rp3s/kinIQg=="

[runtime.pi-extensions.pi-codex-usage.update]
provider = "npm"
stable_only = true

[runtime.pi-extensions.pi-codex-usage.override]
constraint = ">=0.9.0"
allow_prerelease = false
scheme = "numeric"

[runtime.pi-extensions.pi-codex-usage.validation]
metadata_file = "package.json"

[runtime.pi-extensions.pi-proxy]
version = "1.0.0"

[runtime.pi-extensions.pi-proxy.source]
type = "npm"
package = "pi-proxy"

[runtime.pi-extensions.pi-proxy.artifact]
url = "https://registry.npmjs.org/pi-proxy/-/pi-proxy-1.0.0.tgz"
integrity = "sha512-UHr/AQV2S0rISwRsD5jmKAo9ZQlZxU9Csh72sGYYDhbkSo44P+XzfRG96OuYYy2G3Iis0a75w3Cp9KYtjpbZxw=="

[runtime.pi-extensions.pi-proxy.update]
provider = "npm"
stable_only = true

[runtime.pi-extensions.pi-proxy.override]
constraint = ">=1.0.0"
allow_prerelease = false
scheme = "numeric"

[runtime.pi-extensions.pi-proxy.validation]
metadata_file = "package.json"
"""
