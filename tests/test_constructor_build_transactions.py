"""Phase 2 RED/GREEN contracts for serialized build-cache state."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import time
from unittest import mock

from docker.versioning.build_cache import (
    UNCOMMITTED_TTL_SECONDS,
    BuildCacheError,
    BuildTransactionError,
    CheckoutBuildTransaction,
    acquire_checkout_build_lock,
    build_blob_path,
    commit_build_set,
    maintain_uncommitted_blobs,
    mark_uncommitted_blob,
    prepare_build_cache,
    publish_verified_blob,
    recover_abandoned_snapshots,
)
from docker.versioning.digest_identity import DigestIdentity


def _acquire_pristine_lock(checkout: str, start: multiprocessing.Event, results: multiprocessing.Queue) -> None:
    """Child-process helper for concurrent first-build lock bootstrap."""
    start.wait()
    try:
        with acquire_checkout_build_lock(checkout):
            results.put("acquired")
            time.sleep(0.2)
    except BuildTransactionError as exc:
        results.put(str(exc))
    except BaseException as exc:
        results.put(f"unexpected: {type(exc).__name__}: {exc}")


class BuildTransactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkout = Path(self.tmp.name) / "checkout"
        self.checkout.mkdir()

    def blob(self, payload: bytes) -> DigestIdentity:
        identity = DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())
        publish_verified_blob(identity, payload, checkout_root=self.checkout)
        return identity

    def test_simultaneous_pristine_checkout_bootstrap_serializes_builds(self) -> None:
        checkout = Path(self.tmp.name) / "pristine-checkout"
        checkout.mkdir()
        context = multiprocessing.get_context("fork")
        start = context.Event()
        results = context.Queue()
        workers = [
            context.Process(target=_acquire_pristine_lock, args=(str(checkout), start, results))
            for _ in range(4)
        ]
        for worker in workers:
            worker.start()
        start.set()
        for worker in workers:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), "lock contender did not terminate")
        outcomes = [results.get(timeout=1) for _ in workers]
        self.assertIn("acquired", outcomes)
        self.assertTrue(
            all(value == "acquired" or "active build" in value for value in outcomes),
            outcomes,
        )

    def test_competing_process_is_rejected_before_any_mutation(self) -> None:
        with acquire_checkout_build_lock(self.checkout):
            command = (
                "from docker.versioning.build_cache import acquire_checkout_build_lock; "
                f"acquire_checkout_build_lock({str(self.checkout)!r})"
            )
            result = subprocess.run([sys.executable, "-c", command], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active build", result.stderr)
        self.assertFalse((prepare_build_cache(self.checkout).generated_root / "other").exists())

    def test_hard_linked_lock_is_rejected_without_chmodding_link_target(self) -> None:
        paths = prepare_build_cache(self.checkout)
        unrelated = self.checkout / "unrelated-owner-file"
        unrelated.write_bytes(b"must retain mode")
        unrelated.chmod(0o644)
        lock_path = paths.persistent_root / "build.lock"
        lock_path.hardlink_to(unrelated)
        with self.assertRaisesRegex(BuildTransactionError, "unsafe checkout build lock"):
            acquire_checkout_build_lock(self.checkout)
        self.assertEqual(0o644, unrelated.stat().st_mode & 0o777)
        self.assertEqual(2, unrelated.stat().st_nlink)

    def test_competing_lock_does_not_repair_owner_lock_mode(self) -> None:
        paths = prepare_build_cache(self.checkout)
        lock_path = paths.persistent_root / "build.lock"
        with acquire_checkout_build_lock(self.checkout):
            lock_path.chmod(0o644)
            command = (
                "from docker.versioning.build_cache import acquire_checkout_build_lock; "
                f"acquire_checkout_build_lock({str(self.checkout)!r})"
            )
            result = subprocess.run([sys.executable, "-c", command], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("active build", result.stderr)
            self.assertEqual(0o644, lock_path.stat().st_mode & 0o777)
        with acquire_checkout_build_lock(self.checkout):
            self.assertEqual(0o600, lock_path.stat().st_mode & 0o777)

    def test_competing_lock_does_not_repair_unsafe_cache_state(self) -> None:
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout):
            paths.persistent_root.chmod(0o777)
            command = (
                "from docker.versioning.build_cache import acquire_checkout_build_lock; "
                f"acquire_checkout_build_lock({str(self.checkout)!r})"
            )
            result = subprocess.run([sys.executable, "-c", command], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("active build", result.stderr)
            self.assertEqual(0o777, paths.persistent_root.stat().st_mode & 0o777)
            self.assertFalse((paths.persistent_root / "committed-build.json").exists())
            self.assertFalse(any(paths.markers_root.iterdir()))
            self.assertFalse(any(paths.generated_root.iterdir()))

    def test_lock_releases_after_exception_and_normal_exit(self) -> None:
        with self.assertRaises(RuntimeError):
            with acquire_checkout_build_lock(self.checkout):
                raise RuntimeError("interrupted owner")
        with acquire_checkout_build_lock(self.checkout):
            pass
        with acquire_checkout_build_lock(self.checkout):
            pass

    def test_startup_maintenance_failure_releases_lock(self) -> None:
        with mock.patch(
            "docker.versioning.build_cache.maintain_uncommitted_blobs",
            side_effect=RuntimeError("maintenance failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "maintenance failed"):
                with CheckoutBuildTransaction(self.checkout):
                    pass
        with CheckoutBuildTransaction(self.checkout):
            pass

    def test_recovery_needs_live_lock_and_preserves_blobs(self) -> None:
        identity = self.blob(b"reusable")
        paths = prepare_build_cache(self.checkout)
        abandoned = paths.generated_root / "abandoned"
        abandoned.mkdir()
        (abandoned / "snapshot").write_text("partial")
        with self.assertRaises(TypeError):
            recover_abandoned_snapshots(self.checkout)  # type: ignore[call-arg]
        # A later transaction acquires the live checkout lock before recovery.
        with CheckoutBuildTransaction(self.checkout):
            self.assertFalse(abandoned.exists())
            self.assertTrue(build_blob_path(paths.blobs_root, identity).exists())

    def test_manifest_is_atomic_and_commit_precedes_superseded_delete(self) -> None:
        old, new = self.blob(b"old"), self.blob(b"new")
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout) as lock:
            mark_uncommitted_blob(old, self.checkout, lock=lock, verified_at=0)
            commit_build_set(self.checkout, {old}, lock=lock)
            old_path = build_blob_path(paths.blobs_root, old)
            self.assertTrue(old_path.exists())
            commit_build_set(self.checkout, {new}, lock=lock)
        self.assertEqual(
            {"blobs": [f"sha256:{new.hex_digest()}"]},
            json.loads((paths.persistent_root / "committed-build.json").read_text()),
        )
        self.assertFalse(old_path.exists())
        self.assertTrue(build_blob_path(paths.blobs_root, new).exists())

    def test_failed_build_keeps_prior_live_set_and_shared_xdg_is_untouched(self) -> None:
        committed, failed = self.blob(b"committed"), self.blob(b"failed")
        xdg = Path(self.tmp.name) / "xdg-runtime-artifact"
        xdg.write_bytes(b"unrelated")
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout) as lock:
            commit_build_set(self.checkout, {committed}, lock=lock)
            mark_uncommitted_blob(failed, self.checkout, lock=lock, verified_at=1)
            # No commit models Docker failure/interruption.
            maintain_uncommitted_blobs(self.checkout, lock=lock, now=2)
        self.assertTrue(build_blob_path(paths.blobs_root, committed).exists())
        self.assertTrue(build_blob_path(paths.blobs_root, failed).exists())
        self.assertEqual(b"unrelated", xdg.read_bytes())

    def test_interrupted_publication_leaves_marker_for_missing_blob_recovery(self) -> None:
        payload = b"interrupted-before-publish"
        identity = DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout) as lock:
            with mock.patch(
                "docker.versioning.build_cache.publish_verified_blob",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    from docker.versioning.build_cache import publish_uncommitted_blob
                    publish_uncommitted_blob(identity, payload, checkout_root=self.checkout, lock=lock)
            self.assertTrue((paths.markers_root / f"sha256:{identity.hex_digest()}.json").exists())
            self.assertFalse(build_blob_path(paths.blobs_root, identity).exists())
            maintain_uncommitted_blobs(self.checkout, lock=lock, now=0)
        self.assertFalse((paths.markers_root / f"sha256:{identity.hex_digest()}.json").exists())

    def test_interruption_after_publication_retains_expiring_marker(self) -> None:
        payload = b"interrupted-after-publish"
        identity = DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())
        paths = prepare_build_cache(self.checkout)
        original = publish_verified_blob

        def publish_then_interrupt(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt()

        with acquire_checkout_build_lock(self.checkout) as lock:
            with mock.patch(
                "docker.versioning.build_cache.publish_verified_blob",
                side_effect=publish_then_interrupt,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    from docker.versioning.build_cache import publish_uncommitted_blob
                    publish_uncommitted_blob(
                        identity, payload, checkout_root=self.checkout, lock=lock, verified_at=100,
                    )
            self.assertTrue(build_blob_path(paths.blobs_root, identity).exists())
            self.assertTrue((paths.markers_root / f"sha256:{identity.hex_digest()}.json").exists())
            maintain_uncommitted_blobs(
                self.checkout, lock=lock, now=100 + UNCOMMITTED_TTL_SECONDS,
            )
        self.assertFalse(build_blob_path(paths.blobs_root, identity).exists())
        self.assertFalse((paths.markers_root / f"sha256:{identity.hex_digest()}.json").exists())

    def test_post_publication_failure_preserves_marker_until_maintenance(self) -> None:
        payload = b"post-publication-failure"
        identity = DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())
        paths = prepare_build_cache(self.checkout)
        original = publish_verified_blob

        def publish_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("final verification interrupted")

        with acquire_checkout_build_lock(self.checkout) as lock:
            with mock.patch(
                "docker.versioning.build_cache.publish_verified_blob",
                side_effect=publish_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "final verification interrupted"):
                    from docker.versioning.build_cache import publish_uncommitted_blob
                    publish_uncommitted_blob(
                        identity, payload, checkout_root=self.checkout, lock=lock, verified_at=100,
                    )
            marker = paths.markers_root / f"sha256:{identity.hex_digest()}.json"
            self.assertTrue(build_blob_path(paths.blobs_root, identity).exists())
            self.assertTrue(marker.exists())
            maintain_uncommitted_blobs(self.checkout, lock=lock, now=101)
            self.assertTrue(marker.exists())
            blob = build_blob_path(paths.blobs_root, identity)
            blob.chmod(0o644)
            maintain_uncommitted_blobs(self.checkout, lock=lock, now=102)
        self.assertFalse(blob.exists())
        self.assertFalse(marker.exists())

    def test_mismatched_republication_preserves_existing_blob_and_marker(self) -> None:
        payload = b"original-publication"
        identity = DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())
        paths = prepare_build_cache(self.checkout)
        with CheckoutBuildTransaction(self.checkout) as transaction:
            transaction.publish_verified_blob(identity, payload, verified_at=100)
        blob = build_blob_path(paths.blobs_root, identity)
        marker = paths.markers_root / f"sha256:{identity.hex_digest()}.json"
        original_blob = blob.read_bytes()
        original_marker = marker.read_bytes()
        with CheckoutBuildTransaction(self.checkout, now=100) as transaction:
            with self.assertRaisesRegex(Exception, "digest mismatch"):
                transaction.publish_verified_blob(identity, b"mismatched", verified_at=200)
        self.assertEqual(original_blob, blob.read_bytes())
        self.assertEqual(original_marker, marker.read_bytes())

    def test_transaction_publication_marks_blob_and_failed_blob_expires(self) -> None:
        payload = b"failed-download"
        identity = DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())
        paths = prepare_build_cache(self.checkout)
        with CheckoutBuildTransaction(self.checkout, now=100) as transaction:
            transaction.publish_verified_blob(identity, payload, verified_at=100)
            self.assertEqual(
                {"verified_at": 100},
                json.loads((paths.markers_root / f"sha256:{identity.hex_digest()}.json").read_text()),
            )
            # No commit models a failed/interrupted transaction.
        with CheckoutBuildTransaction(
            self.checkout, now=100 + UNCOMMITTED_TTL_SECONDS,
        ):
            pass
        self.assertFalse(build_blob_path(paths.blobs_root, identity).exists())

    def test_corrupt_stale_marker_never_deletes_committed_blob(self) -> None:
        identity = self.blob(b"committed-marker-immunity")
        paths = prepare_build_cache(self.checkout)
        marker = paths.markers_root / f"sha256:{identity.hex_digest()}.json"
        with acquire_checkout_build_lock(self.checkout) as lock:
            commit_build_set(self.checkout, {identity}, lock=lock)
        marker.write_text('{"verified_at":NaN}')
        with acquire_checkout_build_lock(self.checkout) as lock:
            maintain_uncommitted_blobs(self.checkout, lock=lock, now=1)
        self.assertFalse(marker.exists())
        self.assertTrue(build_blob_path(paths.blobs_root, identity).exists())

    def test_interrupted_commit_cleanup_recovers_on_next_transaction(self) -> None:
        previous, replacement = self.blob(b"previous-live"), self.blob(b"replacement-live")
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout) as lock:
            commit_build_set(self.checkout, {previous}, lock=lock)
        with acquire_checkout_build_lock(self.checkout) as lock:
            with mock.patch(
                "docker.versioning.build_cache._recover_pending_cleanup",
                side_effect=KeyboardInterrupt(),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    commit_build_set(self.checkout, {replacement}, lock=lock)
        self.assertTrue(build_blob_path(paths.blobs_root, previous).exists())
        self.assertTrue((paths.persistent_root / "pending-build-cleanup.json").exists())
        with CheckoutBuildTransaction(self.checkout):
            pass
        self.assertFalse(build_blob_path(paths.blobs_root, previous).exists())
        self.assertTrue(build_blob_path(paths.blobs_root, replacement).exists())
        self.assertFalse((paths.persistent_root / "pending-build-cleanup.json").exists())

    def test_interrupted_cleanup_retries_safely_on_next_transaction(self) -> None:
        first, second, replacement = self.blob(b"old-one"), self.blob(b"old-two"), self.blob(b"new")
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout) as lock:
            commit_build_set(self.checkout, {first, second}, lock=lock)
        from docker.versioning.build_cache import _remove_blob_and_marker
        calls = 0

        def remove_once_then_interrupt(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt()
            return _remove_blob_and_marker(*args, **kwargs)

        with acquire_checkout_build_lock(self.checkout) as lock:
            with mock.patch(
                "docker.versioning.build_cache._remove_blob_and_marker",
                side_effect=remove_once_then_interrupt,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    commit_build_set(self.checkout, {replacement}, lock=lock)
        self.assertTrue((paths.persistent_root / "pending-build-cleanup.json").exists())
        with CheckoutBuildTransaction(self.checkout):
            pass
        self.assertFalse(build_blob_path(paths.blobs_root, first).exists())
        self.assertFalse(build_blob_path(paths.blobs_root, second).exists())
        self.assertTrue(build_blob_path(paths.blobs_root, replacement).exists())
        self.assertFalse((paths.persistent_root / "pending-build-cleanup.json").exists())

    def test_exact_ttl_boundary_and_committed_immunity(self) -> None:
        expired, committed = self.blob(b"expired"), self.blob(b"committed")
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout) as lock:
            mark_uncommitted_blob(expired, self.checkout, lock=lock, verified_at=100)
            mark_uncommitted_blob(committed, self.checkout, lock=lock, verified_at=0)
            commit_build_set(self.checkout, {committed}, lock=lock)
            maintain_uncommitted_blobs(
                self.checkout, lock=lock, now=100 + UNCOMMITTED_TTL_SECONDS - 1,
            )
            self.assertTrue(build_blob_path(paths.blobs_root, expired).exists())
            maintain_uncommitted_blobs(
                self.checkout, lock=lock, now=100 + UNCOMMITTED_TTL_SECONDS,
            )
        self.assertFalse(build_blob_path(paths.blobs_root, expired).exists())
        self.assertTrue(build_blob_path(paths.blobs_root, committed).exists())

    def test_invalid_commit_blob_preserves_previous_manifest_and_blobs(self) -> None:
        previous = self.blob(b"previous")
        paths = prepare_build_cache(self.checkout)
        with acquire_checkout_build_lock(self.checkout) as lock:
            commit_build_set(self.checkout, {previous}, lock=lock)
        manifest = paths.persistent_root / "committed-build.json"
        original_manifest = manifest.read_text()
        cases = ("missing", "altered", "writable")
        for case in cases:
            with self.subTest(case=case):
                payload = f"{case}-commit".encode()
                candidate = DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())
                if case != "missing":
                    candidate_path = publish_verified_blob(candidate, payload, checkout_root=self.checkout)
                    if case == "altered":
                        candidate_path.chmod(0o644)
                        candidate_path.write_bytes(b"altered")
                        candidate_path.chmod(0o444)
                    else:
                        candidate_path.chmod(0o644)
                with acquire_checkout_build_lock(self.checkout) as lock:
                    with self.assertRaises(BuildTransactionError):
                        commit_build_set(self.checkout, {candidate}, lock=lock)
                self.assertEqual(original_manifest, manifest.read_text())
                self.assertTrue(build_blob_path(paths.blobs_root, previous).exists())

    def test_corrupt_manifest_keys_fail_without_any_deletion(self) -> None:
        identity = self.blob(b"live")
        paths = prepare_build_cache(self.checkout)
        manifest = paths.persistent_root / "committed-build.json"
        outside = Path(self.tmp.name) / "outside"
        outside.write_bytes(b"must not delete")
        invalid_keys = (
            "sha256:../../outside",
            "md5:" + "0" * 32,
            "sha256:abc",
            "SHA256:" + identity.hex_digest(),
            "sha256:" + identity.hex_digest().upper(),
        )
        for key in invalid_keys:
            with self.subTest(key=key):
                original = json.dumps({"blobs": [key]})
                manifest.write_text(original)
                with acquire_checkout_build_lock(self.checkout) as lock:
                    with self.assertRaises(BuildTransactionError):
                        commit_build_set(self.checkout, {identity}, lock=lock)
                self.assertEqual(original, manifest.read_text())
                self.assertTrue(outside.exists())
                self.assertTrue(build_blob_path(paths.blobs_root, identity).exists())

    def test_marker_creation_rejects_non_finite_timestamps(self) -> None:
        identity = self.blob(b"timestamp")
        for timestamp in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(timestamp=timestamp):
                with acquire_checkout_build_lock(self.checkout) as lock:
                    with self.assertRaises(BuildCacheError):
                        mark_uncommitted_blob(
                            identity, self.checkout, lock=lock, verified_at=timestamp,
                        )

    def test_non_finite_marker_and_clock_values_are_rejected(self) -> None:
        for timestamp in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(marker_timestamp=timestamp):
                payload = f"marker-{timestamp}".encode()
                identity = self.blob(payload)
                paths = prepare_build_cache(self.checkout)
                marker = paths.markers_root / f"sha256:{identity.hex_digest()}.json"
                marker.write_text(f'{{"verified_at":{timestamp}}}')
                with acquire_checkout_build_lock(self.checkout) as lock:
                    maintain_uncommitted_blobs(self.checkout, lock=lock, now=1)
                self.assertFalse(marker.exists())
                self.assertFalse(build_blob_path(paths.blobs_root, identity).exists())

        huge_identity = self.blob(b"huge-marker")
        huge_paths = prepare_build_cache(self.checkout)
        huge_marker = huge_paths.markers_root / f"sha256:{huge_identity.hex_digest()}.json"
        huge_marker.write_text('{"verified_at":' + '1' + ('0' * 4000) + '}')
        with acquire_checkout_build_lock(self.checkout) as lock:
            maintain_uncommitted_blobs(self.checkout, lock=lock, now=1)
        self.assertFalse(huge_marker.exists())
        self.assertFalse(build_blob_path(huge_paths.blobs_root, huge_identity).exists())

        identity = self.blob(b"expired-with-invalid-clock")
        paths = prepare_build_cache(self.checkout)
        for clock in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(clock=clock):
                with acquire_checkout_build_lock(self.checkout) as lock:
                    mark_uncommitted_blob(identity, self.checkout, lock=lock, verified_at=0)
                    with self.assertRaises(BuildCacheError):
                        maintain_uncommitted_blobs(self.checkout, lock=lock, now=clock)
                self.assertTrue(build_blob_path(paths.blobs_root, identity).exists())
                self.assertTrue((paths.markers_root / f"sha256:{identity.hex_digest()}.json").exists())

    def test_valid_marker_with_unsafe_blob_is_removed_immediately(self) -> None:
        cases = ("missing", "altered", "writable")
        for case in cases:
            with self.subTest(case=case):
                payload = f"{case}-blob".encode()
                identity = self.blob(payload)
                paths = prepare_build_cache(self.checkout)
                blob = build_blob_path(paths.blobs_root, identity)
                with acquire_checkout_build_lock(self.checkout) as lock:
                    mark_uncommitted_blob(identity, self.checkout, lock=lock, verified_at=0)
                    if case == "missing":
                        blob.unlink()
                    elif case == "altered":
                        blob.chmod(0o644)
                        blob.write_bytes(b"altered")
                        blob.chmod(0o444)
                    else:
                        blob.chmod(0o644)
                    maintain_uncommitted_blobs(self.checkout, lock=lock, now=1)
                self.assertFalse(blob.exists())
                self.assertFalse((paths.markers_root / f"sha256:{identity.hex_digest()}.json").exists())

    def test_corrupt_marker_removes_partial_blob_immediately(self) -> None:
        identity = self.blob(b"partial")
        paths = prepare_build_cache(self.checkout)
        marker = paths.markers_root / f"sha256:{identity.hex_digest()}.json"
        marker.write_text("not-json")
        with acquire_checkout_build_lock(self.checkout) as lock:
            maintain_uncommitted_blobs(self.checkout, lock=lock, now=0)
        self.assertFalse(marker.exists())
        self.assertFalse(build_blob_path(paths.blobs_root, identity).exists())


if __name__ == "__main__":
    unittest.main()
