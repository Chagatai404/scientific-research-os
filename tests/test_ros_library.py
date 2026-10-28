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
        self.assertEqual(out['added'], 2)  # written material only: no empty file, image, secret or unknown binary
        shelf = self.shelf()
        self.assertEqual(set(shelf), {'week1/teleportation.md', 'notes.txt'})
        self.assertTrue(all(m['state'] == 'added' for m in shelf.values()))
        self.assertEqual(out['counts']['added'], 2)

    def test_progress_ends_in_ready_or_a_reason(self):
        api.call('library_add', self.rec, source=self.source)
        while api.call('library_process', self.rec, limit=2)['remaining']:
            pass
        shelf = self.shelf()
        self.assertEqual(shelf['week1/teleportation.md']['state'], 'ready')
        self.assertEqual(shelf['week1/teleportation.md']['title'], 'Quantum teleportation')
        self.assertTrue(shelf['week1/teleportation.md']['indexed'])
        self.assertNotIn('empty.md', shelf)
        self.assertNotIn('scan.png', shelf)
        hits = api.call('source_search', self.rec, q='Bell pairs')
        self.assertEqual(hits[0]['relativePath'], 'week1/teleportation.md')

    def test_repeating_add_and_process_changes_nothing(self):
        api.call('library_add', self.rec, source=self.source)
        api.call('library_process', self.rec, limit=25)
        before = len(self.rec.events())
        again = api.call('library_add', self.rec, source=self.source)
        self.assertEqual((again['added'], again['existing']), (0, 2))
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

    def test_word_and_slide_files_become_searchable(self):
        import zipfile
        with zipfile.ZipFile(self.folder / 'lecture.docx', 'w') as z:
            z.writestr('word/document.xml', '<w:document><w:p><w:t>Maximum likelihood estimators are consistent</w:t></w:p></w:document>')
        with zipfile.ZipFile(self.folder / 'week2.pptx', 'w') as z:
            z.writestr('ppt/slides/slide1.xml', '<p:sld><a:p><a:t>Quantum teleportation protocol</a:t></a:p></p:sld>')
        api.call('library_add', self.rec, source=self.source)
        api.call('library_process', self.rec, limit=25)
        self.assertEqual(self.shelf()['lecture.docx']['state'], 'ready')
        self.assertEqual(api.call('source_search', self.rec, q='likelihood estimators')[0]['relativePath'], 'lecture.docx')
        self.assertTrue(api.call('source_search', self.rec, q='teleportation protocol'))

    def test_automation_reads_waiting_material_without_a_button(self):
        api.call('library_add', self.rec, source=self.source)
        out = automation.reconcile(self.rec, 'tick')
        self.assertEqual(out['ran']['library_queue']['read'], 2)
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

    def test_central_map_files_places_under_knowledge_research_and_goals_and_never_writes_edges(self):
        r = self.rec
        r.put_node('course:qc', 'course', title='Quantum Computing')
        r.put_node('project:ams', 'project', title='AMS ECAL QML')
        r.put_node('goal:ship', 'goal', title='Publish the QML result')
        r.put_node('capability:tele', 'capability', title='Teleportation')
        r.put_node('capability:bell', 'capability', title='Bell states')
        r.put_node('question:loss', 'question', title='Does the loss converge?')
        r.put_node('handout:tele', 'handout', title='Teleportation handout')
        r.put_node('source:orphan', 'source', title='Loose paper')
        r.put_node('capability:blank', 'capability')
        r.put_node('capability:floating', 'capability', title='Floating idea')
        r.put_node('code-symbol:a', 'code-symbol', file='src/model_loss.py')
        r.put_edge('capability:tele', 'part-of', 'course:qc')
        r.put_edge('capability:bell', 'part-of', 'course:qc')
        r.put_edge('capability:tele', 'requires', 'capability:bell')
        r.put_edge('question:loss', 'part-of', 'project:ams')
        r.put_edge('question:loss', 'requires', 'capability:bell')   # research that rests on knowledge
        r.put_edge('handout:tele', 'about', 'course:qc')
        edges_before, nodes_before = r.edges(), r.nodes_path.read_bytes()
        view = api.call('workspace_map', r)
        self.assertEqual(r.edges(), edges_before)
        self.assertEqual(r.nodes_path.read_bytes(), nodes_before)
        by_id = {n['id']: n for n in view['nodes']}
        self.assertEqual(by_id[view['center']]['role'], 'center')
        self.assertEqual({i for i, n in by_id.items() if n['role'] == 'category'}, {'category:knowledge', 'category:research', 'category:goals'})
        for i in ('category:knowledge', 'category:research', 'category:goals'):
            self.assertEqual(by_id[i]['parent'], view['center'])
        self.assertEqual((by_id['course:qc']['category'], by_id['project:ams']['category'], by_id['goal:ship']['category']), ('knowledge', 'research', 'goals'))
        self.assertEqual(by_id['course:qc']['parent'], 'category:knowledge')
        self.assertEqual(by_id['capability:tele']['parent'], 'course:qc')
        self.assertEqual(by_id['question:loss']['parent'], 'project:ams')
        self.assertEqual(by_id['course:qc']['material'], 1)
        # material is counted on its place, not drawn, unless the place is expanded
        self.assertNotIn('handout:tele', by_id)
        self.assertNotIn('source:orphan', by_id)
        self.assertFalse(any(n['kind'] == 'code-symbol' for n in view['nodes']))
        needs = {n['id']: n['reason'] for n in view['needs_organization']}
        self.assertIn('capability:blank', needs)
        self.assertIn('capability:floating', needs)
        self.assertNotIn('capability:floating', by_id)
        self.assertTrue(all(e['type'] == 'membership' for e in view['edges'] if e['structure']))
        real = {(e['src'], e['type'], e['dst']): e['cross'] for e in view['edges'] if not e['structure']}
        self.assertEqual(real, {('capability:tele', 'requires', 'capability:bell'): False, ('question:loss', 'requires', 'capability:bell'): True})
        for n in view['nodes']:
            if n['role'] != 'center':
                self.assertIn(n['parent'], by_id)   # no detached dots

    def test_expanding_a_place_shows_its_files_and_nothing_else_does(self):
        self.rec.put_node('course:big', 'course', title='Big course')
        for i in range(70):
            self.rec.put_node(f'source:s{i:02d}', 'source', title=f'Chapter {i:02d}')
            self.rec.put_edge(f'source:s{i:02d}', 'about', 'course:big')
        view = api.call('workspace_map', self.rec)
        self.assertEqual({n['id']: n['material'] for n in view['nodes'] if n['role'] == 'hub'}, {'course:big': 70})
        self.assertFalse(any(n['role'] == 'source' for n in view['nodes']))
        full = api.call('workspace_map', self.rec, expand='course:big')
        files = [n for n in full['nodes'] if n['role'] == 'source']
        self.assertEqual(len(files), 60)
        self.assertTrue(all(n['parent'] == 'course:big' and n['category'] == 'knowledge' for n in files))

    def test_renamed_place_shows_in_the_map(self):
        course = api.call('organization_create', self.rec, kind='course', title='Statistics')
        self.rec.put_node('capability:var', 'capability', title='Variance')
        api.call('organization_move', self.rec, subject='capability:var', parent=course['id'])
        api.call('organization_rename', self.rec, subject=course['id'], title='Mathematical Statistics')
        by_id = {n['id']: n for n in api.call('workspace_map', self.rec)['nodes']}
        self.assertEqual(by_id[course['id']]['label'], 'Mathematical Statistics')
        self.assertEqual(by_id['capability:var']['parent'], course['id'])

    def test_a_course_and_project_of_one_name_share_a_place_and_templates_are_not_places(self):
        r = self.rec
        r.put_node('course:stat', 'course', title='STAT303 Mathematical Statistics I')
        r.put_node('project:stat-twin', 'project', title='STAT303 Mathematical Statistics I')
        r.put_node('project:template', 'project', title='{{title}}')
        r.put_node('capability:var', 'capability', title='Variance')
        r.put_edge('capability:var', 'part-of', 'course:stat')
        view = api.call('workspace_map', r)
        hubs = [n['label'] for n in view['nodes'] if n['role'] == 'hub']
        self.assertEqual(hubs, ['STAT303 Mathematical Statistics I'])
        by_id = {n['id']: n for n in view['nodes']}
        self.assertEqual(by_id['capability:var']['parent'], 'course:stat')
        self.assertIn('project:template', {n['id'] for n in view['needs_organization']})

    def test_archived_places_and_what_is_filed_only_in_them_leave_the_map_but_stay_recorded(self):
        r = self.rec
        r.put_node('course:old', 'course', title='STAT291 Old course')
        r.put_node('course:now', 'course', title='STAT303 Mathematical Statistics I')
        r.put_node('capability:old', 'capability', title='Old idea')
        r.put_node('capability:now', 'capability', title='Variance')
        r.put_edge('capability:old', 'part-of', 'course:old')
        r.put_edge('capability:now', 'part-of', 'course:now')
        api.call('organization_archive', r, subject='course:old')
        ids = {n['id'] for n in api.call('workspace_map', r)['nodes']}
        self.assertEqual(ids & {'course:old', 'capability:old'}, set())
        self.assertLessEqual({'course:now', 'capability:now'}, ids)
        self.assertEqual(r.node('course:old')['title'], 'STAT291 Old course')   # nothing deleted
        api.call('organization_archive', r, subject='course:old', archived=False)
        self.assertIn('course:old', {n['id'] for n in api.call('workspace_map', r)['nodes']})


class ProjectFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ROS_HOME': str(Path(self.tmp.name) / 'home')})
        self.env.start()
        self.vault = Path(self.tmp.name) / 'vault'
        self.vault.mkdir()
        self.rec = Record(Path(self.tmp.name) / 'home' / 'projects' / 'demo')

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_a_new_course_or_project_gets_a_vault_index_without_overwriting_anything(self):
        api.call('vault_set', self.rec, path=str(self.vault), root='Research OS')
        made = api.call('organization_create', self.rec, kind='course', title='Quantum Field Theory')
        self.assertIsNone(made['vault_note'], 'a vault with no 01 Projects folder is left alone')
        self.assertEqual(list(self.vault.iterdir()), [])
        (self.vault / '01 Projects').mkdir()
        made = api.call('organization_create', self.rec, kind='course', title='Quantum Field Theory')
        note = self.vault / made['vault_note']
        self.assertEqual(made['vault_note'], '01 Projects/Quantum Field Theory/Quantum Field Theory.md')
        text = note.read_text(encoding='utf-8')
        self.assertIn('Research OS/Courses/Quantum Field Theory/Handouts', text)
        self.assertIn('## Lecture notes', text)
        note.write_text('my own words', encoding='utf-8')
        api.call('organization_create', self.rec, kind='course', title='Quantum Field Theory')
        self.assertEqual(note.read_text(encoding='utf-8'), 'my own words')
        project = api.call('organization_create', self.rec, kind='project', title='Muon g-2')
        self.assertIn('Research OS/Projects/Muon g-2', (self.vault / project['vault_note']).read_text(encoding='utf-8'))
        collection = api.call('organization_create', self.rec, kind='collection', title='Misc')
        self.assertIsNone(collection['vault_note'])


if __name__ == '__main__':
    unittest.main()
