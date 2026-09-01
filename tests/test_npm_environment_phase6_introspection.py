"""Phase 6 — scenario coverage and public-boundary introspection (task 6.6).

Every scenario in the locked-npm-environment-assembly spec is mapped to at
least one focused or acceptance test class, and the mapping itself is
checked so a missing or renamed test fails the build.  The dependent
consumer boundary is verified against the public API surface and the
result/evidence DTO field names: no npm-cache, staging, executor, mount, or
consumer-specific field may leak into the public result contract.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SPEC = (
    _REPO
    / "openspec"
    / "changes"
    / "add-locked-npm-environment-assembler"
    / "specs"
    / "locked-npm-environment-assembly"
    / "spec.md"
)
_MAP_PATH = _REPO / "tests" / "data" / "npm_environment_scenario_coverage.json"

_SCENARIO_RE = re.compile(r"^#### Scenario: (.*)$", re.MULTILINE)


def _scenario_titles() -> set[str]:
    return set(_SCENARIO_RE.findall(_SPEC.read_text(encoding="utf-8")))


class TestScenarioCoverage(unittest.TestCase):
    def test_scenario_map_exists_and_is_valid_json(self) -> None:
        self.assertTrue(_MAP_PATH.is_file())
        data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertTrue(all(isinstance(v, list) for v in data.values()))

    def test_every_spec_scenario_is_mapped_to_a_test(self) -> None:
        data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
        mapped = set(data)
        scenarios = _scenario_titles()
        self.assertEqual(
            mapped,
            scenarios,
            "the scenario coverage map must name exactly the spec "
            "scenarios, with no extra or missing entries",
        )
        for title, targets in data.items():
            with self.subTest(scenario=title):
                self.assertTrue(
                    targets,
                    f"scenario {title!r} must map to at least one test class",
                )
                for target in targets:
                    self._assert_test_class_exists(title, target)

    def _assert_test_class_exists(self, scenario: str, target: str) -> None:
        module_name, _, class_name = target.rpartition(".")
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - report any import failure
            self.fail(
                f"scenario {scenario!r} maps to {target!r}, but importing "
                f"{module_name!r} failed: {exc}"
            )
        cls = getattr(module, class_name, None)
        if cls is None:
            self.fail(
                f"scenario {scenario!r} maps to {target!r}, but "
                f"{class_name!r} is not defined in {module_name!r}"
            )
        methods = [
            name for name in dir(cls) if name.startswith("test_")
        ]
        self.assertTrue(
            methods,
            f"scenario {scenario!r} maps to {target!r}, but the class "
            "defines no test methods",
        )


class TestPublicResultBoundary(unittest.TestCase):
    def test_public_api_exposes_the_consumer_boundary(self) -> None:
        import docker.npm_environment as pkg

        for name in (
            "preflight",
            "assemble_environment",
            "AssemblyResult",
            "AssemblerEvidence",
            "AssemblerInputIdentity",
            "AssembledOutputIdentity",
        ):
            self.assertIn(name, pkg.__all__)
            self.assertTrue(hasattr(pkg, name), name)

    def test_result_and_evidence_do_not_leak_cache_or_runtime_internals(self) -> None:
        import docker.npm_environment as pkg

        for dto in (pkg.AssemblyResult, pkg.AssemblerEvidence, pkg.AssemblerEvidenceBody):
            fields = {f.name for f in dataclasses.fields(dto)}
            lowered = " ".join(fields).lower()
            for forbidden in (
                "npm_cache",
                "namespace",
                "staging",
                "executor",
                "mount",
                "docker",
            ):
                self.assertNotIn(forbidden, lowered, fields)


if __name__ == "__main__":
    unittest.main()
