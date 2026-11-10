"""Credential references (S4): a profile names where a key lives, never the key. No real provider is contacted.

The Windows Credential Manager case writes, replaces and deletes one uuid-named entry in the Research OS namespace and
never reads any other entry."""
import json
import os
import unittest
import uuid
from unittest.mock import patch

from ros.lib import credentials

SENTINEL = "sk-test-" + uuid.uuid4().hex  # looks like a key, belongs to no service


class References(unittest.TestCase):
    def test_env_and_os_references_are_normalised(self):
        self.assertEqual(credentials.reference({"store": "env", "name": "ROS_TEST_KEY"}), {"store": "env", "name": "ROS_TEST_KEY"})
        self.assertEqual(credentials.reference({"store": "os", "name": "ResearchOS:fixture"}), {"store": "os", "name": "ResearchOS:fixture"})

    def test_a_value_is_never_accepted_and_never_echoed(self):
        for bad in ({"store": "env", "name": "X", "value": SENTINEL}, {"store": "env", "name": SENTINEL}, {"store": "env", "secret": SENTINEL},
                    {"store": "os", "name": SENTINEL}, {"store": "file", "name": "X"}, SENTINEL, None, ["env", "X"]):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(credentials.CredentialInvalid) as caught:
                credentials.reference(bad)
            self.assertNotIn(SENTINEL, str(caught.exception))
            self.assertNotIn(SENTINEL[8:], str(caught.exception))

    def test_os_names_outside_the_namespace_are_refused_before_any_store_read(self):
        def never(*args): raise AssertionError("the store was read")
        with patch.object(credentials, "_os_read", never):
            for name in ("git:https://github.com", "Microsoft_OC1:uri", "ResearchOS", "ResearchOS:", "ResearchOS:../x", "researchos:lower"):
                with self.subTest(name=name), self.assertRaises(credentials.CredentialInvalid):
                    credentials.resolve({"store": "os", "name": name})


class Resolution(unittest.TestCase):
    def test_env_secret_is_opaque(self):
        with patch.dict(os.environ, {"ROS_TEST_KEY": SENTINEL}):
            secret = credentials.resolve({"store": "env", "name": "ROS_TEST_KEY"})
        self.assertEqual(secret.reveal(), SENTINEL)
        for text in (str(secret), repr(secret), f"{secret}", "%s" % secret):
            self.assertNotIn(SENTINEL, text)
        with self.assertRaises(TypeError): json.dumps({"key": secret})
        with self.assertRaises(TypeError):
            import pickle; pickle.dumps(secret)

    def test_missing_empty_replaced_and_revoked_env_credentials(self):
        ref = {"store": "env", "name": "ROS_TEST_KEY"}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROS_TEST_KEY", None)
            with self.assertRaises(credentials.CredentialMissing) as caught: credentials.resolve(ref)
            self.assertIn("ROS_TEST_KEY", str(caught.exception))
            self.assertEqual(credentials.status(ref), "missing")
            os.environ["ROS_TEST_KEY"] = "   "
            with self.assertRaises(credentials.CredentialMissing): credentials.resolve(ref)
            os.environ["ROS_TEST_KEY"] = SENTINEL
            self.assertEqual(credentials.resolve(ref).reveal(), SENTINEL)
            self.assertEqual(credentials.status(ref), "present")
            os.environ["ROS_TEST_KEY"] = SENTINEL + "-replaced"  # replacement is read on the next use, nothing is cached
            self.assertEqual(credentials.resolve(ref).reveal(), SENTINEL + "-replaced")
            del os.environ["ROS_TEST_KEY"]  # revocation
            with self.assertRaises(credentials.CredentialMissing): credentials.resolve(ref)

    def test_os_store_absent_is_explicitly_unavailable(self):
        with patch.object(credentials, "_advapi", lambda: None):
            self.assertFalse(credentials.os_store_available())
            self.assertEqual(credentials.status({"store": "os", "name": "ResearchOS:fixture"}), "unavailable")
            with self.assertRaises(credentials.CredentialUnavailable): credentials.resolve({"store": "os", "name": "ResearchOS:fixture"})
            with self.assertRaises(credentials.CredentialUnavailable): credentials.os_store_write("ResearchOS:fixture", SENTINEL)

    def test_error_classes_are_value_errors_with_codes(self):
        for cls, code in ((credentials.CredentialInvalid, "credential_reference_invalid"), (credentials.CredentialMissing, "credential_missing"),
                          (credentials.CredentialUnavailable, "credential_store_unavailable")):
            self.assertTrue(issubclass(cls, credentials.CredentialError) and issubclass(cls, ValueError))
            self.assertEqual(cls.code, code)

    def test_scrub_removes_the_exact_value(self):
        with patch.dict(os.environ, {"ROS_TEST_KEY": SENTINEL}):
            secret = credentials.resolve({"store": "env", "name": "ROS_TEST_KEY"})
        self.assertEqual(credentials.scrub("server said " + SENTINEL + " is bad", secret), "server said [hidden] is bad")
        self.assertEqual(credentials.scrub("nothing", None), "nothing")


@unittest.skipUnless(os.name == "nt", "Windows Credential Manager")
class WindowsStore(unittest.TestCase):
    def test_write_read_replace_delete_one_namespaced_entry(self):
        name = "ResearchOS:test-" + uuid.uuid4().hex
        self.addCleanup(credentials.os_store_delete, name)
        self.assertTrue(credentials.os_store_available())
        ref = {"store": "os", "name": name}
        self.assertEqual(credentials.status(ref), "missing")
        with self.assertRaises(credentials.CredentialMissing): credentials.resolve(ref)
        credentials.os_store_write(name, SENTINEL)
        self.assertEqual(credentials.resolve(ref).reveal(), SENTINEL)
        credentials.os_store_write(name, SENTINEL + "-replaced")
        self.assertEqual(credentials.resolve(ref).reveal(), SENTINEL + "-replaced")
        self.assertTrue(credentials.os_store_delete(name))
        self.assertFalse(credentials.os_store_delete(name))
        with self.assertRaises(credentials.CredentialMissing): credentials.resolve(ref)

    def test_writes_outside_the_namespace_are_refused(self):
        with self.assertRaises(credentials.CredentialInvalid): credentials.os_store_write("git:https://example.invalid", SENTINEL)
        with self.assertRaises(credentials.CredentialInvalid): credentials.os_store_delete("git:https://example.invalid")


if __name__ == "__main__":
    unittest.main()
