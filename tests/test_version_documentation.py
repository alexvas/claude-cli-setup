"""Consistency checks for the maintained workflow documentation."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READMES = ("README.md", "README.en.md", "README.zh.md")
HEADINGS = {
    "README.md": (
        "## Требования", "## 1. Сборка окружения", "## 2. Запуск окружения",
        "## 3. Обновление компонентов окружения", "## Обслуживание",
        "## Устранение неполадок",
    ),
    "README.en.md": (
        "## Requirements", "## 1. Build the environment", "## 2. Launch the environment",
        "## 3. Update environment components", "## Maintenance", "## Troubleshooting",
    ),
    "README.zh.md": (
        "## 要求", "## 1. 构建环境", "## 2. 启动环境", "## 3. 更新环境组件",
        "## 维护", "## 故障排除",
    ),
}


class TestVersionDocumentation(unittest.TestCase):
    def _documents(self):
        for name in READMES:
            yield name, (ROOT / name).read_text(encoding="utf-8")

    def test_workflow_structure_is_equivalent(self):
        for name, text in self._documents():
            with self.subTest(readme=name):
                positions = [text.index(heading) for heading in HEADINGS[name]]
                self.assertEqual(positions, sorted(positions))
                self.assertNotRegex(text, r"(?m)^## (Setup|Настройка|设置)$")

    def test_focused_pi_update_workflow(self):
        required = (
            "stages.pi-tools.pi", "./docker/versions.py check-updates",
            "--only stages.pi-tools.pi", "--suggest", "non-mutating",
            "versions.toml", "./docker/versions.py validate", "git diff -- versions.toml",
            "./docker/versions.py compose build pi", "./docker/verify-runtime.sh",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in required:
                    self.assertIn(token, text)

    def test_update_options_are_grouped(self):
        required = (
            "--only", "--suggest", "--json", "--strict", "--fail-on-outdated",
            "--include-prerelease", "--cache-ttl", "--cache-dir", "--no-cache",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in required:
                    self.assertIn(token, text)

    def test_component_taxonomy_and_ownership(self):
        required = (
            "Base image", "Toolchain", "Node CLIs", "Prebuilt binaries",
            "Shell runtime", "Pi extensions", "Debian packages", "/home/dev/.pi",
            "runtime.pi-extensions", "OCI",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in required:
                    self.assertIn(token, text)
                self.assertRegex(text, re.compile(r"Debian.*versions\.toml", re.I | re.S))

    def test_commands_and_safe_maintenance_guidance(self):
        required = (
            "./docker/versions.py validate", "./docker/versions.py env",
            "./docker/versions.py compose", "./launch-pi.py",
            "/home/dev/install-pi-extensions.sh", "docker system df -v",
            "docker builder prune", "<docker-dev>:<docker-dev>",
            "chmod -R ug+rwX", "usermod -aG <docker-dev>", "100999",
            "rootless Docker",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in required:
                    self.assertIn(token, text)

    def test_no_selected_versions_or_removed_development_notes(self):
        inventory = (ROOT / "versions.toml").read_text(encoding="utf-8")
        selected = set(re.findall(r'^(?:version|revision)\s*=\s*"([^"]+)"', inventory, re.M))
        forbidden_phrases = ("BuildKit cache verification", "Проверка кеширования BuildKit", "BuildKit 缓存验证")
        for name, text in self._documents():
            with self.subTest(readme=name):
                for value in selected:
                    self.assertNotIn(value, text)
                for phrase in forbidden_phrases:
                    self.assertNotIn(phrase, text)

    def test_restricted_override_grammar_remains_documented(self):
        for name, text in self._documents():
            with self.subTest(readme=name):
                self.assertIn("--override stages.toolchain.python.version=X.Y.Z", text)
                self.assertIn("==, >, >=, <, <=", text)
                self.assertIn("prerelease", text.lower())


if __name__ == "__main__":
    unittest.main()
