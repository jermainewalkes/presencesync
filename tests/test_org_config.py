"""Org-config seeding tests using a temp file and fake secret store."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from presencesync.core import org_config  # noqa: E402
from presencesync.core.store import Settings  # noqa: E402


class FakeSecrets:
    def __init__(self, secret=""):
        self.secret = secret

    def get_slack_client_secret(self):
        return self.secret

    def set_slack_client_secret(self, value):
        self.secret = value


def write_config(directory, **fields):
    path = os.path.join(directory, "org-config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fields, f)
    return path


class OrgConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = mock.patch.object(org_config, "_candidate_paths",
                                    return_value=[os.path.join(self.tmp, "org-config.json")])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.save = mock.patch.object(Settings, "save")
        self.save.start()
        self.addCleanup(self.save.stop)

    def test_seeds_empty_fields(self):
        write_config(self.tmp, ms_tenant_id="T1", ms_client_id="C1",
                     slack_client_id="S1", slack_client_secret="SEC")
        settings, secrets = Settings(), FakeSecrets()
        self.assertTrue(org_config.seed_if_present(settings, secrets))
        self.assertEqual(settings.ms_tenant_id, "T1")
        self.assertEqual(settings.ms_client_id, "C1")
        self.assertEqual(settings.slack_client_id, "S1")
        self.assertEqual(secrets.secret, "SEC")

    def test_does_not_overwrite_user_values(self):
        write_config(self.tmp, ms_tenant_id="T1", slack_client_secret="SEC")
        settings, secrets = Settings(ms_tenant_id="USER"), FakeSecrets("USERSEC")
        org_config.seed_if_present(settings, secrets)
        self.assertEqual(settings.ms_tenant_id, "USER")
        self.assertEqual(secrets.secret, "USERSEC")

    def test_no_file_is_noop(self):
        settings, secrets = Settings(), FakeSecrets()
        self.assertFalse(org_config.seed_if_present(settings, secrets))
        self.assertEqual(settings.ms_tenant_id, "")

    def test_invalid_json_is_ignored(self):
        with open(os.path.join(self.tmp, "org-config.json"), "w") as f:
            f.write("{not json")
        self.assertFalse(org_config.seed_if_present(Settings(), FakeSecrets()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
