"""Library material is listed at once, read afterwards, and the organizational map invents no scientific relations."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, automation, library
from ros.store import Record


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'})
        self.env.start()
        self.rec = Record(Path(self.tmp.name) / 'projects' / 'demo')
        self.folder = Path(self.tmp.name) / 'readings'
        (self.folder / 'week1').mkdir(parents=True)
        (self.folder / 'week1' / 'teleportation.md').write_text('# Quantum teleportation\n\nBell pairs and classical bits.\n', encoding='utf-8')
        (self.folder / 'notes.txt').write_text('plain notes about entanglement', encoding='utf-8')
        (self.folder / 'empty.md').write_bytes(b'')
        (self.folder / 'scan.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 20)
        (self.folder / '.env').write_text('SECRET=1', encoding='utf-8')
        (self.folder / 'data.bin').write_bytes(b'\x00\x01')
        self.source = api.call('source_register', self.rec, root=str(self.folder), kind='folder')['id']

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def shelf(self):
        return {m['path']: m for m in api.call('workspace_organization', self.rec)['library']}

    def test_adding_is_immediate_and_never_reads_content(self):
        with patch('ros.sources.preview', side_effect=AssertionError('content read while adding')):
            out = api.call('library_add', self.rec, source=self.source)
        self.assertEqual(out['added'], 4)  # md, md, txt, png; never .env or an unknown binary
        shelf = self.shelf()
        self.assertEqual(set(shelf), {'week1/teleportation.md', 'notes.txt', 'empty.md', 'scan.png'})
        self.assertTrue(all(m['state'] == 'added' for m in shelf.values()))
        self.assertEqual(out['counts']['added'], 4)

    def test_progress_ends_in_ready_or_a_reason(self):
        api.call('library_add', self.rec, source=self.source)
        while api.call('library_process', self.rec, limit=2)['remaining']:
            pass
        shelf = self.shelf()
        self.assertEqual(shelf['week1/teleportation.md']['state'], 'ready')
        self.assertEqual(shelf['week1/teleportation.md']['title'], 'Quantum teleportation')
        self.assertTrue(shelf['week1/teleportation.md']['indexed'])
        self.assertEqual(shelf['empty.md']['state'], 'attention')
        self.assertIn('empty', shelf['empty.md']['detail'])
        self.assertEqual(shelf['scan.png']['state'], 'ready')
        self.assertFalse(shelf['scan.png']['indexed'])
        hits = api.call('source_search', self.rec, q='Bell pairs')
        self.assertEqual(hits[0]['relativePath'], 'week1/teleportation.md')

    def test_repeating_add_and_process_changes_nothing(self):
        api.call('library_add', self.rec, source=self.source)
        api.call('library_process', self.rec, limit=25)
        before = len(self.rec.events())
        again = api.call('library_add', self.rec, source=self.source)
        self.assertEqual((again['added'], again['existing']), (0, 4))
        self.assertEqual(api.call('library_process', self.rec, limit=25)['processed'], 0)
        self.assertEqual(len(self.rec.events()), before)

    def test_changed_file_is_read_again_and_interrupted_reading_resumes(self):
        api.call('library_add', self.rec, source=self.source)
        api.call('library_process', self.rec, limit=25)
        note = self.folder / 'notes.txt'
        note.write_text('rewritten with a new idea about decoherence', encoding='utf-8')
        self.assertEqual(api.call('library_process', self.rec, limit=25)['ready'], 1)
        self.assertEqual(api.call('source_search', self.rec, q='decoherence')[0]['relativePath'], 'notes.txt')
        ident = library.material_id(self.source, 'notes.txt')
        self.rec.append('library.state', ident, {'state': 'reading', 'detail': 'Reading'})
        self.assertEqual([m['id'] for m in library.pending(self.rec)], [ident])
        api.call('library_process', self.rec, limit=25)
        self.assertEqual(self.shelf()['notes.txt']['state'], 'ready')

    def test_missing_original_explains_what_to_do(self):
        api.call('library_add', self.rec, source=self.source)
        (self.folder / 'notes.txt').unlink()
        api.call('library_process', self.rec, limit=25)
        row = self.shelf()['notes.txt']
        self.assertEqual(row['state'], 'attention')
        self.assertIn('Reconnect', row['detail'])
        (self.folder / 'notes.txt').write_text('back again', encoding='utf-8')
        api.call('library_retry', self.rec, subject=row['id'])
        api.call('library_process', self.rec, limit=25)
        self.assertEqual(self.shelf()['notes.txt']['state'], 'ready')

    def test_placing_in_a_folder_renaming_and_forgetting(self):
        course = api.call('organization_create', self.rec, kind='course', title='Quantum computing')
        api.call('library_add', self.rec, source=self.source, path='week1', folder=course['id'])
        row = self.shelf()['week1/teleportation.md']
        self.assertEqual(row['parent'], course['id'])
        api.call('organization_rename', self.rec, subject=row['id'], title='Teleportation lecture')
        self.assertEqual(self.shelf()['week1/teleportation.md']['title'], 'Teleportation lecture')
        with self.assertRaises(ValueError):
            api.call('library_add', self.rec, source=self.source, folder='course:missing')
        api.call('library_forget', self.rec, subject=row['id'])
        self.assertNotIn('week1/teleportation.md', self.shelf())
        self.assertTrue((self.folder / 'week1' / 'teleportation.md').exists())
        self.assertEqual(api.call('library_add', self.rec, source=self.source, path='week1')['added'], 1)

    def test_a_vault_adds_its_notes_but_never_what_the_app_generated_or_its_own_navigation(self):
        vault = Path(self.tmp.name) / 'vault'
        for rel, text in {'01 Projects/Course/lecture.md': '# Lecture\n\ntext', 'Home.md': '# Home\n\nmine',
                          'Research OS/Projects/demo/Notes.md': '# generated', '90 Templates/Session.md': '# template',
                          '99 Archive/old.md': '# old', '01 Projects/Course/Material Index.md': '# index',
                          '02 Knowledge/Material Index.md': '# index', '.obsidian/app.json': '{}'}.items():
            (vault / rel).parent.mkdir(parents=True, exist_ok=True)
            (vault / rel).write_text(text, encoding='utf-8')
        source = api.call('source_register', self.rec, root=str(vault), kind='vault')['id']
        api.call('library_add', self.rec, source=source)
        added = sorted(m['path'] for m in api.call('workspace_organization', self.rec)['library'] if m['source'] == source)
        self.assertEqual(added, ['01 Projects/Course/lecture.md', 'Home.md'])

    def test_automation_reads_waiting_material_without_a_button(self):
        api.call('library_add', self.rec, source=self.source)
        out = automation.reconcile(self.rec, 'tick')
        self.assertEqual(out['ran']['library_queue']['read'], 4)
        self.assertEqual(automation.reconcile(self.rec, 'tick')['ran'].get('library_queue'), None)


class MapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'})
        self.env.start()
        self.rec = Record(Path(self.tmp.name) / 'projects' / 'demo')

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_branching_map_names_hubs_and_never_writes_edges(self):
        r = self.rec
        r.put_node('course:qc', 'course', title='Quantum Computing')
        r.put_node('project:ams', 'project', title='AMS ECAL QML')
        r.put_node('capability:tele', 'capability', title='Teleportation')
        r.put_node('capability:bell', 'capability', title='Bell states')
        r.put_node('handout:tele', 'handout', title='Teleportation handout')
        r.put_node('source:orphan', 'source', title='Loose paper')
        r.put_node('source:blank', 'source')
        r.put_node('code-symbol:a', 'code-symbol', file='src/model_loss.py')
        r.put_node('code-symbol:b', 'code-symbol', file='src/model_loss.py')
        r.put_edge('capability:tele', 'part-of', 'course:qc')
        r.put_edge('capability:bell', 'part-of', 'course:qc')
        r.put_edge('capability:tele', 'requires', 'capability:bell')
        r.put_edge('handout:tele', 'part-of', 'course:qc')
        r.put_edge('handout:tele', 'teaches', 'capability:tele')
        edges_before = r.edges()
        nodes_before = r.nodes_path.read_bytes()
        view = api.call('workspace_map', r)
        self.assertEqual(r.edges(), edges_before)
        self.assertEqual(r.nodes_path.read_bytes(), nodes_before)
        by_id = {n['id']: n for n in view['nodes']}
        self.assertEqual(by_id[view['center']]['role'], 'center')
        self.assertEqual({by_id[i]['label'] for i in ('course:qc', 'project:ams')}, {'Quantum Computing', 'AMS ECAL QML'})
        self.assertEqual(by_id['capability:tele']['parent'], 'course:qc')
        self.assertEqual(by_id['handout:tele']['parent'], 'capability:tele')  # supporting material hangs below its topic
        inbox = 'inbox:demo'
        self.assertEqual(by_id['source:orphan']['parent'], inbox)
        self.assertEqual(by_id[inbox]['label'], 'Inbox')
        self.assertIn('source:blank', {n['id'] for n in view['needs_organization']})
        self.assertNotIn('source:blank', by_id)
        files = [n for n in view['nodes'] if n['kind'] == 'source-file']
        self.assertEqual([f['label'] for f in files], ['model_loss.py'])
        self.assertFalse(any(n['kind'] == 'code-symbol' for n in view['nodes']))
        structure = [e for e in view['edges'] if e['structure']]
        self.assertTrue(all(e['type'] == 'membership' for e in structure))
        real = {(e['src'], e['type'], e['dst']) for e in view['edges'] if not e['structure']}
        # Recorded relations only. The handout's part-of link to the course is also recorded, so it stays visible
        # even though the handout hangs under the topic it teaches.
        self.assertEqual(real, {('capability:tele', 'requires', 'capability:bell'), ('handout:tele', 'teaches', 'capability:tele'),
                                ('handout:tele', 'part-of', 'course:qc')})
        # every non-centre node has a visible parent: no detached dots
        for n in view['nodes']:
            if n['role'] != 'center':
                self.assertIn(n['parent'] or view['center'], by_id)

    def test_cap_is_reported_and_expand_shows_the_rest(self):
        self.rec.put_node('course:big', 'course', title='Big course')
        for i in range(30):
            self.rec.put_node(f'capability:c{i:02d}', 'capability', title=f'Idea {i:02d}')
            self.rec.put_edge(f'capability:c{i:02d}', 'part-of', 'course:big')
        view = api.call('workspace_map', self.rec, per_hub=10)
        self.assertEqual(view['omitted'], {'course:big': 20})
        full = api.call('workspace_map', self.rec, per_hub=10, expand='course:big')
        self.assertEqual(full['omitted'], {})
        self.assertEqual(sum(n['kind'] == 'capability' for n in full['nodes']), 30)

    def test_renamed_hub_and_folder_placement_show_in_the_map(self):
        course = api.call('organization_create', self.rec, kind='course', title='Statistics')
        self.rec.put_node('lesson:one', 'lesson', title='First lesson')
        api.call('organization_move', self.rec, subject='lesson:one', parent=course['id'])
        api.call('organization_rename', self.rec, subject=course['id'], title='Mathematical Statistics')
        by_id = {n['id']: n for n in api.call('workspace_map', self.rec)['nodes']}
        self.assertEqual(by_id[course['id']]['label'], 'Mathematical Statistics')
        self.assertEqual(by_id['lesson:one']['parent'], course['id'])


if __name__ == '__main__':
    unittest.main()
