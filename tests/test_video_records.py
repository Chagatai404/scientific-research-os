"""The safe records a session plan's video segments are handed: the vetted registry records they name, as card snapshots, and nothing the page could turn into an address of its own."""
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import resources as rs

YT = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
BASIS = 'Watched 0:30 to 3:30 against the course notes on variance; the effect of rescaling is stated correctly.'
SESSION = 'Sessions/lesson.md'


def fetcher(url):
    return 200, url, json.dumps({'title': 'Why spread changes'}) if 'oembed' in url else '<html><head><title>Why spread changes</title></head></html>'


class VideoRecords(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = Path(self.tmp.name)
        (self.vault / 'Sessions').mkdir()
        hs.install_runtime(self.vault)
        hs.create_session(self.vault, SESSION, '# Variance\n\nA lesson.\n', title='Variance')
        self.dir = rs.registry_dir(self.vault)
        plan = json.loads((ROOT / 'examples' / 'session-plan-variance.json').read_text(encoding='utf-8'))
        for segment in plan['segments']:
            if 'video' in segment:
                segment['video']['resource'] = 'RES-v'
        self.plan = plan

    def add(self, **extra):
        fields = dict(id='RES-v', title='Why spread changes', url=YT, kind='video', publisher='An educator', authority='educator', language='en', concepts=['variance'],
                      embed='youtube', found_by='agent: finder')
        fields.update(extra)
        rs.add(self.dir, **fields)

    def vet(self, resource='RES-v', today=None):
        rs.check(self.dir, resource, fetcher=fetcher)
        rs.vet(self.dir, resource, by='reviewer: second pair of eyes', basis=BASIS, notice='The same shape gets wider.', license='Standard YouTube licence', today=today)

    def state(self):
        return hs.load_session(self.vault, SESSION)

    def test_a_vetted_embeddable_record_is_handed_over_as_a_card_snapshot(self):
        self.add(); self.vet()
        hs.update_session(self.vault, SESSION, plan=self.plan)
        records = self.state()['video_records']
        self.assertEqual(list(records), ['RES-v'])
        self.assertEqual(records['RES-v'], rs.card_resource(rs.load_all(self.dir)[0]['RES-v']))
        self.assertEqual(records['RES-v']['video_id'], 'dQw4w9WgXcQ')
        self.assertEqual(records['RES-v']['embed'], 'youtube')
        self.assertEqual(records['RES-v']['vetted_on'], date.today().isoformat())

    def test_a_record_that_is_not_ready_is_left_out_and_the_plan_is_still_accepted(self):
        hs.update_session(self.vault, SESSION, plan=self.plan)                     # not in the registry at all
        self.assertNotIn('video_records', self.state())
        self.add()                                                                 # a candidate
        hs.update_session(self.vault, SESSION, plan=self.plan)
        self.assertNotIn('video_records', self.state())
        rs.check(self.dir, 'RES-v', fetcher=fetcher)                               # checked, not vetted
        hs.update_session(self.vault, SESSION, plan=self.plan)
        self.assertNotIn('video_records', self.state())
        self.vet()
        rs.reject(self.dir, 'RES-v', 'The explanation of the effect of scaling is wrong.')
        hs.update_session(self.vault, SESSION, plan=self.plan)
        self.assertNotIn('video_records', self.state())

    def test_stale_vetting_is_left_out(self):
        self.add(); self.vet(today=date(2020, 1, 1))
        hs.update_session(self.vault, SESSION, plan=self.plan)
        self.assertNotIn('video_records', self.state())

    def test_a_record_without_an_embed_is_left_out(self):
        self.add(embed=None, url='https://example.org/lecture', kind='article'); self.vet()
        hs.update_session(self.vault, SESSION, plan=self.plan)
        self.assertNotIn('video_records', self.state())

    def test_only_the_records_a_plan_names_are_handed_over_and_a_plan_without_videos_clears_them(self):
        self.add(); self.vet()
        self.add(id='RES-other', title='Another', url='https://youtu.be/aaaaaaaaaaa'); self.vet('RES-other')
        hs.update_session(self.vault, SESSION, plan=self.plan)
        self.assertEqual(list(self.state()['video_records']), ['RES-v'], 'a vetted record the plan does not name is not handed over')
        plain = json.loads(json.dumps(self.plan))
        for segment in plain['segments']:
            segment.pop('video', None)
        plain['segments'] = [s for s in plain['segments'] if s.get('script')]
        hs.update_session(self.vault, SESSION, plan=plain)
        self.assertNotIn('video_records', self.state())

    def test_the_plan_holds_no_address_and_the_snapshot_is_the_only_one_the_page_gets(self):
        self.add(); self.vet()
        hs.update_session(self.vault, SESSION, plan=self.plan)
        state = self.state()
        self.assertFalse([s for s in state['plan']['segments'] if 'video' in s and set(s['video']) - {'resource', 'start', 'end', 'notice'}], 'a plan segment names a record and a part, never an address')
        self.assertEqual(sorted(state['video_records']['RES-v']), sorted(rs.card_resource(rs.load_all(self.dir)[0]['RES-v'])))

    def test_forged_video_records_are_refused_when_the_session_is_saved(self):
        self.add(); self.vet()
        hs.update_session(self.vault, SESSION, plan=self.plan)
        good = self.state()
        hs.validate_state(good)
        record = good['video_records']['RES-v']
        for change in ({'url': 'http://www.youtube.com/watch?v=dQw4w9WgXcQ'}, {'url': 'https://user:pw@www.youtube.com/watch?v=dQw4w9WgXcQ'}, {'url': 'https://example.org/watch?v=dQw4w9WgXcQ'},
                       {'video_id': 'AAAAAAAAAAA'}, {'video_id': 'short'}, {'embed': None}, {'embed': 'vimeo'}, {'id': 'RES-x'}, {'title': 'x' * 201}, {'title': 7},
                       {'vetted_on': 'yesterday'}, {'vetted_on': '2026-1-1'}, {'vetted_on': None}):
            forged = json.loads(json.dumps(good))
            forged['video_records']['RES-v'] = dict(record, **change)
            with self.assertRaises(ValueError, msg=str(change)):
                hs.validate_state(forged)
        for bad in ('text', [], {'not-an-id': record}, {'RES-v': 'text'}, {'RES-%d' % n: dict(record, id='RES-%d' % n) for n in range(33)}):
            forged = json.loads(json.dumps(good))
            forged['video_records'] = bad
            with self.assertRaises(ValueError, msg=str(bad)[:40]):
                hs.validate_state(forged)


if __name__ == '__main__':
    unittest.main()
