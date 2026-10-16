"""Teaching resources: registry, vetting rules, card snapshots, click-to-load rendering and the runtime and host wiring."""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import html_sessions as hs
import library_index as li
import resources as rs
import tutor_gate as tg
from test_context_kernel import KernelCase
from test_teaching import ONE, SOURCE
from test_tutor_gate import Base

YT = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
BASIS = 'Watched 0:05 to 2:00 against the gamma density in the course notes; the shape parameter is stated correctly.'


def page(url='https://example.org/a', **extra):
    return dict({'id': 'RES-a', 'title': 'A page', 'url': url, 'kind': 'article', 'publisher': 'Example', 'authority': 'university', 'language': 'en',
                 'concepts': ['gamma-density']}, **extra)


def fetcher(title='A page', status=200):
    def get(url):
        if 'oembed' in url:
            return status, url, json.dumps({'title': title})
        return status, url, f'<html><head><title>\n {title}\n</title></head></html>'
    return get


class Records(unittest.TestCase):
    def test_youtube_ids_come_from_watch_short_and_embed_urls_only(self):
        for url in (YT, 'https://youtu.be/dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ', 'https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=3'):
            self.assertEqual(rs.youtube_id(url), 'dQw4w9WgXcQ', url)
        for url in ('https://example.org/watch?v=dQw4w9WgXcQ', 'https://www.youtube.com/watch?v=short', 'https://www.youtube.com/@channel'):
            self.assertIsNone(rs.youtube_id(url), url)

    def test_a_candidate_needs_the_basics_and_nothing_unknown(self):
        good = dict(page(), resource_schema=1, status='candidate')
        self.assertEqual(rs.problems(good), [])
        for change, expect in (({'url': 'http://example.org'}, 'HTTPS'), ({'url': 'https://u:p@example.org'}, 'HTTPS'), ({'kind': 'podcast'}, 'kind'),
                               ({'authority': 'famous'}, 'authority'), ({'language': 'Turkish'}, 'language'), ({'concepts': []}, 'concepts'),
                               ({'id': 'gamma'}, 'id looks'), ({'mood': 'x'}, 'unknown field'), ({'status': 'trusted'}, 'status')):
            self.assertTrue(any(expect in p for p in rs.problems(dict(good, **change))), change)

    def test_embed_and_segment_are_validated(self):
        good = dict(page(YT), resource_schema=1, status='candidate', embed='youtube', video_id='dQw4w9WgXcQ', segment={'start': 5, 'end': 60})
        self.assertEqual(rs.problems(good), [])
        self.assertTrue(rs.problems(dict(good, video_id='AAAAAAAAAAA')))
        self.assertTrue(rs.problems(dict(good, url='https://example.org/v')))
        self.assertTrue(rs.problems(dict(good, segment={'start': 60, 'end': 5})))
        self.assertTrue(rs.problems(dict(good, segment={'start': -1})))

    def test_vetting_rules(self):
        checked = dict(page(), resource_schema=1, status='checked', checked={'date': '2026-10-01', 'method': 'online', 'http_status': 200})
        vetted = dict(checked, status='vetted', what_to_notice='The shape parameter.', license='CC BY 4.0',
                      vetted={'by': 'human: researcher', 'date': '2026-10-02', 'basis': BASIS, 'consequence': 'routine'})
        self.assertEqual(rs.problems(vetted), [])
        self.assertTrue(any('checked' in p for p in rs.problems(dict(vetted, checked=None))))
        self.assertTrue(any('vetted.by' in p for p in rs.problems(dict(vetted, vetted=dict(vetted['vetted'], by='somebody')))))
        self.assertTrue(any('basis' in p for p in rs.problems(dict(vetted, vetted=dict(vetted['vetted'], basis='looked fine')))))
        self.assertTrue(any('notice' in p for p in rs.problems(dict(vetted, what_to_notice=''))))
        self.assertTrue(any('licence' in p for p in rs.problems(dict(vetted, license=''))))
        agent = dict(vetted['vetted'], by='agent: tutor')
        self.assertEqual(rs.problems(dict(vetted, vetted=agent)), [], 'an agent may vet routine use')
        self.assertTrue(any('not by an agent' in p for p in rs.problems(dict(vetted, vetted=dict(agent, consequence='consequential')))))
        self.assertTrue(any('own find' in p for p in rs.problems(dict(vetted, found_by='agent: tutor', vetted=agent))))
        self.assertEqual(rs.problems(dict(vetted, found_by='human: researcher')), [], 'the human may vet what they found')
        self.assertTrue(any('why' in p for p in rs.problems(dict(vetted, status='rejected'))))

    def test_stale_vetting_is_not_reused(self):
        record = dict(page(), resource_schema=1, status='vetted', checked={'date': '2026-01-01', 'method': 'manual'}, what_to_notice='x', license='CC BY',
                      vetted={'by': 'human: r', 'date': '2025-09-01', 'basis': BASIS, 'consequence': 'routine'})
        self.assertFalse(rs.is_stale(record, date(2026, 8, 31)))
        self.assertTrue(rs.is_stale(record, date(2026, 10, 16)))
        self.assertEqual(rs.reusable({'RES-a': record}, 'gamma-density', today=date(2026, 8, 31)), [record])
        self.assertEqual(rs.reusable({'RES-a': record}, 'gamma-density', today=date(2026, 10, 16)), [])


