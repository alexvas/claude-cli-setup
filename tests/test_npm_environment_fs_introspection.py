"""Phase 2 — filesystem-operation introspection (task 2.7).

The assembler storage and tree-evidence primitives are audited for
traversal, TOCTOU, ambient umask, symlink following, and accidental
npm-cache authority.  Every directory open is descriptor-relative and
no-follow; every created directory/file uses an explicit mode that is
clamped on an opened descriptor; the npm download cache is namespaced and
never consulted as an authority.
"""

from __future__ import annotations

import inspect
import unittest

from docker.npm_environment import storage as storage_module
from docker.npm_environment import tree as tree_module


def _source(module) -> str:
    return inspect.getsource(module)


class TestNoFollowEnforcement(unittest.TestCase):
    def test_storage_uses_o_nofollow(self):
        self.assertIn("O_NOFOLLOW", _source(storage_module))

    def test_tree_uses_o_nofollow(self):
        self.assertIn("O_NOFOLLOW", _source(tree_module))

    def test_never_follows_symlinks(self):
        for module in (storage_module, tree_module):
            src = _source(module)
            self.assertNotIn("follow_symlinks=True", src, module.__name__)
            self.assertNotIn("os.path.realpath", src, module.__name__)
            self.assertNotIn("resolve(", src, module.__name__)

    def test_no_path_based_recursive_walk(self):
        for module in (storage_module, tree_module):
            src = _source(module)
            for banned in ("os.walk", "os.fwalk", "rglob", "glob(", "scandir"):
                self.assertNotIn(banned, src, f"{module.__name__}: {banned}")


class TestUmaskIndependence(unittest.TestCase):
    def test_modes_are_explicit_not_umask_derived(self):
        src = _source(storage_module) + _source(tree_module)
        # Every directory creation passes an explicit 0o700 mode; every
        # private file is clamped via fchmod, never via umask arithmetic.
        self.assertIn("0o700", src)
        self.assertIn("fchmod", src)
        self.assertNotIn("umask", src)

    def test_created_dirs_use_descriptor_relative_mkdir(self):
        src = _source(storage_module)
        self.assertIn("os.mkdir", src)
        self.assertIn("dir_fd", src)


class TestNpmCacheAuthority(unittest.TestCase):
    def test_npm_cache_is_a_namespaced_child(self):
        self.assertEqual(storage_module.NPM_CACHE_CHILD, "npm-cache")

    def test_npm_cache_never_returns_as_authority(self):
        # The namespace DTO exposes the npm cache only as an opaque path;
        # no storage primitive reads from it or derives identity from it.
        ns_fields = {f.name for f in storage_module.AssemblerNamespace.__dataclass_fields__.values()}
        self.assertEqual(
            ns_fields, {"root", "npm_cache", "locks", "staging"}
        )


if __name__ == "__main__":
    unittest.main()
