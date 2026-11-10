"""Independent processes can build a cold derived index and keep writing the same record."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ros.store import Record, canonical, make_event  # noqa: E402


WORKER = r"""
import json, sqlite3, sys, time
from pathlib import Path
from ros import store

# Widen the actual check/create race without replacing SQLite or its results.
class SlowSchema(sqlite3.Connection):
    def executescript(self, sql):
        if 'CREATE TABLE meta(' in sql:
            time.sleep(.15)
        return super().executescript(sql)

connect = sqlite3.connect
store.sqlite3.connect = lambda *a, **kw: connect(*a, factory=SlowSchema, **kw)
root, worker = Path(sys.argv[1]), sys.argv[2]
record = store.Record(root)
(root / ('ready-' + worker)).touch()
sys.stdin.readline()
try:
    original = [event['id'] for event in record.events(type='fixture')]
    print(json.dumps({'original': original}), flush=True)
    (root / ('opened-' + worker)).touch()
    sys.stdin.readline()
    for number in range(8):
        record.append('fixture.writer', 'subject:shared', {'worker': worker, 'number': number},
                      id=f'writer-{worker}-{number}')
    print(json.dumps({'written': worker}), flush=True)
finally:
    record.close()
"""


class ColdIndexConcurrencyTest(unittest.TestCase):
    def test_two_cold_opens_then_both_writers_preserve_the_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'record'
            (root / 'graph').mkdir(parents=True)
            original = canonical(make_event('fixture', 'subject:shared', {'text': 'original ğ'},
                                            id='original')) + b'\n'
            (root / 'events.jsonl').write_bytes(original)
            nodes = canonical({'id': 'subject:shared', 'type': 'subject', 'title': 'Shared'}) + b'\n'
            (root / 'graph' / 'nodes.jsonl').write_bytes(nodes)
            edges = b''
            (root / 'graph' / 'edges.jsonl').write_bytes(edges)
            self.assertFalse((root / 'index.sqlite').exists())
            env = {**os.environ, 'ROS_NO_VAULT': '1', 'ROS_HOME': str(Path(directory) / 'home'),
                   'PYTHONUTF8': '1'}
            processes = []
            try:
                for worker in ('a', 'b'):
                    processes.append(subprocess.Popen(
                        [sys.executable, '-c', WORKER, str(root), worker],
                        cwd=Path(__file__).resolve().parents[1], env=env,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding='utf-8'))
                deadline = time.monotonic() + 15
                while not all((root / ('ready-' + worker)).exists() for worker in ('a', 'b')):
                    if time.monotonic() >= deadline or any(p.poll() is not None for p in processes):
                        self.fail('cold-index workers did not reach the start barrier')
                    time.sleep(.01)
                for process in processes:
                    process.stdin.write('open\n')
                    process.stdin.flush()
                # Wait for both opens before either writer may append: reads must preserve source bytes.
                deadline = time.monotonic() + 15
                while not all((root / ('opened-' + worker)).exists() for worker in ('a', 'b')):
                    for process in processes:
                        if process.poll() is not None:
                            _, errors = process.communicate(timeout=15)
                            self.fail(errors)
                    self.assertLess(time.monotonic(), deadline, 'cold-index open timed out')
                    time.sleep(.01)
                opened = [p.stdout.readline() for p in processes]
                for process, line in zip(processes, opened):
                    if not line:
                        _, errors = process.communicate(timeout=15)
                        self.fail(errors)
                    self.assertEqual(json.loads(line), {'original': ['original']})
                self.assertEqual((root / 'events.jsonl').read_bytes(), original)
                self.assertEqual((root / 'graph' / 'nodes.jsonl').read_bytes(), nodes)
                self.assertEqual((root / 'graph' / 'edges.jsonl').read_bytes(), edges)
                for process in processes:
                    process.stdin.write('write\n')
                    process.stdin.flush()
                for process in processes:
                    output, errors = process.communicate(timeout=15)
                    self.assertEqual(process.returncode, 0, errors)
                    self.assertIn('written', json.loads(output))
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=15)

            expected = {'original'} | {f'writer-{worker}-{number}'
                                       for worker in ('a', 'b') for number in range(8)}
            event_bytes = (root / 'events.jsonl').read_bytes()
            self.assertTrue(event_bytes.startswith(original))
            written = [json.loads(line)['id'] for line in event_bytes.splitlines()]
            self.assertEqual(len(written), len(expected))
            self.assertEqual(set(written), expected)
            self.assertEqual((root / 'graph' / 'nodes.jsonl').read_bytes(), nodes)
            self.assertEqual((root / 'graph' / 'edges.jsonl').read_bytes(), edges)
            record = Record(root)
            try:
                self.assertEqual({e['id'] for e in record.events(type='fixture')}, expected)
                self.assertEqual(record.node('subject:shared')['title'], 'Shared')
                self.assertEqual(record.index().execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(record.index().execute('SELECT COUNT(*) FROM events').fetchone()[0],
                                 len(expected))
                self.assertEqual(record.problems, [])
            finally:
                record.close()


if __name__ == '__main__':
    unittest.main()
