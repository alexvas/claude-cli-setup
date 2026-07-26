"""npm registry update provider.

Checks https://registry.npmjs.org/ for package version updates.
"""
from __future__ import annotations

import json
from typing import Optional
from urllib.parse import quote

from .base import HttpTransport, ProviderContext, ProviderResult, UpdateProvider
from ..model import (
    NpmSource,
    NpmUpdate,
    UpdateCandidate,
    UpdateKind,
    UpdateTarget,
)
from ..semver import SemanticVersion, parse


def _encode_package(pkg: str) -> str:
    """Percent-encode npm package name for URL."""
    return quote(pkg, safe="")


def _npm_registry_url(package: str) -> str:
    return f"https://registry.npmjs.org/{_encode_package(package)}"


def _latest_stable(versions: dict[str, object]) -> Optional[str]:
    """Return the highest stable semver key from the versions dict."""
    best: Optional[SemanticVersion] = None
    best_raw: Optional[str] = None
    for raw in versions:
        try:
            sv = parse(raw)
        except ValueError:
            continue
        if sv.is_prerelease:
            continue
        if best is None or sv > best:
            best = sv
            best_raw = raw
    return best_raw


def _latest_any(versions: dict[str, object]) -> Optional[str]:
    """Return the highest semver key, including prereleases."""
    best: Optional[SemanticVersion] = None
    best_raw: Optional[str] = None
    for raw in versions:
        try:
            sv = parse(raw)
        except ValueError:
            continue
        if best is None or sv > best:
            best = sv
            best_raw = raw
    return best_raw


class NpmProvider:
    name = "npm"

    def discover(
        self,
        target: UpdateTarget,
        context: ProviderContext,
    ) -> ProviderResult:
        source = target.source
        if not isinstance(source, NpmSource):
            return ProviderResult(
                skipped_reason=f"{target.path}: expected npm source, got {type(source).__name__}"
            )
        upd = target.update
        if not isinstance(upd, NpmUpdate):
            return ProviderResult(
                skipped_reason=f"{target.path}: expected npm update, got {type(upd).__name__}"
            )

        package = source.package
        url = _npm_registry_url(package)

        headers: dict[str, str] = {}
        token = context.tokens.get("NPM_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = context.http.request("GET", url, headers=dict(headers))
        except Exception as exc:
            return ProviderResult(unavailable_reason=f"npm registry: {exc}")

        if resp.status != 200:
            return ProviderResult(
                unavailable_reason=f"npm registry returned HTTP {resp.status}"
            )

        try:
            data = json.loads(resp.body)
        except Exception as exc:
            return ProviderResult(
                unavailable_reason=f"npm registry: invalid JSON ({exc})"
            )

        if not isinstance(data, dict):
            return ProviderResult(
                unavailable_reason="npm registry: unexpected response format"
            )

        versions = data.get("versions")
        if not isinstance(versions, dict) or not versions:
            return ProviderResult(
                skipped_reason=f"npm registry: no versions for {package}"
            )

        current = target.current

        selector = _latest_stable if (upd.stable_only and not context.include_prerelease) else _latest_any
        candidate_raw = selector(versions)
        if candidate_raw is None:
            return ProviderResult(
                skipped_reason=f"npm registry: no matching versions for {package}"
            )

        if candidate_raw == current:
            return ProviderResult(
                candidate=UpdateCandidate(
                    value=current,
                    kind=UpdateKind.VERSION,
                    artifacts={},
                )
            )

        # Prevent downgrade: if upstream maximum is older than selected,
        # report CURRENT rather than OUTDATED.
        try:
            cur_sv = parse(current)
            cand_sv = parse(candidate_raw)
            if cand_sv < cur_sv:
                return ProviderResult(
                    candidate=UpdateCandidate(
                        value=current,
                        kind=UpdateKind.VERSION,
                        artifacts={},
                    )
                )
        except ValueError:
            pass  # fall through to string comparison

        return ProviderResult(
            candidate=UpdateCandidate(
                value=candidate_raw,
                kind=UpdateKind.VERSION,
                artifacts={},
            )
        )