class Lifecycle(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = rs.registry_dir(tmp.name)

    def test_candidate_check_vet_reject_in_order(self):
        rs.add(self.dir, **page(found_by='agent: tutor'), today='2026-10-01')
        with self.assertRaisesRegex(rs.ResourceError, 'already exists'):
            rs.add(self.dir, **page())
        with self.assertRaisesRegex(rs.ResourceError, 'check the link'):
            rs.vet(self.dir, 'RES-a', by='human: r', basis=BASIS, notice='n', license='CC BY')
        checked = rs.check(self.dir, 'RES-a', fetcher=fetcher('Gamma distribution — a page'), today=date(2026, 10, 2))
        self.assertEqual((checked['status'], checked['checked']['title_seen']), ('checked', 'Gamma distribution — a page'))
        with self.assertRaisesRegex(rs.ResourceError, 'own find'):
            rs.vet(self.dir, 'RES-a', by='agent: tutor', basis=BASIS, notice='n', license='CC BY', today=date(2026, 10, 3))
        vetted = rs.vet(self.dir, 'RES-a', by='human: researcher', basis=BASIS, notice='The shape parameter.', license='CC BY 4.0', today=date(2026, 10, 3))
        self.assertEqual(vetted['status'], 'vetted')
        rejected = rs.reject(self.dir, 'RES-a', 'Superseded by a better resource.')
        self.assertEqual(rejected['status'], 'rejected')
        with self.assertRaisesRegex(rs.ResourceError, 'rejected'):
            rs.check(self.dir, 'RES-a', fetcher=fetcher())

    def test_online_check_failures_are_reported_and_do_not_change_the_record(self):
        rs.add(self.dir, **page())
        with self.assertRaisesRegex(rs.ResourceError, 'HTTP 404'):
            rs.check(self.dir, 'RES-a', fetcher=fetcher(status=404))
        with self.assertRaisesRegex(rs.ResourceError, 'HTTPS'):
            rs.check(self.dir, 'RES-a', fetcher=lambda url: (200, 'http://example.org/a', ''))

        def boom(url):
            raise OSError('network is down')

        with self.assertRaisesRegex(rs.ResourceError, 'could not be checked'):
            rs.check(self.dir, 'RES-a', fetcher=boom)
        self.assertEqual(rs.load_all(self.dir)[0]['RES-a']['status'], 'candidate')

    def test_youtube_check_uses_the_oembed_title(self):
        rs.add(self.dir, **page(YT, id='RES-v', kind='video', embed='youtube'))
        record = rs.check(self.dir, 'RES-v', fetcher=fetcher('A lecture title'))
        self.assertEqual(record['checked']['title_seen'], 'A lecture title')
        self.assertEqual(record['video_id'], 'dQw4w9WgXcQ')

    def test_fetch_refuses_plain_http(self):
        with self.assertRaises(rs.ResourceError):
            rs.fetch('http://example.org/a')

    def test_reuse_prefers_the_learners_language_then_authority_and_card_snapshots_are_small(self):
        for rid, lang, authority in (('RES-en-uni', 'en', 'university'), ('RES-tr-edu', 'tr', 'educator'), ('RES-en-primary', 'en', 'primary')):
            rs.add(self.dir, **page(id=rid, language=lang, authority=authority, url=f'https://example.org/{rid}'))
            rs.check(self.dir, rid, fetcher=fetcher())
            rs.vet(self.dir, rid, by='human: researcher', basis=BASIS, notice='n', license='CC BY 4.0')
        rs.add(self.dir, **page(id='RES-cand', url='https://example.org/cand'))
        records, diagnostics = rs.load_all(self.dir)
        self.assertEqual(diagnostics, [])
        self.assertEqual([r['id'] for r in rs.reusable(records, 'gamma-density')], ['RES-en-primary', 'RES-en-uni', 'RES-tr-edu'])
        self.assertEqual([r['id'] for r in rs.reusable(records, 'gamma-density', 'tr')][0], 'RES-tr-edu')
        self.assertEqual(rs.reusable(records, 'other-concept'), [])
        card = rs.card_resource(records['RES-tr-edu'])
        self.assertEqual(set(card), {'id', 'title', 'url', 'kind', 'lang', 'publisher', 'license', 'vetted_on'})
        self.assertEqual(tg.resource_issues('b', [card]), [], 'a registry snapshot is a valid card resource')

    def test_the_index_has_a_link_in_every_row_and_lints_clean(self):
        rs.add(self.dir, **page(title='Pipes | and more'))
        records, _ = rs.load_all(self.dir)
        text = rs.index_markdown(records)
        self.assertIn('https://example.org/a', text)
        self.assertEqual(li.lint(text), [])

    def test_damaged_files_are_reported_not_fatal(self):
        rs.add(self.dir, **page())
        (self.dir / 'RES-broken.resource.json').write_text('{nope', encoding='utf-8')
        (self.dir / 'RES-wrong.resource.json').write_text(json.dumps(dict(page(id='RES-other'), resource_schema=1, status='candidate')), encoding='utf-8')
        records, diagnostics = rs.load_all(self.dir)
        self.assertEqual(list(records), ['RES-a'])
        self.assertEqual(len(diagnostics), 2)

    def test_the_cli_round_trip(self):
        script = str(ROOT / 'scripts/resources.py')
        vault = str(self.dir.parents[1])

        def run(*args):
            return subprocess.run([sys.executable, '-S', '-B', script, '--vault', vault, *args], capture_output=True, text=True, encoding='utf-8')

        add = ('add', '--id', 'RES-c', '--title', 'T', '--url', 'https://example.org/c', '--kind', 'article', '--publisher', 'P',
               '--authority', 'university', '--language', 'tr', '--concept', 'gamma-density')
        self.assertEqual(run(*add).returncode, 0)
        self.assertEqual(run(*add).returncode, 2)
        shown = json.loads(run('list', '--lang', 'tr').stdout)
        self.assertEqual([r['id'] for r in shown['resources']], ['RES-c'])
        self.assertEqual(run('card', 'RES-c').returncode, 2, 'only a vetted resource becomes a card resource')
        self.assertEqual(run('validate').returncode, 0)
        self.assertIn('https://example.org/c', run('index').stdout)


class CardsAndPages(Base):
    VIDEO = {'id': 'RES-v', 'title': 'The wait for several events', 'url': YT, 'kind': 'video', 'lang': 'en', 'publisher': 'Example Channel',
             'license': 'Standard YouTube licence', 'embed': 'youtube', 'video_id': 'dQw4w9WgXcQ', 'start': 5, 'end': 60}
    SIM = {'id': 'RES-s', 'title': 'A simulation', 'url': 'https://phet.colorado.edu/en/simulations/', 'kind': 'interactive', 'lang': 'en',
           'publisher': 'PhET Interactive Simulations', 'license': 'CC BY 4.0', 'attribution': 'Simulation by PhET Interactive Simulations'}

    def block(self, *items):
        return dict(ONE, card=dict(ONE['card'], resources=list(items)))

    def test_card_resources_are_validated(self):
        self.assertEqual(tg.card_issues('b', self.block(self.VIDEO, self.SIM)['card']), [])
        bad = (dict(self.VIDEO, url='http://www.youtube.com/watch?v=dQw4w9WgXcQ'), dict(self.VIDEO, video_id='AAAAAAAAAAA'), dict(self.VIDEO, embed='vimeo'),
               dict(self.SIM, kind='podcast'), dict(self.SIM, id='gamma'), dict(self.SIM, extra=1), dict(self.SIM, start=-5), dict(self.SIM, url='https://u:p@x.org/'))
        for item in bad:
            self.assertTrue(tg.card_issues('b', self.block(item)['card']), item)
        self.assertTrue(tg.card_issues('b', self.block(self.SIM, dict(self.SIM))['card']), 'duplicate ids')
        self.assertTrue(tg.card_issues('b', self.block(*[dict(self.SIM, id=f'RES-{i}') for i in range(7)])['card']))
        self.assertTrue(tg.card_issues('b', self.block()['card']))

    def test_the_projection_lists_resources_collapsed_with_their_source_host_and_id(self):
        name = self.make(SOURCE)
        self.declare(name, self.block(self.VIDEO, self.SIM))
        shown = hs._teaching_source(self.state(name))
        self.assertIn('> [!resource]- Go further', shown)
        self.assertIn('- **The wait for several events** — video, en · Example Channel · Standard YouTube licence · youtube.com · `RES-v`', shown)
        self.assertIn('phet.colorado.edu · `RES-s`', shown)
        listing = shown.split('Go further')[1].split('\n\n')[0]
        self.assertNotIn('https://', listing, 'the list shows hosts, not clickable links')

    def test_only_a_youtube_resource_widens_the_page_policy_and_no_frame_exists_before_a_click(self):
        name = self.make(SOURCE)
        self.declare(name, self.block(self.SIM))
        plain = hs.render_html(self.state(name), standalone=True)
        self.assertNotIn('frame-src', plain)
        self.assertEqual(plain.count('<iframe'), 0)
        name2 = self.make(SOURCE, name='b.md')
        self.declare(name2, self.block(self.VIDEO, self.SIM))
        embedded = hs.render_html(self.state(name2), standalone=True)
        self.assertIn("base-uri 'none'; frame-src https://www.youtube-nocookie.com\">", embedded)
        self.assertEqual(embedded.count('frame-src'), 1)
        self.assertEqual(embedded.count('<iframe'), 0, 'the player is created by a click, not by the page')
        self.assertIn('data-ros="resource"', embedded)

    def test_runtime_and_host_carry_the_click_to_load_contract(self):
        bundle = (ROOT / 'assets/html-runtime/session.js').read_text(encoding='utf-8')
        for needle in ('open-resource', 'resource-opened', 'youtube-nocookie.com/embed/', 'allow-scripts allow-same-origin allow-presentation', 'Play here'):
            self.assertIn(needle, bundle)
        self.assertNotIn('autoplay', bundle.split('youtube-nocookie.com/embed/')[1][:300])
        host = (ROOT / 'extensions/obsidian-html/main.js').read_text(encoding='utf-8')
        self.assertIn("frame-src \\'none\\'", host, 'the companion still forbids frames')
        self.assertIn("data.type === 'open-resource'", host)


class Receipt(KernelCase):
    def test_vetted_resources_for_the_target_concept_ride_in_the_receipt_without_changing_its_outcome(self):
        before = self.build()
        self.assertEqual(before['retrieval']['resources']['status'], 'empty')
        directory = rs.registry_dir(self.vault)
        rs.add(directory, **page(concepts=['box-counting']))
        rs.check(directory, 'RES-a', fetcher=fetcher())
        rs.vet(directory, 'RES-a', by='human: researcher', basis=BASIS, notice='n', license='CC BY 4.0')
        after = self.build()
        self.assertEqual(after['outcome'], before['outcome'])
        self.assertEqual([r['id'] for r in after['retrieval']['resources']['reusable']], ['RES-a'])
        none = self.build(vault=None, project=None, target=None, workflow='standalone-question')
        self.assertIsNone(none['retrieval']['resources'])


if __name__ == '__main__':
    unittest.main()
