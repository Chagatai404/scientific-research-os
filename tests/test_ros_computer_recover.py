"""Desktop start recovers computer work in every workspace record that holds any (General work and courses), not only the
default record: a crashed unit becomes interrupted and resumable instead of staying running (COMPUTER-ADAPTERS.md §10)."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from ros import api, computer, desktop, home, runtime
from ros.store import Record
from test_ros_computer_files import ComputerFixture


class RecoverAtStart(ComputerFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        api.call('workspace_ensure', self.user, kind='general', title='General work', key='general')
        self.course = Record(home.init('stat303'))
        self.addCleanup(self.course.close)
        api.call('link', self.course, user='knowledge', project='course:stat303', title='STAT303')
        self.course_id = api.call('workspace_identity', self.course)['workspace_id']

    def crashed(self, workspace_id, name):
        source = self.write(self.src / name, b'data ' + name.encode())
        self.grant(workspace_id=workspace_id)
        view = self.plan([{'id': 'c', 'op': 'copy', 'src': str(source), 'dst': str(self.dst)}], workspace_id=workspace_id)
        unit = api.call('computer_run', self.user, plan=view['plan'], revision=view['revision'])
        owner = Record(home.resolve(unit['owner_record']))
        self.addCleanup(owner.close)
        with api.execution.worker_scope():
            api.call('operation_start', owner, identifier=unit['id'])
        owner.append('operation.state', unit['id'], {'owner_pid': 999999999})  # the backend that ran it is gone
        return view, unit, owner

    def state(self, owner, ident):
        return next(r for r in api.call('operation_list', owner) if r['id'] == ident)['state']

    def test_a_crashed_unit_in_general_work_and_in_a_course_becomes_resumable(self):
        gview, gunit, gowner = self.crashed(computer.GENERAL, 'general.txt')
        cview, cunit, cowner = self.crashed(self.course_id, 'course.txt')
        self.assertEqual((gowner.root.name, cowner.root.name), ('general-work', 'stat303'))
        self.assertEqual(self.state(gowner, gunit['id']), 'running')
        again = api.call('computer_run', self.user, plan=gview['plan'], revision=gview['revision'])
        self.assertTrue(again['duplicate'], 'before recovery the crashed unit still counts as running')
        with patch.object(runtime, 'process_alive', return_value=False):
            done = desktop.recover_computer_work(self.user)
        self.assertEqual(sorted(done), ['general-work', 'stat303'])
        for owner, unit in ((gowner, gunit), (cowner, cunit)):
            self.assertEqual(self.state(owner, unit['id']), 'interrupted')
        for view, owner in ((gview, gowner), (cview, cowner)):
            resumed = api.call('computer_run', self.user, plan=view['plan'], revision=view['revision'])
            self.assertFalse(resumed.get('duplicate'), resumed)
            self.assertEqual(resumed['attempt'], 2)
            runtime.execute_operation(owner, resumed['_operation'])
            self.assertEqual(self.state(owner, resumed['id']), 'completed')
        self.assertEqual(sorted(p.name for p in self.dst.iterdir()), ['course.txt', 'general.txt'])

    def test_records_without_computer_work_are_left_alone_and_a_missing_general_work_is_fine(self):
        other = Record(home.init('plain'))
        self.addCleanup(other.close)
        with patch.object(runtime, 'recover', wraps=runtime.recover) as spy:
            done = desktop.recover_computer_work(self.user)
        self.assertEqual(done, [])
        self.assertEqual([c.args[0].root.name for c in spy.call_args_list], [])


if __name__ == '__main__':
    unittest.main()
