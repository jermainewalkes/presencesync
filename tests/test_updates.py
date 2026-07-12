"""Self-update tests — version comparison, the daily check gate, and apply_update
preconditions, all with mocked network and subprocess.

Run:  python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from presencesync.core import updates  # noqa: E402
from presencesync.core.errors import UpdateError  # noqa: E402


class FakeSettings:
    def __init__(self, auto=True, last_check=0.0, notified=""):
        self.auto_check_updates = auto
        self.last_update_check = last_check
        self.last_update_notified = notified
        self.saved = 0

    def save(self):
        self.saved += 1


class IsNewerTests(unittest.TestCase):
    def test_newer_and_older(self):
        self.assertTrue(updates.is_newer("v1.0.2", "1.0.1"))
        self.assertFalse(updates.is_newer("v1.0.1", "1.0.1"))
        self.assertFalse(updates.is_newer("v1.0.0", "1.0.1"))

    def test_v_prefix_and_part_counts(self):
        self.assertTrue(updates.is_newer("2.0", "1.9.9"))
        self.assertTrue(updates.is_newer("v1.10.0", "1.9.0"))
        self.assertFalse(updates.is_newer("1.0", "1.0.0"))

    def test_empty_or_junk_tag(self):
        self.assertFalse(updates.is_newer("", "1.0.1"))
        self.assertFalse(updates.is_newer("latest", "1.0.1"))

    def test_defaults_to_package_version(self):
        self.assertTrue(updates.is_newer("v999.0.0"))


class CheckTests(unittest.TestCase):
    def test_disabled_never_checks(self):
        s = FakeSettings(auto=False)
        with mock.patch.object(updates, "latest_release") as rel:
            self.assertIsNone(updates.check(s))
        rel.assert_not_called()

    def test_daily_gate_skips_network(self):
        s = FakeSettings(last_check=time.time())
        with mock.patch.object(updates, "latest_release") as rel:
            self.assertIsNone(updates.check(s))
        rel.assert_not_called()

    def test_due_check_returns_newer_release(self):
        s = FakeSettings(last_check=0)
        release = updates.Release("v999.0.0", "https://example.test/rel")
        with mock.patch.object(updates, "latest_release", return_value=release):
            self.assertEqual(updates.check(s), release)
        self.assertGreater(s.last_update_check, 0)
        self.assertEqual(s.saved, 1)

    def test_current_release_returns_none(self):
        s = FakeSettings(last_check=0)
        from presencesync import __version__

        with mock.patch.object(updates, "latest_release", return_value=updates.Release(f"v{__version__}", "u")):
            self.assertIsNone(updates.check(s))

    def test_cached_tag_shown_without_network(self):
        s = FakeSettings(last_check=time.time(), notified="v999.0.0")
        with mock.patch.object(updates, "latest_release") as rel:
            result = updates.check(s)
        rel.assert_not_called()
        self.assertEqual(result.tag, "v999.0.0")

    def test_network_failure_is_silent(self):
        s = FakeSettings(last_check=0)
        with mock.patch.object(updates, "latest_release", return_value=None):
            self.assertIsNone(updates.check(s))


def run_result(returncode=0, stdout="", stderr=""):
    m = mock.Mock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        with open(os.path.join(self.root, "requirements.txt"), "w") as f:
            f.write("requests\n")
        patcher = mock.patch.object(updates, "repo_root", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_not_a_checkout_raises(self):
        with mock.patch.object(updates, "repo_root", return_value=None):
            with self.assertRaises(UpdateError):
                updates.apply_update()

    def test_dirty_tree_refuses(self):
        with mock.patch.object(updates.subprocess, "run", return_value=run_result(stdout=" M presencesync/core/sync.py\n")) as run:
            with self.assertRaises(UpdateError):
                updates.apply_update()
        self.assertEqual(run.call_count, 1)  # status only; no pull attempted

    def test_untracked_files_do_not_block(self):
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            if "status" in args:
                return run_result(stdout="?? org-config.json\n")
            return run_result()

        with mock.patch.object(updates.subprocess, "run", side_effect=fake_run):
            updates.apply_update()
        self.assertIn("pull", calls[1])
        self.assertIn("--ff-only", calls[1])
        self.assertIn("pip", calls[2])

    def test_pull_failure_surfaces_stderr(self):
        def fake_run(args, **kw):
            if "status" in args:
                return run_result()
            return run_result(returncode=1, stderr="fatal: Not possible to fast-forward")

        with mock.patch.object(updates.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(UpdateError) as ctx:
                updates.apply_update()
        self.assertIn("fast-forward", str(ctx.exception))


class LatestReleaseTests(unittest.TestCase):
    def test_parses_tag_and_url(self):
        resp = mock.Mock()
        resp.json.return_value = {"tag_name": "v1.2.0", "html_url": "https://example.test/v1.2.0"}
        with mock.patch.object(updates.requests, "get", return_value=resp):
            rel = updates.latest_release()
        self.assertEqual(rel, updates.Release("v1.2.0", "https://example.test/v1.2.0"))

    def test_missing_tag_returns_none(self):
        resp = mock.Mock()
        resp.json.return_value = {"message": "Not Found"}
        with mock.patch.object(updates.requests, "get", return_value=resp):
            self.assertIsNone(updates.latest_release())

    def test_network_error_returns_none(self):
        with mock.patch.object(updates.requests, "get", side_effect=updates.requests.ConnectionError("down")):
            self.assertIsNone(updates.latest_release())


if __name__ == "__main__":
    unittest.main(verbosity=2)
