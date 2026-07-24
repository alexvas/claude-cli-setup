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

[stages.base.node]
tag = "24-trixie-slim"
{g("base.node", 'digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"')}

[stages.base.node.source]
{g("stages.base.node.source", 'type = "docker-registry"\nregistry = "docker.io"\nrepository = "library/node"')}

[stages.base.node.update]
{g("stages.base.node.update", '''provider = "docker-registry"
stable_only = true
track = "tag-digest"''')}

[stages.toolchain.rust]
{g("stages.toolchain.rust", 'version = "1.0.0"\nprofile = "minimal"\ncomponents = ["rustfmt", "clippy"]')}

[stages.toolchain.rust.source]
{g("stages.toolchain.rust.source", 'type = "rust-channel"\nmanifest = "https://static.rust-lang.org/dist/channel-rust-1.0.0.toml"')}

[stages.toolchain.rust.update]
{g("stages.toolchain.rust.update", '''provider = "rust-channel"
channel = "stable"
stable_only = true''')}

[stages.toolchain.rust.rustup.source]
{g("stages.toolchain.rust.rustup.source", 'type = "static-url"\nchecksum_url = "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init.sha256"')}

[stages.toolchain.rust.rustup.update]
{g("stages.toolchain.rust.rustup.update", '''provider = "static-url"
stable_only = true''')}

[stages.toolchain.rust.rustup.artifacts.linux-amd64]
{g("stages.toolchain.rust.rustup", 'url = "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init"\nsha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"')}

[stages.toolchain.uv]
{g("stages.toolchain.uv", 'version = "0.1.0"')}

[stages.toolchain.uv.source]
{g("stages.toolchain.uv.source", 'type = "github-release"\nrepository = "astral-sh/uv"\ntag = "0.1.0"')}

[stages.toolchain.uv.artifacts.linux-amd64]
url = "https://github.com/astral-sh/uv/releases/download/0.1.0/uv-x86_64-unknown-linux-gnu.tar.gz"
sha256 = "0a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f6789"

[stages.toolchain.uv.update]
{g("stages.toolchain.uv.update", 'provider = "github-release"\nstable_only = true\nrequired_platforms = ["linux-amd64"]')}

[stages.toolchain.python]
{g("stages.toolchain.python", 'version = "3.14.6"')}

[stages.toolchain.python.source]
{g("stages.toolchain.python.source", 'type = "uv-python"\nimplementation = "cpython"')}

[stages.toolchain.python.update]
{g("stages.toolchain.python.update", 'provider = "uv-python"\nimplementation = "cpython"\nstable_only = true')}

[stages.toolchain.ty]
{g("stages.toolchain.ty", 'version = "0.0.61"')}

[stages.toolchain.ty.source]
{g("stages.toolchain.ty.source", 'type = "pypi"\npackage = "ty"')}

[stages.toolchain.ty.update]
{g("stages.toolchain.ty.update", 'provider = "pypi"\nstable_only = true')}

[stages.rtk-prebuilt.rtk]
{g("stages.rtk-prebuilt.rtk", 'version = "v0.43.0"')}

[stages.rtk-prebuilt.rtk.source]
{g("stages.rtk-prebuilt.rtk.source", 'type = "github-release"\nrepository = "rtk-ai/rtk"\ntag = "v0.43.0"')}

[stages.rtk-prebuilt.rtk.artifacts.linux-amd64]
url = "https://github.com/rtk-ai/rtk/releases/download/v0.43.0/rtk_amd64.deb"
sha256 = "eb571d784b3269521722ebe2f0dc2409e89da6bd70bf097ddb21e9d4b3b240b9"

[stages.rtk-prebuilt.rtk.update]
{g("stages.rtk-prebuilt.rtk.update", 'provider = "github-release"\nstable_only = true\ntag_prefix = "v"\nrequired_platforms = ["linux-amd64"]')}

[stages.fd-prebuilt.fd]
{g("stages.fd-prebuilt.fd", 'version = "v10.4.2"')}

[stages.fd-prebuilt.fd.source]
{g("stages.fd-prebuilt.fd.source", 'type = "github-release"\nrepository = "sharkdp/fd"\ntag = "v10.4.2"')}

[stages.fd-prebuilt.fd.artifacts.linux-amd64]
url = "https://github.com/sharkdp/fd/releases/download/v10.4.2/fd_10.4.2_amd64.deb"
sha256 = "0e44eb5fca93f09bc6f5430b90acdf44c8e069d0a903700aeb4820629337b67b"

[stages.fd-prebuilt.fd.update]
{g("stages.fd-prebuilt.fd.update", 'provider = "github-release"\nstable_only = true\ntag_prefix = "v"\nrequired_platforms = ["linux-amd64"]')}

[stages.pi-tools.pi]
{g("stages.pi-tools.pi", 'version = "0.80.10"')}

[stages.pi-tools.pi.source]
{g("stages.pi-tools.pi.source", 'type = "npm"\npackage = "@earendil-works/pi-coding-agent"')}

[stages.pi-tools.pi.update]
{g("stages.pi-tools.pi.update", 'provider = "npm"\nstable_only = true')}

[stages.openspec-tools.openspec]
{g("stages.openspec-tools.openspec", 'version = "1.6.0"')}

[stages.openspec-tools.openspec.source]
{g("stages.openspec-tools.openspec.source", 'type = "npm"\npackage = "@fission-ai/openspec"')}

[stages.openspec-tools.openspec.update]
{g("stages.openspec-tools.openspec.update", 'provider = "npm"\nstable_only = true')}

[stages.runtime.oh-my-zsh]
{g("stages.runtime.oh-my-zsh", 'revision = "70ad5e3df8f7bed68aa6672029496926e632aedd"')}

[stages.runtime.oh-my-zsh.source]
{g("stages.runtime.oh-my-zsh.source", 'type = "git"\nrepository = "https://github.com/ohmyzsh/ohmyzsh.git"')}

[stages.runtime.oh-my-zsh.update]
{g("stages.runtime.oh-my-zsh.update", 'provider = "git-ref"\nref = "master"')}

[runtime.pi-extensions.pi-read]
{g("runtime.pi-extensions.pi-read", 'version = "0.2.0"')}

[runtime.pi-extensions.pi-read.source]
{g("runtime.pi-extensions.pi-read.source", 'type = "npm"\npackage = "@arcanemachine/pi-read"')}

[runtime.pi-extensions.pi-read.update]
{g("runtime.pi-extensions.pi-read.update", 'provider = "npm"\nstable_only = true')}

[runtime.pi-extensions.pi-codex-usage]
version = "0.9.1"

[runtime.pi-extensions.pi-codex-usage.source]
type = "npm"
package = "@llblab/pi-codex-usage"

[runtime.pi-extensions.pi-codex-usage.update]
provider = "npm"
stable_only = true

[runtime.pi-extensions.pi-proxy]
version = "1.0.0"

[runtime.pi-extensions.pi-proxy.source]
type = "npm"
package = "pi-proxy"

[runtime.pi-extensions.pi-proxy.update]
provider = "npm"
stable_only = true
"""
