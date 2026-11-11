"""AC18: unrelated computer jobs share the single General work workspace, which only the person's first computer act creates;
course and project jobs stay with their workspace; an ambiguous request creates nothing (COMPUTER-ADAPTERS.md §7)."""
from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, cli, computer, home, mcp, serve, store
from ros.store import Record

REPO = Path(__file__).resolve().parents[1]
TEMP = REPO / '.test-temp'


class Placement(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        env = patch.dict(os.environ, {'ROS_HOME': str(base / 'home'), 'ROS_NO_VAULT': '1'})
        env.start()
        self.addCleanup(env.stop)
        trusted = patch.object(computer, 'TRUSTED_PARENTS', (str(TEMP),))  # the disposable folders sit under the repository's dot folders
        trusted.start()
        self.addCleanup(trusted.stop)
        self.folder = base / 'downloads'
        self.folder.mkdir()
        self.user = Record(home.init('knowledge'))
        self.addCleanup(self.user.close)
        self.addCleanup(api.release)
        api.call('link', self.user, user_wide=True)
        self.course = Record(home.init('stat303'))
        self.addCleanup(self.course.close)
        api.call('link', self.course, user='knowledge', project='course:stat303', title='STAT303')

    def conversations(self, name):
        rec = Record(home.resolve(name))
        try:
            return [n for n in rec.nodes(type='conversation') if n.get('mode') == 'computer']
        finally:
            rec.close()

    def test_before_the_first_computer_act_nothing_is_created(self):
        before = home.projects()
        out = api.call('engage', self.user, intent='Copy the PDFs in Downloads to my USB stick', kind='computer')
        self.assertEqual(out['status'], 'missing')
        self.assertEqual(out['workspace_id'], computer.GENERAL)
        self.assertIn('http://127.0.0.1', out['portal'])
        self.assertEqual(api.call('computer_plan', self.user, steps=[{'id': 'm', 'op': 'mkdir', 'dst': str(self.folder / 'x')}],
                                  request_ref='request:one')['status'], 'missing')
        self.assertEqual(home.projects(), before, 'no General work, no "me" record, nothing')
        grant = api.call('computer_grant', self.user, roots=[str(self.folder)], ops=['inspect'])
        self.assertEqual(grant['workspace_id'], computer.GENERAL)
        self.assertEqual(sorted(home.projects()), sorted(before + ['general-work']))
        api.call('computer_grant', self.user, roots=[str(self.folder)], ops=['copy'])
        self.assertEqual(len(home.projects()), len(before) + 1, 'one General work, however many acts')

    def test_unrelated_jobs_from_cli_mcp_and_http_on_three_days_share_general_work(self):
        api.call('computer_grant', self.user, roots=[str(self.folder)], ops=['copy'])
        records = sorted(home.projects())
        results = []
        with patch.object(store, 'now', return_value='2026-11-02T09:00:00Z'), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['--project', 'knowledge', '--json', 'engage', '--intent', 'Rename the holiday photos by date', '--kind', 'computer']), 0)
        results.append(json.loads(out.getvalue()))
        with patch.object(store, 'now', return_value='2026-11-03T09:00:00Z'):
            server = mcp.Server('knowledge')
            try:
                answer = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                    'name': 'engage', 'arguments': {'intent': 'Move last year\'s invoices into one folder', 'kind': 'computer'}}})
            finally:
                server.close()
        results.append(answer['result']['structuredContent'])
        with patch.object(store, 'now', return_value='2026-11-04T09:00:00Z'):
            portal = serve.start(self.user, 0)
            try:
                connection = http.client.HTTPConnection('127.0.0.1', portal.server_address[1], timeout=10)
                connection.request('POST', '/api/engage', json.dumps({'intent': 'Tidy the screenshots on my desktop', 'kind': 'computer'}), {'X-ROS': '1'})
                response = connection.getresponse()
                body = json.loads(response.read())
                connection.close()
            finally:
                portal.pool.coordinator.close()
                portal.shutdown()
                portal.server_close()
        self.assertEqual(response.status, 200, body)
        results.append(body['result'])
        for result in results:
            self.assertEqual((result['status'], result['workspace_id'], result['record']), ('resolved', computer.GENERAL, 'general-work'), result)
        self.assertEqual(len({r['conversation'] for r in results}), 3)
        self.assertEqual(sorted(home.projects()), records, 'no new record')
        self.assertEqual(len(self.conversations('general-work')), 3)
        again = api.call('engage', self.user, intent='Tidy the screenshots on my desktop', kind='computer')
        self.assertEqual(again['conversation'], results[2]['conversation'], 'saying it again reuses the conversation')

    def test_a_course_job_stays_with_the_course_and_an_ambiguous_one_creates_nothing(self):
        api.call('computer_grant', self.user, roots=[str(self.folder)], ops=['copy'])
        selected = api.call('workspace_identity', self.course)['workspace_id']
        out = api.call('engage', self.user, intent='Copy the STAT303 slides to my USB stick', kind='computer', workspace_id=selected)
        self.assertEqual((out['workspace_id'], out['record']), (selected, 'stat303'))
        self.assertEqual(api.call('engage', self.course, intent='Collect the problem sets', kind='computer')['record'], 'stat303')
        self.assertEqual(api.call('engage', self.user, intent='Print-ready copies of STAT303 notes', kind='computer')['record'], 'stat303')
        self.assertEqual(len(self.conversations('stat303')), 3)
        self.assertEqual(self.conversations('general-work'), [])
        grant = api.call('computer_grant', self.course, roots=[str(self.folder)], ops=['copy'])
        self.assertEqual(grant['owner_record'], 'stat303')
        self.user.put_node('course:other', 'course', title='STAT303')
        before = sorted(home.projects())
        ambiguous = api.call('engage', self.user, intent='Copy the STAT303 handouts', kind='computer')
        self.assertEqual(ambiguous['status'], 'ambiguous')
        self.assertEqual(len(ambiguous['matches']), 2)
        self.assertNotIn('conversation', ambiguous)
        self.assertEqual(sorted(home.projects()), before)
        self.assertEqual(len(self.conversations('stat303')), 3)


if __name__ == '__main__':
    unittest.main()
