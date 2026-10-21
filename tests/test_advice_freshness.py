"""No timezone changes, vault access, network or trusted receipt fabrication."""
from datetime import datetime, timedelta, timezone, tzinfo
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import advice_freshness as af

UTC=timezone.utc
def instant(value): return datetime.fromisoformat(value.replace('Z','+00:00'))
def cases(): return json.loads((Path(__file__).parent/'fixtures/p1clock/windows.json').read_text(encoding='utf-8'))


class TransitionZone(tzinfo):
    """Deterministic injected clock with one explicit UTC offset transition."""
    def __init__(self, at, before, after):
        self.at=instant(at).replace(tzinfo=None); self.before=timedelta(hours=before); self.after=timedelta(hours=after)
    def utcoffset(self, dt):
        wall=dt.replace(tzinfo=None); a=self.at+self.before; b=self.at+self.after
        if wall<min(a,b): return self.before
        if wall>=max(a,b): return self.after
        return self.after if dt.fold else self.before
    def dst(self, dt): return timedelta(0)
    def fromutc(self, dt):
        utc=dt.replace(tzinfo=None); offset=self.before if utc<self.at else self.after
        fold=int(self.after<self.before and self.at<=utc<self.at+self.before-self.after)
        return (utc+offset).replace(tzinfo=self,fold=fold)


class FreshnessTests(unittest.TestCase):
    def test_shared_fixture_validation_and_current(self):
        for row in cases():
            with self.subTest(row=row['name']):
                self.assertEqual(af.validate(row['window'],row['as_of']),row['valid'])
                self.assertEqual(af.is_current(row['window'],row['as_of'],row['now']),row['current'])

    def test_istanbul_local_day_does_not_become_utc_day(self):
        now=instant('2026-10-20T21:30:00Z'); zone=timezone(timedelta(hours=3))
        window=af.mint('2026-10-21',now,zone)
        self.assertEqual(window,cases()[0]['window'])
        self.assertIsNone(af.mint('2026-10-20',now,zone))
        self.assertIsNone(af.mint('2026-10-22',now,zone))

    def test_separately_resolved_dst_midnights(self):
        for day,at,before,after,hours in [('2026-03-29','2026-03-29T01:00:00Z',0,1,23),('2026-10-25','2026-10-25T01:00:00Z',1,0,25)]:
            with self.subTest(day=day):
                zone=TransitionZone(at,before,after); w=af.mint(day,instant(day+'T12:00:00Z'),zone)
                self.assertIsNotNone(w); self.assertEqual(instant(w['end'])-instant(w['start']),timedelta(hours=hours))

    def test_ambiguous_skipped_midnight_and_skipped_day_refuse(self):
        for zone,day,now in [
            (TransitionZone('2026-05-01T01:00:00Z',0,-1),'2026-05-01','2026-05-01T12:00:00Z'),
            (TransitionZone('2026-05-01T00:00:00Z',0,1),'2026-05-01','2026-05-01T12:00:00Z'),
            (TransitionZone('2026-12-30T12:00:00Z',-12,12),'2026-12-29','2026-12-29T18:00:00Z')]:
            self.assertIsNone(af.mint(day,instant(now),zone))

    def test_extreme_offsets_and_same_instant(self):
        now=instant('2026-10-21T11:30:00Z')
        for offset,day in [(14,'2026-10-22'),(-12,'2026-10-20')]:
            zone=timezone(timedelta(hours=offset)); w=af.mint(day,now,zone)
            self.assertIsNotNone(w); self.assertTrue(af.is_current(w,day,now.astimezone(zone)))

    def test_precision_boundaries_and_purity(self):
        w=copy.deepcopy(cases()[0]['window']); before=copy.deepcopy(w)
        end=instant(w['end']); self.assertTrue(af.is_current(w,w['day'],end-timedelta(microseconds=1)))
        self.assertFalse(af.is_current(w,w['day'],end)); self.assertEqual(w,before)
        self.assertFalse(af.is_current(w,w['day'],datetime(2026,10,21)))
        self.assertFalse(af.is_current(w,w['day'],float('nan')))

    def test_invalid_inputs_and_unavailable_zone_fail_safe(self):
        for day in [None,[],True,'0000-01-01','2026-2-01','2026-02-30','9999-12-31']:
            self.assertIsNone(af.mint(day,instant('2026-10-20T21:30:00Z'),UTC))
        self.assertIsNone(af.mint('2026-10-21',instant('2026-10-21T12:00:00Z'),'not/a/real/zone'))
        self.assertFalse(af.validate([], '2026-10-21'))
        self.assertIsNone(af.mint('2026-10-21',instant('2026-10-21T12:00:00Z'),timezone(timedelta(microseconds=1))))
        with patch('zoneinfo.ZoneInfo',side_effect=KeyError('missing tzdata')):
            self.assertIsNone(af.mint('2026-10-21',instant('2026-10-21T12:00:00Z'),'Europe/Istanbul'))

    def test_host_local_default_does_not_change_timezone(self):
        now=datetime.now(UTC); day=now.astimezone().date().isoformat()
        self.assertTrue(af.is_current(af.mint(day,now),day,now))


if __name__=='__main__': unittest.main()
