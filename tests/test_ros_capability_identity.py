"""Explicit capability equivalence references evidence; it never merges grades."""
import os
import tempfile
import unittest
from unittest.mock import patch

from ros import api, home
from ros.store import Record


class CapabilityIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'})
        self.env.start()
        self.rec = Record(home.init('knowledge'))
        api.call('link', self.rec, user_wide=True)
        for ident, definition in [('capability:a', 'sample mean'), ('capability:b', 'distribution mean')]:
            self.rec.put_node(ident, 'capability', title='Mean', definition=definition)

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def identity(self, ident):
        return api.call('capability_identity', self.rec, ref={'owner_record': 'knowledge', 'entity_id': ident})

    def test_equal_titles_do_not_merge_and_rename_does_not_reidentify(self):
        a, b = self.identity('capability:a'), self.identity('capability:b')
        self.assertNotEqual(a['canonical'], b['canonical'])
        api.call('organization_rename', self.rec, subject='capability:a', title='Expected sample value')
        self.assertEqual(self.identity('capability:a')['canonical'], a['canonical'])

    def test_verified_revision_binding_and_original_evidence_owner(self):
        a, b = self.identity('capability:a'), self.identity('capability:b')
        self.rec.append('retrieval', 'capability:a', {'day': '2026-11-09', 'outcome': 'pass'}, actor='learner')
        api.call('capability_equivalence', self.rec, alias=b['ref'], canonical=a['ref'],
                 evidence='Reviewed definitions and transfer conditions', verified_by='Researcher')
        out = self.identity('capability:b')
        self.assertEqual(out['canonical'], a['ref'])
        self.assertEqual(len(out['evidence_refs']), 1)
        self.assertEqual(out['evidence_refs'][0]['owner_record'], 'knowledge')
        self.assertEqual(len(self.rec.events(type='retrieval')), 1)
        self.rec.put_node('capability:a', 'capability', title='Mean', definition='different revision')
        stale = self.identity('capability:b')
        self.assertEqual(stale['canonical'], b['ref'])
        self.assertEqual(stale['equivalence_status'], 'stale')

    def test_equivalence_is_human_only_and_requires_revision(self):
        self.assertTrue(api.TOOLS['capability_equivalence'].human)
        with self.assertRaises(ValueError):
            api.call('capability_equivalence', self.rec,
                     alias={'owner_record': 'knowledge', 'entity_id': 'capability:b'},
                     canonical={'owner_record': 'knowledge', 'entity_id': 'capability:a'},
                     evidence='Reviewed', verified_by='Researcher')


if __name__ == '__main__':
    unittest.main()
